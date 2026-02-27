"""Upload translated mod files to i18n-Dict-Merged repository.

Uses the GitHub Git Data API to batch all file changes into a single
commit and push, avoiding multiple Action triggers.

Flow: create blobs → create tree → create commit → update ref
"""

from __future__ import annotations

import base64
import json
import logging
from pathlib import Path

import httpx

from .config import AppConfig

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def upload_to_dict_repo(
    extracted_dir: Path,
    translated_dir: Path,
    mc_version: str,
    config: AppConfig,
) -> None:
    """Upload translated mod files to i18n-Dict-Merged in a single commit.

    Only uploads mods listed in _llm_translated.json (LLM-translated mods).
    Each mod produces two files: en_us.json (originals) + zh_cn.json (translations).
    All files are committed in one batch push via the Git Data API.
    """
    if not config.github_token:
        logger.warning("No GITHUB_TOKEN configured, skipping dict upload")
        return

    mods_extracted = extracted_dir / "mods"
    mods_translated = translated_dir / "mods"

    if not mods_translated.is_dir():
        logger.info("No translated mods found, skipping upload")
        return

    # Only upload mods that used LLM translation
    manifest_path = mods_translated / "_llm_translated.json"
    if not manifest_path.exists():
        logger.info("No LLM translation manifest found, skipping upload")
        return

    try:
        llm_modids: list[str] = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("Failed to read LLM manifest: %s", e)
        return

    llm_modid_set = set(llm_modids)

    # Collect files to upload
    file_entries: list[tuple[str, bytes]] = []  # (repo_path, content)

    for modid in sorted(llm_modid_set):
        mod_translated = mods_translated / modid
        zh_cn_file = mod_translated / "en_us.json"  # Contains Chinese translations
        en_us_file = mods_extracted / modid / "en_us.json"

        if not zh_cn_file.exists() or not en_us_file.exists():
            logger.debug("  %s: missing files, skipping", modid)
            continue

        try:
            en_content = en_us_file.read_bytes()
            zh_content = zh_cn_file.read_bytes()
        except Exception as e:
            logger.warning("  %s: failed to read files: %s", modid, e)
            continue

        # Validate JSON
        try:
            en_data = json.loads(en_content)
            zh_data = json.loads(zh_content)
        except json.JSONDecodeError as e:
            logger.warning("  %s: invalid JSON: %s", modid, e)
            continue

        # Skip if no actual translations (all values same as English)
        has_translation = any(
            zh_data.get(k) != v for k, v in en_data.items() if k in zh_data
        )
        if not has_translation:
            logger.debug("  %s: no actual translations, skipping", modid)
            continue

        base_path = f"assets/{mc_version}/{modid}"
        file_entries.append((f"{base_path}/en_us.json", en_content))
        file_entries.append((f"{base_path}/zh_cn.json", zh_content))

    if not file_entries:
        logger.info("No files to upload after filtering")
        return

    logger.info(
        "Uploading %d files (%d mods) to %s in a single commit...",
        len(file_entries),
        len(file_entries) // 2,
        config.dict_repo,
    )

    # ── Git Data API: single commit, single push ──
    headers = _headers(config.github_token)
    repo = config.dict_repo
    branch = "main"

    with httpx.Client(follow_redirects=True, timeout=60.0) as client:
        try:
            _batch_commit(client, repo, branch, file_entries, headers, mc_version)
        except Exception as e:
            logger.error("Upload failed: %s", e)
            return

    logger.info("Upload complete: %d files in 1 commit", len(file_entries))


def _batch_commit(
    client: httpx.Client,
    repo: str,
    branch: str,
    files: list[tuple[str, bytes]],
    headers: dict[str, str],
    mc_version: str,
) -> None:
    """Create a single commit with all files and push it."""
    # 1. Get current HEAD SHA and tree SHA
    ref_resp = client.get(
        f"{GITHUB_API}/repos/{repo}/git/ref/heads/{branch}",
        headers=headers,
    )
    ref_resp.raise_for_status()
    head_sha = ref_resp.json()["object"]["sha"]

    commit_resp = client.get(
        f"{GITHUB_API}/repos/{repo}/git/commits/{head_sha}",
        headers=headers,
    )
    commit_resp.raise_for_status()
    base_tree_sha = commit_resp.json()["tree"]["sha"]

    # 2. Create blobs for all files
    tree_items = []
    for i, (path, content) in enumerate(files):
        blob_resp = client.post(
            f"{GITHUB_API}/repos/{repo}/git/blobs",
            headers=headers,
            json={
                "content": base64.b64encode(content).decode("ascii"),
                "encoding": "base64",
            },
        )
        blob_resp.raise_for_status()
        blob_sha = blob_resp.json()["sha"]

        tree_items.append({
            "path": path,
            "mode": "100644",
            "type": "blob",
            "sha": blob_sha,
        })

        if (i + 1) % 20 == 0:
            logger.info("  Created %d/%d blobs...", i + 1, len(files))

    # 3. Create tree
    tree_resp = client.post(
        f"{GITHUB_API}/repos/{repo}/git/trees",
        headers=headers,
        json={
            "base_tree": base_tree_sha,
            "tree": tree_items,
        },
    )
    tree_resp.raise_for_status()
    new_tree_sha = tree_resp.json()["sha"]

    if new_tree_sha == base_tree_sha:
        logger.info("  No changes detected compared to upstream (tree is identical). Skipping commit.")
        return

    # 4. Create commit
    mod_count = len(files) // 2
    commit_message = (
        f"feat: add translations for {mod_count} mods ({mc_version})\n\n"
        f"Auto-generated by modpack-localization-auto"
    )

    new_commit_resp = client.post(
        f"{GITHUB_API}/repos/{repo}/git/commits",
        headers=headers,
        json={
            "message": commit_message,
            "tree": new_tree_sha,
            "parents": [head_sha],
        },
    )
    new_commit_resp.raise_for_status()
    new_commit_sha = new_commit_resp.json()["sha"]

    # 5. Update ref (this is the single push)
    update_resp = client.patch(
        f"{GITHUB_API}/repos/{repo}/git/refs/heads/{branch}",
        headers=headers,
        json={"sha": new_commit_sha},
    )
    update_resp.raise_for_status()

    logger.info(
        "  Committed %s (%d files, %d mods)",
        new_commit_sha[:8],
        len(files),
        mod_count,
    )
