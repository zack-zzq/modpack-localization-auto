"""Upload translated mod files to i18n-Dict-Merged repository.

Pushes en_us.json (original) + zh_cn.json (translated) pairs to
assets/{mc_version}/{modid}/ in the target GitHub repository.
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


def _get_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _get_file_sha(
    client: httpx.Client, repo: str, path: str, headers: dict[str, str]
) -> str | None:
    """Get the SHA of an existing file in the repo (needed for updates)."""
    resp = client.get(f"{GITHUB_API}/repos/{repo}/contents/{path}", headers=headers)
    if resp.status_code == 200:
        return resp.json().get("sha")
    return None


def _upload_file(
    client: httpx.Client,
    repo: str,
    path: str,
    content_bytes: bytes,
    message: str,
    headers: dict[str, str],
) -> bool:
    """Create or update a file in the repo via GitHub Contents API."""
    encoded = base64.b64encode(content_bytes).decode("ascii")

    body: dict = {
        "message": message,
        "content": encoded,
    }

    # Check if file already exists (need SHA for update)
    existing_sha = _get_file_sha(client, repo, path, headers)
    if existing_sha:
        body["sha"] = existing_sha

    resp = client.put(
        f"{GITHUB_API}/repos/{repo}/contents/{path}",
        headers=headers,
        json=body,
        timeout=30.0,
    )

    if resp.status_code in (200, 201):
        action = "updated" if existing_sha else "created"
        logger.debug("  %s: %s", action, path)
        return True
    else:
        logger.warning(
            "  Failed to upload %s: %d %s",
            path,
            resp.status_code,
            resp.text[:200],
        )
        return False


def upload_to_dict_repo(
    extracted_dir: Path,
    translated_dir: Path,
    mc_version: str,
    config: AppConfig,
) -> None:
    """Upload translated mod files to the i18n-Dict-Merged repository.

    For each mod in translated/mods/{modid}/en_us.json:
      - Copies extracted/mods/{modid}/en_us.json as the English original
      - Uses translated/mods/{modid}/en_us.json as zh_cn.json (the translations)
      - Uploads both to assets/{mc_version}/{modid}/ in the dict repo

    Args:
        extracted_dir: Path to work/<slug>/extracted/
        translated_dir: Path to work/<slug>/translated/
        mc_version: Minecraft version string (e.g. "1.21.1")
        config: App configuration with github_token and dict_repo
    """
    if not config.github_token:
        logger.warning("No GITHUB_TOKEN configured, skipping dict upload")
        return

    mods_extracted = extracted_dir / "mods"
    mods_translated = translated_dir / "mods"

    if not mods_translated.is_dir():
        logger.info("No translated mods found, skipping upload")
        return

    # Only upload mods that used LLM translation (not dictionary-matched)
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
    logger.info("LLM-translated mods to upload: %d", len(llm_modid_set))

    # Collect mod directories — only those in the LLM manifest
    mod_dirs = sorted(
        d for d in mods_translated.iterdir()
        if d.is_dir() and d.name in llm_modid_set and (d / "en_us.json").exists()
    )

    if not mod_dirs:
        logger.info("No mod translation files found, skipping upload")
        return

    logger.info(
        "Uploading %d mod translations to %s...",
        len(mod_dirs),
        config.dict_repo,
    )

    headers = _get_headers(config.github_token)
    uploaded = 0
    failed = 0

    with httpx.Client(follow_redirects=True, timeout=30.0) as client:
        for mod_dir in mod_dirs:
            modid = mod_dir.name
            zh_cn_file = mod_dir / "en_us.json"  # This contains the Chinese translations
            en_us_file = mods_extracted / modid / "en_us.json"

            if not en_us_file.exists():
                logger.warning("  %s: en_us.json not found in extracted, skipping", modid)
                failed += 1
                continue

            # Read the files
            try:
                en_content = en_us_file.read_bytes()
                zh_content = zh_cn_file.read_bytes()
            except Exception as e:
                logger.warning("  %s: failed to read files: %s", modid, e)
                failed += 1
                continue

            # Validate JSON
            try:
                en_data = json.loads(en_content)
                zh_data = json.loads(zh_content)
            except json.JSONDecodeError as e:
                logger.warning("  %s: invalid JSON: %s", modid, e)
                failed += 1
                continue

            # Skip if the translated file has no actual Chinese content
            # (all values are same as English → nothing was translated)
            has_translation = any(
                zh_data.get(k) != v
                for k, v in en_data.items()
                if k in zh_data
            )
            if not has_translation:
                logger.debug("  %s: no actual translations, skipping", modid)
                continue

            # Upload paths: assets/{mc_version}/{modid}/{en_us,zh_cn}.json
            base_path = f"assets/{mc_version}/{modid}"
            commit_msg = f"feat({modid}): update translations for {mc_version}"

            ok_en = _upload_file(
                client, config.dict_repo,
                f"{base_path}/en_us.json",
                en_content, commit_msg, headers,
            )
            ok_zh = _upload_file(
                client, config.dict_repo,
                f"{base_path}/zh_cn.json",
                zh_content, commit_msg, headers,
            )

            if ok_en and ok_zh:
                uploaded += 1
                logger.info("  [%d/%d] Uploaded %s", uploaded, len(mod_dirs), modid)
            else:
                failed += 1

    logger.info(
        "Upload complete: %d succeeded, %d failed out of %d mods",
        uploaded,
        failed,
        len(mod_dirs),
    )

