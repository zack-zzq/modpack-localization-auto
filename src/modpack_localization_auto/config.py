"""Load configuration from config.toml and .env."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_PROJECT_ROOT / ".env")

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[no-redef]


@dataclass
class AppConfig:
    """Application configuration."""

    # Modpack
    slugs: list[str] = field(default_factory=lambda: ["all-the-mods-10"])

    # Translation
    target_lang: str = "zh_cn"
    pack_format: int = 34
    llm_batch_size: int = 50
    llm_temperature: float = 0.3
    llm_timeout: float = 30000.0
    llm_max_retries: int = 30
    custom_terminology: dict[str, str] = field(default_factory=dict)

    # OpenAI-compatible LLM (from .env)
    openai_base_url: str = ""
    openai_api_key: str = ""
    openai_model_id: str = ""

    # CurseForge (from .env)
    curseforge_api_key: str = ""

    # GitHub / Dict repo (from .env)
    github_token: str = ""
    dict_repo: str = "zack-zzq/i18n-Dict-Merged"

    # Paths
    project_root: Path = field(default_factory=lambda: _PROJECT_ROOT)

    # ── Per-slug path helpers (set slug before using) ──
    _current_slug: str = ""

    @property
    def slug(self) -> str:
        return self._current_slug

    @slug.setter
    def slug(self, value: str) -> None:
        self._current_slug = value

    @property
    def work_dir(self) -> Path:
        return self.project_root / "work" / self._current_slug

    @property
    def output_dir(self) -> Path:
        return self.project_root / "output" / self._current_slug

    @property
    def version_file(self) -> Path:
        return self.output_dir / "version.json"


def load_config(config_path: Path | None = None) -> AppConfig:
    """Load configuration from config.toml and environment variables."""
    if config_path is None:
        config_path = _PROJECT_ROOT / "config.toml"

    # Read TOML
    toml_data: dict = {}
    if config_path.exists():
        with open(config_path, "rb") as f:
            toml_data = tomllib.load(f)

    modpack = toml_data.get("modpack", {})
    translation = toml_data.get("translation", {})

    # Support both "slug" (single) and "slugs" (list) for backward compat
    slugs = modpack.get("slugs", [])
    if not slugs:
        single = modpack.get("slug", "all-the-mods-10")
        slugs = [single]

    return AppConfig(
        slugs=slugs,
        target_lang=translation.get("target_lang", "zh_cn"),
        pack_format=translation.get("pack_format", 34),
        llm_batch_size=translation.get("llm_batch_size", 50),
        llm_temperature=translation.get("llm_temperature", 0.3),
        llm_timeout=translation.get("llm_timeout", 30000.0),
        llm_max_retries=translation.get("llm_max_retries", 30),
        custom_terminology=translation.get("terminology", {}),
        openai_base_url=os.environ.get("OPENAI_BASE_URL", ""),
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        openai_model_id=os.environ.get("OPENAI_MODEL_ID", ""),
        curseforge_api_key=os.environ.get("CURSEFORGE_API_KEY", ""),
        github_token=os.environ.get("GITHUB_TOKEN", ""),
        dict_repo=toml_data.get("upload", {}).get("dict_repo", "zack-zzq/i18n-Dict-Merged"),
    )
