"""Download and install a CurseForge modpack by its slug."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, asdict
from pathlib import Path

from curseforge_dl.api import CurseForgeAPI
from curseforge_dl.installer import ModpackInstaller
from curseforge_dl.models import SECTION_MODPACK

from .config import AppConfig

logger = logging.getLogger(__name__)


@dataclass
class ModpackInfo:
    """Metadata about the downloaded modpack."""

    name: str
    version: str
    slug: str
    file_id: int
    file_name: str
    mc_version: str
    install_dir: str  # absolute path string

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(asdict(self), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path) -> ModpackInfo | None:
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls(**data)
        except Exception:
            return None


async def _download_and_install(config: AppConfig) -> ModpackInfo:
    """Async implementation of download and install."""
    work_dir = config.work_dir
    install_dir = work_dir / "instance"
    download_dir = work_dir / "downloads"
    download_dir.mkdir(parents=True, exist_ok=True)
    install_dir.mkdir(parents=True, exist_ok=True)

    async with CurseForgeAPI(api_key=config.curseforge_api_key) as api:
        installer = ModpackInstaller(api)

        # Download latest zip (also looks up by slug internally)
        logger.info("Downloading modpack: %s", config.slug)
        zip_path, addon, addon_file = await installer.download_modpack_by_slug(
            config.slug, output_dir=download_dir
        )
        logger.info("Downloaded: %s (id=%d)", addon.name, addon.id)

        # Parse manifest for version info
        manifest = ModpackInstaller.parse_modpack_info(zip_path)
        mc_version = manifest.minecraft.version

        # Install (extract overrides + download mods)
        logger.info("Installing modpack to: %s", install_dir)
        await installer.install(zip_path, install_dir)
        logger.info("Installation complete!")

    info = ModpackInfo(
        name=addon.name,
        version=manifest.version,
        slug=config.slug,
        file_id=addon_file.id,
        file_name=addon_file.file_name,
        mc_version=mc_version,
        install_dir=str(install_dir),
    )

    return info


def download_and_install(config: AppConfig) -> ModpackInfo:
    """Download and install modpack. Returns ModpackInfo."""
    return asyncio.run(_download_and_install(config))


async def check_for_update(config: AppConfig) -> int | None:
    """Check CurseForge for the latest file ID. Returns file_id or None."""
    async with CurseForgeAPI(api_key=config.curseforge_api_key) as api:
        addon = await api.get_mod_by_slug(config.slug, class_id=SECTION_MODPACK)
        if addon is None:
            return None
        latest = ModpackInstaller._select_latest_file(addon)
        if latest is None:
            return None
        return latest.id
