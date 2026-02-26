"""Translate extracted strings using dictionary matching and LLM."""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path

import httpx
from openai import OpenAI

from .config import AppConfig

logger = logging.getLogger(__name__)

# ── Dictionary loader ──────────────────────────────────────────────

DICT_MINI_URL = (
    "https://github.com/VM-Chinese-translate-group/i18n-Dict-Extender"
    "/releases/latest/download/Dict-Mini.json"
)


def load_dictionary(work_dir: Path) -> dict[str, list[str]]:
    """Download and load Dict-Mini.json from i18n-Dict-Extender releases.

    Returns a mapping of english_text -> [chinese_translations] sorted by frequency.
    """
    cache_path = work_dir / "dict-mini.json"

    if not cache_path.exists():
        logger.info("Downloading Dict-Mini.json...")
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with httpx.Client(follow_redirects=True, timeout=60.0) as client:
                resp = client.get(DICT_MINI_URL)
                resp.raise_for_status()
                cache_path.write_bytes(resp.content)
            logger.info("Dict-Mini.json downloaded (%d bytes)", cache_path.stat().st_size)
        except Exception as e:
            logger.warning("Failed to download Dict-Mini.json: %s", e)
            return {}
    else:
        logger.info("Using cached Dict-Mini.json")

    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
        return {}
    except Exception as e:
        logger.warning("Failed to parse Dict-Mini.json: %s", e)
        return {}


# ── Dictionary-based translation ──────────────────────────────────


def translate_with_dictionary(
    entries: dict[str, str],
    dictionary: dict[str, list[str]],
) -> tuple[dict[str, str], dict[str, str]]:
    """Translate entries using exact dictionary matching.

    Args:
        entries: Mapping of translation_key -> english_value.
        dictionary: Dict-Mini.json data (english -> [chinese_translations]).

    Returns:
        (translated, remaining) — translated entries and untranslated entries.
    """
    translated: dict[str, str] = {}
    remaining: dict[str, str] = {}

    for key, value in entries.items():
        if value in dictionary and dictionary[value]:
            translated[key] = dictionary[value][0]  # highest frequency
        else:
            remaining[key] = value

    logger.info(
        "Dictionary translation: %d translated, %d remaining",
        len(translated),
        len(remaining),
    )
    return translated, remaining


# ── LLM-based translation ─────────────────────────────────────────

SYSTEM_PROMPT_TEMPLATE = """\
你是一位专业的 Minecraft 模组翻译专家，精通英文到简体中文的翻译。你的任务是将 Minecraft 模组/整合包中的英文文本翻译成简体中文。

## 翻译规范

1. **保留所有格式代码**：不要修改 `§` 颜色代码（如 `§a`, `§l`, `§r`）、`&` 颜色代码（如 `&a`, `&l`）、以及 Minecraft 格式代码。
2. **保留所有占位符**：`%s`, `%d`, `%1$s`, `%2$d`, `{0}`, `{1}` 等占位符必须原样保留。
3. **保留技术标记**：JSON 转义字符、`\\n` 换行符等必须保留。
4. **专有名词**：Minecraft 物品名、方块名、实体名等应参考社区通用译名。如果不确定，保留英文原文。
5. **不要翻译**：
   - 纯数字、标点符号
   - 命令（以 `/` 开头的）
   - 变量名（如 `player_name`）
   - 资源路径（如 `minecraft:stone`）
   - 已经是中文的文本
6. **翻译风格**：使用简洁、自然的中文翻译，符合 Minecraft 中文社区的习惯用语。

## 参考词典

以下是一些模组翻译词典中的参考条目，请在翻译时参考：

$dict_context

## 输入格式

输入是一个 JSON 对象，键是翻译键（translation key），值是需要翻译的英文文本。

## 输出格式

输出一个 JSON 对象，键与输入相同，值是对应的简体中文翻译。不要输出任何其他内容，只输出 JSON。
"""


def _build_dict_context(
    entries: dict[str, str],
    dictionary: dict[str, list[str]],
    max_entries: int = 200,
) -> str:
    """Build dictionary context for the LLM prompt.

    Extracts relevant dictionary entries based on words appearing in the
    values to translate.
    """
    if not dictionary:
        return "（无可用词典条目）"

    # Collect unique words from all values
    words: set[str] = set()
    for value in entries.values():
        # Split on non-alpha characters to get individual words
        for word in re.split(r"[^a-zA-Z]+", value):
            if len(word) >= 2:  # skip single characters
                words.add(word)
                words.add(word.lower())
                words.add(word.capitalize())

    # Find matching dictionary entries
    context_entries: list[str] = []
    for en_text, zh_list in dictionary.items():
        if len(context_entries) >= max_entries:
            break
        # Check if any word appears in this dictionary entry
        if any(w in en_text for w in words):
            zh = zh_list[0] if zh_list else "?"
            context_entries.append(f"- {en_text} → {zh}")

    if not context_entries:
        return "（无匹配的词典条目）"

    return "\n".join(context_entries)


def translate_with_llm(
    entries: dict[str, str],
    config: AppConfig,
    dictionary: dict[str, list[str]] | None = None,
) -> dict[str, str]:
    """Translate entries using OpenAI-compatible LLM API.

    Args:
        entries: Mapping of translation_key -> english_value.
        config: App configuration with LLM settings.
        dictionary: Optional Dict-Mini.json for context injection.

    Returns:
        Mapping of translation_key -> translated_value.
    """
    if not entries:
        return {}

    if not config.openai_api_key:
        logger.warning("No OpenAI API key configured, skipping LLM translation")
        return {}

    from openai import APITimeoutError, APIConnectionError

    client = OpenAI(
        base_url=config.openai_base_url or None,
        api_key=config.openai_api_key,
        timeout=config.llm_timeout,
        max_retries=0,  # We handle retries ourselves
    )

    translated: dict[str, str] = {}
    batch_size = config.llm_batch_size
    items = list(entries.items())
    total_batches = (len(items) + batch_size - 1) // batch_size
    max_retries = config.llm_max_retries

    for batch_idx in range(total_batches):
        start = batch_idx * batch_size
        end = min(start + batch_size, len(items))
        batch = dict(items[start:end])

        logger.info(
            "LLM translating batch %d/%d (%d entries)...",
            batch_idx + 1,
            total_batches,
            len(batch),
        )

        # Build context from dictionary
        dict_context = _build_dict_context(
            batch, dictionary or {}, max_entries=100
        )
        from string import Template
        system_prompt = Template(SYSTEM_PROMPT_TEMPLATE).safe_substitute(dict_context=dict_context)

        user_content = json.dumps(batch, indent=2, ensure_ascii=False)

        # Retry logic with exponential backoff
        for attempt in range(max_retries):
            try:
                response = client.chat.completions.create(
                    model=config.openai_model_id,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content},
                    ],
                    temperature=config.llm_temperature,
                )

                content = response.choices[0].message.content or ""
                # Try to extract JSON from response (handle markdown code blocks)
                content = content.strip()
                if content.startswith("```"):
                    # Remove markdown code block
                    lines = content.split("\n")
                    lines = lines[1:]  # remove opening ```json
                    if lines and lines[-1].strip() == "```":
                        lines = lines[:-1]
                    content = "\n".join(lines)

                result = json.loads(content)
                if isinstance(result, dict):
                    translated.update(result)
                    logger.info(
                        "  Batch %d: translated %d entries",
                        batch_idx + 1,
                        len(result),
                    )
                    break
                else:
                    logger.warning("  Batch %d: unexpected response type", batch_idx + 1)

            except (APITimeoutError, APIConnectionError) as e:
                backoff = min(2 ** (attempt + 1), 30)
                logger.warning(
                    "  Batch %d attempt %d/%d: timeout/connection error, "
                    "retrying in %ds: %s",
                    batch_idx + 1,
                    attempt + 1,
                    max_retries,
                    backoff,
                    e,
                )
                if attempt < max_retries - 1:
                    time.sleep(backoff)
            except json.JSONDecodeError as e:
                backoff = min(2 ** attempt, 10)
                logger.warning(
                    "  Batch %d attempt %d/%d: JSON parse error: %s",
                    batch_idx + 1,
                    attempt + 1,
                    max_retries,
                    e,
                )
                if attempt < max_retries - 1:
                    time.sleep(backoff)
            except Exception as e:
                backoff = min(2 ** (attempt + 1), 30)
                logger.warning(
                    "  Batch %d attempt %d/%d: API error: %s",
                    batch_idx + 1,
                    attempt + 1,
                    max_retries,
                    backoff,
                    e,
                )
                if attempt < max_retries - 1:
                    time.sleep(backoff)
        else:
            logger.error(
                "  Batch %d: all %d retries exhausted, skipping",
                batch_idx + 1,
                max_retries,
            )

        # Rate limiting: small delay between batches
        if batch_idx < total_batches - 1:
            time.sleep(1.0)

    logger.info("LLM translation complete: %d/%d entries translated", len(translated), len(entries))
    return translated


# ── Pipeline ───────────────────────────────────────────────────────


def _is_fully_translated(output_file: Path, entries: dict[str, str]) -> bool:
    """Check if an output file exists and contains translations for all entries."""
    if not output_file.exists():
        return False
    try:
        existing = json.loads(output_file.read_text(encoding="utf-8"))
        if not isinstance(existing, dict):
            return False
        # Check that all keys exist and values differ from English originals
        # (meaning they've been translated, not just copied)
        for key, en_value in entries.items():
            if key not in existing:
                return False
            # If value is same as English, it may not have been translated yet
            # But some entries legitimately keep their English value (numbers, names)
            # So we just check key presence
        return True
    except Exception:
        return False


def _load_partial_translations(output_file: Path) -> dict[str, str]:
    """Load existing partial translations from a previous run."""
    if not output_file.exists():
        return {}
    try:
        data = json.loads(output_file.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
        return {}
    except Exception:
        return {}


def translate_all(
    extracted_dir: Path,
    translated_dir: Path,
    config: AppConfig,
) -> None:
    """Run full translation pipeline: dictionary match, then LLM.

    Supports resumption: skips fully-translated files, resumes partially-
    translated files by only sending un-translated keys to the LLM.
    Saves progress after each file so interrupted runs can be continued.

    Processes all JSON files in extracted_dir subdirectories (mods/, kubejs/, ftbquests/).
    Writes translated files to translated_dir with same structure.
    """
    translated_dir.mkdir(parents=True, exist_ok=True)

    # Load dictionary
    dictionary = load_dictionary(config.work_dir)

    # Collect stats
    total_files = 0
    skipped_files = 0
    translated_files = 0

    # Process each extraction type
    for subdir_name in ("mods", "kubejs", "ftbquests"):
        subdir = extracted_dir / subdir_name
        if not subdir.is_dir():
            continue

        logger.info("Translating %s content...", subdir_name)
        out_subdir = translated_dir / subdir_name
        out_subdir.mkdir(parents=True, exist_ok=True)

        # Find all JSON files recursively
        json_files = sorted(subdir.rglob("*.json"))
        if not json_files:
            logger.info("No JSON files found in %s", subdir)
            continue

        for file_idx, json_file in enumerate(json_files):
            rel_path = json_file.relative_to(subdir)
            output_file = out_subdir / rel_path
            total_files += 1

            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning("Failed to read %s: %s", json_file, e)
                continue

            if not data or not isinstance(data, dict):
                continue

            # Skip files that only have non-translatable data
            entries = {k: v for k, v in data.items() if isinstance(v, str) and v.strip()}
            if not entries:
                continue

            # ── Resume check: skip fully translated files ──
            if _is_fully_translated(output_file, entries):
                skipped_files += 1
                logger.info(
                    "  [%d/%d] Skipping %s (already translated)",
                    file_idx + 1,
                    len(json_files),
                    rel_path,
                )
                continue

            logger.info(
                "  [%d/%d] Processing %s (%d entries)",
                file_idx + 1,
                len(json_files),
                rel_path,
                len(entries),
            )

            # ── Resume check: load partial translations ──
            existing_translations = _load_partial_translations(output_file)

            # Phase 1: Dictionary matching
            dict_translated, remaining = translate_with_dictionary(entries, dictionary)

            # Remove entries that were already translated in a previous run
            already_done: dict[str, str] = {}
            still_remaining: dict[str, str] = {}
            for key, value in remaining.items():
                if key in existing_translations and existing_translations[key] != entries.get(key):
                    # This key was translated in a previous run, reuse it
                    already_done[key] = existing_translations[key]
                else:
                    still_remaining[key] = value

            if already_done:
                logger.info(
                    "  Resumed %d entries from previous run, %d still need LLM",
                    len(already_done),
                    len(still_remaining),
                )

            # Phase 2: LLM translation for remaining
            llm_translated = {}
            if still_remaining:
                try:
                    llm_translated = translate_with_llm(still_remaining, config, dictionary)
                except KeyboardInterrupt:
                    # Save partial progress before exiting
                    logger.info("  Interrupted! Saving partial progress...")
                    partial: dict[str, str] = {}
                    for key in data:
                        if key in dict_translated:
                            partial[key] = dict_translated[key]
                        elif key in already_done:
                            partial[key] = already_done[key]
                        elif key in llm_translated:
                            partial[key] = llm_translated[key]
                        else:
                            partial[key] = data[key]
                    output_file.parent.mkdir(parents=True, exist_ok=True)
                    output_file.write_text(
                        json.dumps(partial, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8",
                    )
                    logger.info("  Partial progress saved to: %s", output_file)
                    raise

            # Merge results
            final: dict[str, str] = {}
            for key in data:
                if key in dict_translated:
                    final[key] = dict_translated[key]
                elif key in already_done:
                    final[key] = already_done[key]
                elif key in llm_translated:
                    final[key] = llm_translated[key]
                else:
                    # Keep original value if untranslated
                    final[key] = data[key]

            # Write translated file (atomic save point)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text(
                json.dumps(final, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

            translated_count = len(dict_translated) + len(already_done) + len(llm_translated)
            translated_files += 1
            logger.info(
                "  Translated %d/%d entries (dict: %d, resumed: %d, llm: %d)",
                translated_count,
                len(entries),
                len(dict_translated),
                len(already_done),
                len(llm_translated),
            )

    logger.info(
        "Translation complete: %d files processed, %d skipped (already done), %d newly translated",
        total_files,
        skipped_files,
        translated_files,
    )

