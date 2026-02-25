"""Main CLI entry point — orchestrates the full localization pipeline."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

from .config import AppConfig, load_config
from .downloader import ModpackInfo, download_and_install, check_for_update
from .extractor import extract_all
from .translator import translate_all
from .packager import package_all

logger = logging.getLogger(__name__)


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def run_pipeline(config: AppConfig) -> None:
    """Execute the full localization pipeline."""
    # Check if we already have this version
    existing = ModpackInfo.load(config.version_file)
    if existing:
        logger.info(
            "Existing localization found: %s v%s (file_id=%d)",
            existing.name,
            existing.version,
            existing.file_id,
        )
        # Check for updates
        logger.info("Checking for updates on CurseForge...")
        latest_id = asyncio.run(check_for_update(config))
        if latest_id and latest_id == existing.file_id:
            logger.info("Already up to date. No work needed.")
            return
        elif latest_id:
            logger.info(
                "Update found! Latest file_id=%d (current=%d)",
                latest_id,
                existing.file_id,
            )
        else:
            logger.warning("Could not check for updates, proceeding anyway")

    # ── Step 1: Download & Install ────────────────────────────────
    logger.info("=" * 60)
    logger.info("STEP 1: Download & Install modpack '%s'", config.slug)
    logger.info("=" * 60)

    modpack_info = download_and_install(config)
    install_dir = Path(modpack_info.install_dir)

    logger.info(
        "Installed: %s v%s (MC %s, file_id=%d)",
        modpack_info.name,
        modpack_info.version,
        modpack_info.mc_version,
        modpack_info.file_id,
    )

    # ── Step 2: Extract ───────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("STEP 2: Extract translatable content")
    logger.info("=" * 60)

    extraction = extract_all(install_dir, config.work_dir, modpack_info.name)

    total_keys = extraction.mods_keys + extraction.kubejs_keys + extraction.ftbquests_keys
    if total_keys == 0:
        logger.warning("No translatable content found. Exiting.")
        return

    # ── Step 3: Translate ─────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("STEP 3: Translate (%d total keys)", total_keys)
    logger.info("=" * 60)

    extracted_dir = config.work_dir / "extracted"
    translated_dir = config.work_dir / "translated"
    translate_all(extracted_dir, translated_dir, config)

    # ── Step 4: Package ───────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("STEP 4: Package outputs")
    logger.info("=" * 60)

    package_all(config.work_dir, install_dir, config.output_dir, config)

    # ── Step 5: Save version info ─────────────────────────────────
    modpack_info.save(config.version_file)
    logger.info("Version info saved to: %s", config.version_file)

    # Done!
    logger.info("=" * 60)
    logger.info("DONE! Output files in: %s", config.output_dir)
    logger.info("=" * 60)
    for f in sorted(config.output_dir.iterdir()):
        if f.is_file():
            size_kb = f.stat().st_size / 1024
            logger.info("  %s (%.1f KB)", f.name, size_kb)


def main() -> None:
    """CLI entry point."""
    _setup_logging()

    # Allow passing config path as argument
    config_path = None
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        config_path = Path(sys.argv[1])

    try:
        config = load_config(config_path)
    except Exception as e:
        logger.error("Failed to load configuration: %s", e)
        sys.exit(1)

    logger.info("Modpack Localization Auto v0.1.0")
    logger.info("Slug: %s", config.slug)
    logger.info("Target lang: %s", config.target_lang)

    try:
        run_pipeline(config)
    except KeyboardInterrupt:
        logger.info("\nInterrupted by user.")
        sys.exit(130)
    except Exception as e:
        logger.error("Pipeline failed: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
