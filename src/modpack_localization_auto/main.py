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
from .uploader import upload_to_dict_repo

logger = logging.getLogger(__name__)


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def run_pipeline(config: AppConfig) -> None:
    """Execute the full localization pipeline with resumption support."""
    # Check if we already have a FINISHED localization for this version
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
    # Check if we already have a working install (from an interrupted run)
    install_checkpoint = config.work_dir / "modpack_info.json"
    modpack_info = ModpackInfo.load(install_checkpoint)

    if modpack_info and Path(modpack_info.install_dir).exists():
        install_dir = Path(modpack_info.install_dir)
        logger.info("=" * 60)
        logger.info("STEP 1: Resuming from existing install")
        logger.info(
            "  %s v%s (MC %s, file_id=%d)",
            modpack_info.name,
            modpack_info.version,
            modpack_info.mc_version,
            modpack_info.file_id,
        )
        logger.info("=" * 60)
    else:
        logger.info("=" * 60)
        logger.info("STEP 1: Download & Install modpack '%s'", config.slug)
        logger.info("=" * 60)

        modpack_info = download_and_install(config)
        install_dir = Path(modpack_info.install_dir)

        # Save checkpoint immediately so we can resume if interrupted later
        modpack_info.save(install_checkpoint)
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

    # ── Step 3: Translate (supports resumption) ───────────────────
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

    # ── Step 5: Upload to Dict ────────────────────────────────────
    logger.info("=" * 60)
    logger.info("STEP 5: Upload translations to %s", config.dict_repo)
    logger.info("=" * 60)

    upload_to_dict_repo(
        extracted_dir, translated_dir,
        mc_version=modpack_info.mc_version,
        config=config,
    )

    # ── Step 6: Save version info ─────────────────────────────────
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

    # Parse arguments
    import argparse

    parser = argparse.ArgumentParser(
        prog="modpack-localize",
        description="Modpack Localization Auto",
    )
    parser.add_argument("config", nargs="?", default=None, help="Path to config.toml")
    parser.add_argument("--slug", dest="only_slug", default=None, help="Only process this slug")
    args = parser.parse_args()

    config_path = Path(args.config) if args.config else None

    try:
        config = load_config(config_path)
    except Exception as e:
        logger.error("Failed to load configuration: %s", e)
        sys.exit(1)

    # Determine which slugs to process
    slugs = config.slugs
    if args.only_slug:
        if args.only_slug not in slugs:
            logger.warning("Slug '%s' not in config, running anyway", args.only_slug)
        slugs = [args.only_slug]

    logger.info("Modpack Localization Auto v0.1.0")
    logger.info("Slugs: %s", ", ".join(slugs))
    logger.info("Target lang: %s", config.target_lang)

    failed: list[str] = []
    for i, slug in enumerate(slugs):
        config.slug = slug
        logger.info("")
        logger.info("━" * 60)
        logger.info("Processing modpack %d/%d: %s", i + 1, len(slugs), slug)
        logger.info("━" * 60)
        try:
            run_pipeline(config)
        except KeyboardInterrupt:
            logger.info("\nInterrupted by user.")
            sys.exit(130)
        except Exception as e:
            logger.error("Pipeline failed for '%s': %s", slug, e, exc_info=True)
            failed.append(slug)

    if failed:
        logger.error("Failed slugs: %s", ", ".join(failed))
        sys.exit(1)


if __name__ == "__main__":
    main()
