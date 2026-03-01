"""Extract translatable strings from an installed modpack."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
import re

logger = logging.getLogger(__name__)


@dataclass
class ExtractionResults:
    """Summary of what was extracted."""

    mods_keys: int = 0
    kubejs_keys: int = 0
    ftbquests_keys: int = 0
    has_kubejs: bool = False
    has_ftbquests: bool = False


def extract_mods(install_dir: Path, output_dir: Path) -> int:
    """Extract translatable strings from mod jars."""
    from mods_string_extractor.extractor import extract_mods as _extract_mods

    mods_dir = install_dir / "mods"
    if not mods_dir.is_dir():
        logger.warning("No mods/ directory found at %s", mods_dir)
        return 0

    mods_output = output_dir / "mods"
    mods_output.mkdir(parents=True, exist_ok=True)

    logger.info("Extracting strings from mods in: %s", mods_dir)
    results = _extract_mods(mods_dir, mods_output)

    total = sum(r.total_keys for r in results)
    logger.info(
        "Mods extraction complete: %d mods, %d keys",
        len(results),
        total,
    )
    return total


def extract_kubejs(install_dir: Path, output_dir: Path, config) -> int:
    """Extract translatable strings from KubeJS scripts."""
    from kubejs_string_extractor.extractor import extract_from_directory
    from kubejs_string_extractor.keygen import generate_keys
    from kubejs_string_extractor.rewriter import rewrite_directory
    from kubejs_string_extractor.writer import write_lang_json

    kubejs_dir = install_dir / "kubejs"
    if not kubejs_dir.is_dir():
        logger.info("No kubejs/ directory found, skipping KubeJS extraction")
        return 0

    # Check if any script directories exist
    has_scripts = any(
        (kubejs_dir / d).is_dir()
        for d in ("client_scripts", "server_scripts", "startup_scripts")
    )
    if not has_scripts:
        logger.info("No KubeJS script directories found, skipping")
        return 0

    logger.info("Extracting strings from KubeJS scripts in: %s", kubejs_dir)
    result = extract_from_directory(kubejs_dir)

    # Generate translation keys from scraped JS strings
    translations = {}
    if result.strings:
        translations = generate_keys(result.strings, namespace="kubejs")
        
    if result.premapped_keys:
        logger.info("Found %d context-mapped keys (e.g. displayName without Text.translate)", len(result.premapped_keys))
        translations.update(result.premapped_keys)
        
    # [NEW] Code LLM Semantic Analyzer Integration
    # Since complex dynamic registries like `event.create(\`${id}_mechanism\`)` inside loops
    # evade regex, we run a fallback semantic analysis on all scripts containing backticked `.create`.
    from modpack_localization_auto.kubejs_analyzer import analyze_kubejs_script_for_dynamic_keys
    
    analyzed_keys_count = 0
    create_template_re = re.compile(r"event\.create\(\s*`.+?`\s*\)")
    
    for script_file in kubejs_dir.rglob("*.js"):
        content = script_file.read_text(encoding="utf-8")
        if create_template_re.search(content):
            logger.info("Detected template literal registry in %s, sending to Code LLM...", script_file.name)
            ai_keys = analyze_kubejs_script_for_dynamic_keys(content, config)
            if ai_keys:
                translations.update(ai_keys)
                analyzed_keys_count += len(ai_keys)

    if analyzed_keys_count > 0:
        logger.info("Code LLM generated %d total dynamic registry keys!", analyzed_keys_count)

    # and modpack authors sometimes bundle manual hardcoded lang files there too.
    # We must extract these and merge them so they get translated.
    assets_dir = kubejs_dir / "assets"
    asset_keys_count = 0
    if assets_dir.is_dir():
        import json
        for lang_file in assets_dir.rglob("lang/en_us.json"):
            try:
                data = json.loads(lang_file.read_text(encoding="utf-8"))
                for k, v in data.items():
                    if isinstance(v, str):
                        translations[k] = v
                        asset_keys_count += 1
            except Exception as e:
                logger.warning("Failed to read KubeJS asset lang file %s: %s", lang_file, e)
                
    if not translations:
        logger.info("No translatable KubeJS strings found anywhere")
        return 0

    logger.info("Generated %d unique KubeJS keys (and %d from assets/lang)", len(translations) - asset_keys_count, asset_keys_count)

    # Write en_us.json for the extracted strings
    kubejs_output = output_dir / "kubejs"
    kubejs_output.mkdir(parents=True, exist_ok=True)
    write_lang_json(translations, kubejs_output, namespace="kubejs_string_extractor")

    # Write en_us.json for the extracted strings
    kubejs_output = output_dir / "kubejs"
    kubejs_output.mkdir(parents=True, exist_ok=True)
    write_lang_json(translations, kubejs_output, namespace="kubejs_string_extractor")

    return len(translations)


def extract_ftbquests(install_dir: Path, output_dir: Path, modpack_name: str) -> int:
    """Extract translatable strings from FTB Quests."""
    # FTB Quests can be in several locations
    quest_paths = [
        install_dir / "config" / "ftbquests" / "quests",
        install_dir / "ftbquests" / "quests",
        install_dir / "config" / "ftbquests",
    ]

    quests_dir = None
    for p in quest_paths:
        if p.is_dir():
            quests_dir = p
            break

    if quests_dir is None:
        logger.info("No FTB Quests directory found, skipping")
        return 0

    ftbq_output = output_dir / "ftbquests"
    ftbq_output.mkdir(parents=True, exist_ok=True)

    # Check format: new (1.20+) has lang/ subdirectory
    lang_dir = quests_dir / "lang"
    lang_file = quests_dir / "lang" / "en_us.snbt"
    
    if lang_dir.is_dir() and (lang_dir / "en_us").is_dir():
        # New format (split): split SNBT lang files into JSON
        from ftb_quest_localizer.splitter import split_lang_files

        logger.info("Detected new-format FTB Quests (1.20+) with lang/ directory")
        results = split_lang_files(quests_dir, ftbq_output)
        total = sum(results.values()) if results else 0
        logger.info("FTB Quests extraction (new format split): %d entries", total)
        return total
    elif lang_file.is_file():
        # New format (single file): export en_us.snbt to en_us.json
        from ftb_quest_localizer.splitter import extract_single_file_lang

        logger.info("Detected new-format FTB Quests (1.20+) single-file export")
        total = extract_single_file_lang(lang_file, ftbq_output)
        logger.info("FTB Quests extraction (new format single-file): %d entries", total)
        return total
    else:
        # Old format: extract inline strings from chapter files
        from ftb_quest_localizer.extractor import extract_quest_strings

        logger.info("Detected old-format FTB Quests (pre-1.20)")
        results = extract_quest_strings(quests_dir, ftbq_output, modpack_name)
        total = sum(results.values()) if results else 0
        logger.info("FTB Quests extraction (old format): %d entries", total)
        return total


def extract_all(install_dir: Path, work_dir: Path, modpack_name: str, config) -> ExtractionResults:
    """Run all extractors on an installed modpack."""
    extracted_dir = work_dir / "extracted"
    extracted_dir.mkdir(parents=True, exist_ok=True)

    results = ExtractionResults()

    # 1. Mods
    results.mods_keys = extract_mods(install_dir, extracted_dir)

    # 2. KubeJS
    results.kubejs_keys = extract_kubejs(install_dir, extracted_dir, config)
    results.has_kubejs = results.kubejs_keys > 0

    # 3. FTB Quests
    results.ftbquests_keys = extract_ftbquests(install_dir, extracted_dir, modpack_name)
    results.has_ftbquests = results.ftbquests_keys > 0

    logger.info(
        "Extraction summary — Mods: %d keys, KubeJS: %d keys, FTB Quests: %d keys",
        results.mods_keys,
        results.kubejs_keys,
        results.ftbquests_keys,
    )

    return results
