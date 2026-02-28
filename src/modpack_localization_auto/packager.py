"""Package translated content into resource packs and override files."""

from __future__ import annotations

import json
import logging
import shutil
import zipfile
from pathlib import Path

from .config import AppConfig

logger = logging.getLogger(__name__)


def _copy_tree(src: Path, dst: Path) -> int:
    """Recursively copy directory tree, return file count."""
    count = 0
    for item in src.rglob("*"):
        if item.is_file():
            rel = item.relative_to(src)
            target = dst / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)
            count += 1
    return count


def _create_pack_mcmeta(pack_format: int, description: str) -> str:
    """Generate pack.mcmeta JSON content."""
    meta = {
        "pack": {
            "pack_format": pack_format,
            "description": description,
        }
    }
    return json.dumps(meta, indent=2, ensure_ascii=False) + "\n"


def build_resource_pack(
    translated_dir: Path,
    misc_packs_dir: Path,
    output_zip: Path,
    config: AppConfig,
) -> int:
    """Build the resource pack zip from translated mods + misc packs.

    Args:
        translated_dir: Directory with translated JSON files.
        misc_packs_dir: Path to libs/misc-localization-packs.
        output_zip: Output zip file path.
        config: App configuration.

    Returns:
        Number of files packed.
    """
    output_zip.parent.mkdir(parents=True, exist_ok=True)
    file_count = 0

    with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        # pack.mcmeta
        description = f"{config.slug} 自动本地化资源包"
        zf.writestr(
            "pack.mcmeta",
            _create_pack_mcmeta(config.pack_format, description),
        )

        pack_png = config.project_root / "resources" / "pack.png"
        if pack_png.is_file():
            zf.write(pack_png, "pack.png")

        # 1. Mods translations -> assets/<modid>/lang/zh_cn.json
        mods_dir = translated_dir / "mods"
        if mods_dir.is_dir():
            for modid_dir in sorted(mods_dir.iterdir()):
                if not modid_dir.is_dir():
                    continue
                modid = modid_dir.name
                # ftbquests is handled separately (merged with quest lang)
                if modid == "ftbquests":
                    continue
                lang_file = modid_dir / "en_us.json"
                if not lang_file.exists():
                    continue

                try:
                    content = lang_file.read_text(encoding="utf-8")
                    data = json.loads(content)
                except Exception:
                    continue

                if not data:
                    continue

                pack_path = f"assets/{modid}/lang/{config.target_lang}.json"
                zf.writestr(
                    pack_path,
                    json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                )
                file_count += 1
                logger.info("  Packed mods: %s (%d keys)", modid, len(data))

                # Handle Patchouli Reconstruction
                patchouli_file = modid_dir / "patchouli.json"
                mods_jar_dir = config.work_dir / "instance" / "mods"
                if patchouli_file.exists() and mods_jar_dir.exists():
                    try:
                        patchouli_data = json.loads(patchouli_file.read_text(encoding="utf-8"))
                        file_map: dict[str, dict[str, str]] = {}
                        for full_key, translation in patchouli_data.items():
                            if "::" in full_key:
                                file_path, json_path = full_key.split("::", 1)
                                file_map.setdefault(file_path, {})[json_path] = translation
                        
                        if file_map:
                            from mods_string_extractor.packer import _get_jar_for_modid, _replace_patchouli_strings
                            jar_path = _get_jar_for_modid(mods_jar_dir, modid)
                            if jar_path:
                                with zipfile.ZipFile(jar_path, "r") as jar:
                                    packed_patchouli = 0
                                    for en_us_path, file_translations in file_map.items():
                                        try:
                                            ast = json.loads(jar.read(en_us_path))
                                            
                                            from mods_string_extractor.extractor import _extract_patchouli_strings
                                            parts = en_us_path.split("/")
                                            en_us_idx = parts.index("en_us")
                                            
                                            zh_cn_parts = parts.copy()
                                            zh_cn_parts[en_us_idx] = config.target_lang
                                            zh_cn_path_in_jar = "/".join(zh_cn_parts)
                                            
                                            merged_translations = {}
                                            if zh_cn_path_in_jar in jar.namelist():
                                                zh_ast = json.loads(jar.read(zh_cn_path_in_jar))
                                                merged_translations = _extract_patchouli_strings(zh_ast)
                                            
                                            merged_translations.update(file_translations)
                                            
                                            localized_ast = _replace_patchouli_strings(ast, merged_translations)
                                            
                                            parts[en_us_idx] = config.target_lang
                                            if parts[0] == "data":
                                                parts[0] = "assets"
                                            target_path = "/".join(parts)
                                            zf.writestr(
                                                target_path,
                                                json.dumps(localized_ast, indent=2, ensure_ascii=False) + "\n",
                                            )
                                            packed_patchouli += 1
                                        except Exception as e:
                                            logger.warning("Failed to localize %s: %s", en_us_path, e)
                                    file_count += packed_patchouli
                                    logger.info("  Packed %d patchouli files for %s", packed_patchouli, modid)
                    except json.JSONDecodeError as e:
                        logger.warning("Invalid JSON in patchouli %s: %s, skipping", patchouli_file, e)

        # 2. KubeJS lang -> assets/kubejs_string_extractor/lang/zh_cn.json
        kubejs_dir = translated_dir / "kubejs"
        if kubejs_dir.is_dir():
            kubejs_lang = kubejs_dir / "assets" / "kubejs_string_extractor" / "lang" / "en_us.json"
            if kubejs_lang.exists():
                try:
                    content = kubejs_lang.read_text(encoding="utf-8")
                    data = json.loads(content)
                    if data:
                        pack_path = f"assets/kubejs_string_extractor/lang/{config.target_lang}.json"
                        zf.writestr(
                            pack_path,
                            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                        )
                        file_count += 1
                        logger.info("  Packed KubeJS lang: %d keys", len(data))
                except Exception as e:
                    logger.warning("  Failed to pack KubeJS lang: %s", e)

        # Detect FTB Quests single-file format
        ftbq_install_dir = None
        install_dir = config.work_dir / "instance"
        for p in [
            install_dir / "config" / "ftbquests" / "quests",
            install_dir / "ftbquests" / "quests",
            install_dir / "config" / "ftbquests",
        ]:
            if p.is_dir():
                ftbq_install_dir = p
                break
                
        is_single_file_format = False
        if ftbq_install_dir:
            lang_file = ftbq_install_dir / "lang" / "en_us.snbt"
            lang_dir = ftbq_install_dir / "lang" / "en_us"
            if lang_file.is_file() and not lang_dir.is_dir():
                is_single_file_format = True

        # 3. FTB Quests lang -> assets/ftbquests/lang/zh_cn.json
        # Merges mod UI strings + quest content translations into one file
        ftbq_merged: dict[str, str] = {}
        # a) Mod ftbquests lang (UI strings like "block.ftbquests.*")
        ftbq_mod_lang = translated_dir / "mods" / "ftbquests" / "en_us.json"
        if ftbq_mod_lang.exists():
            try:
                ftbq_merged.update(json.loads(ftbq_mod_lang.read_text(encoding="utf-8")))
            except Exception:
                pass
        # b) Quest content lang (extracted quest strings)
        if not is_single_file_format:
            ftbq_quest_lang = translated_dir / "ftbquests" / "en_us.json"
            if ftbq_quest_lang.exists():
                try:
                    ftbq_merged.update(json.loads(ftbq_quest_lang.read_text(encoding="utf-8")))
                except Exception:
                    pass
        if ftbq_merged:
            pack_path = f"assets/ftbquests/lang/{config.target_lang}.json"
            zf.writestr(
                pack_path,
                json.dumps(ftbq_merged, indent=2, ensure_ascii=False) + "\n",
            )
            file_count += 1
            has_quest_lang = not is_single_file_format and translated_dir.joinpath("ftbquests", "en_us.json").exists()
            logger.info("  Packed FTB Quests lang: %d keys (mod: %s, quests: %s)",
                        len(ftbq_merged),
                        "yes" if ftbq_mod_lang.exists() else "no",
                        "yes" if has_quest_lang else "skipped (single-file override)")

        # 3. misc-localization-packs assets
        misc_assets = misc_packs_dir / "assets"
        if misc_assets.is_dir():
            for item in misc_assets.rglob("*"):
                if item.is_file():
                    rel = item.relative_to(misc_packs_dir)
                    # Use forward slashes for zip paths
                    zip_path = str(rel).replace("\\", "/")
                    zf.write(item, zip_path)
                    file_count += 1
            logger.info("  Packed misc-localization-packs assets")

    logger.info("Resource pack created: %s (%d files)", output_zip.name, file_count)
    return file_count


def build_overrides_pack(
    translated_dir: Path,
    install_dir: Path,
    output_zip: Path,
    config: AppConfig,
) -> int:
    """Build the overrides zip for files that must overwrite originals.

    This includes KubeJS rewritten scripts and FTB Quests translated SNBT files.

    Args:
        translated_dir: Directory with translated files.
        install_dir: Modpack install directory.
        output_zip: Output zip file path.
        config: App configuration.

    Returns:
        Number of files packed.
    """
    output_zip.parent.mkdir(parents=True, exist_ok=True)
    file_count = 0

    with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        # Detect FTB Quests format from install dir
        ftbq_install_dir = None
        for p in [
            install_dir / "config" / "ftbquests" / "quests",
            install_dir / "ftbquests" / "quests",
            install_dir / "config" / "ftbquests",
        ]:
            if p.is_dir():
                ftbq_install_dir = p
                break
                
        is_single_file_format = False
        if ftbq_install_dir:
            lang_file = ftbq_install_dir / "lang" / "en_us.snbt"
            lang_dir = ftbq_install_dir / "lang" / "en_us"
            if lang_file.is_file() and not lang_dir.is_dir():
                is_single_file_format = True

        # 1. FTB Quests: pack overrides
        extracted_dir = Path(str(translated_dir).replace("translated", "extracted"))
        ftbq_extracted = extracted_dir / "ftbquests"
        ftbq_translated = translated_dir / "ftbquests" / "en_us.json"
        
        if is_single_file_format and ftbq_translated.exists():
            # Single-file format: convert translated JSON directly to lang/zh_cn.snbt
            try:
                data = json.loads(ftbq_translated.read_text(encoding="utf-8"))
                # Write back as SNBT string
                lines = ["{"]
                for k, v in data.items():
                    k_esc = json.dumps(k, ensure_ascii=False)
                    v_esc = json.dumps(v, ensure_ascii=False)
                    lines.append(f"\t{k_esc}: {v_esc}")
                lines.append("}")
                snbt_content = "\n".join(lines) + "\n"
                
                zip_path = f"config/ftbquests/quests/lang/{config.target_lang}.snbt"
                zf.writestr(zip_path, snbt_content.encode("utf-8"))
                file_count += 1
                logger.info("  Packed FTB Quests lang override as single SNBT: %s", zip_path)
            except Exception as e:
                logger.warning("  Failed to pack single-file FTB Quests override: %s", e)
        elif ftbq_extracted.is_dir():
            # Old format: modified SNBT files replace originals at config/ftbquests/quests/
            for snbt_file in ftbq_extracted.rglob("*.snbt"):
                rel = snbt_file.relative_to(ftbq_extracted)
                zip_path = f"config/ftbquests/quests/{str(rel).replace(chr(92), '/')}"
                zf.write(snbt_file, zip_path)
                file_count += 1
            if file_count > 0 and not is_single_file_format:
                logger.info("  Packed FTB Quests SNBT overrides (%d files)", file_count)

        # 2. KubeJS rewritten scripts
        # The extractor rewrites JS files with Text.translatable() calls
        # They're saved in extracted/kubejs/{client_scripts,server_scripts,...}/
        kubejs_extracted = extracted_dir / "kubejs"
        if kubejs_extracted.is_dir():
            kubejs_count = 0
            script_dirs = ("client_scripts", "server_scripts", "startup_scripts")
            for script_dir_name in script_dirs:
                script_dir = kubejs_extracted / script_dir_name
                if not script_dir.is_dir():
                    continue
                for js_file in script_dir.rglob("*.js"):
                    rel = js_file.relative_to(kubejs_extracted)
                    zip_path = f"kubejs/{str(rel).replace(chr(92), '/')}"
                    zf.write(js_file, zip_path)
                    file_count += 1
                    kubejs_count += 1
            if kubejs_count > 0:
                logger.info("  Packed KubeJS script overrides (%d files)", kubejs_count)

    if file_count > 0:
        logger.info("Overrides pack created: %s (%d files)", output_zip.name, file_count)
    else:
        # Remove empty zip
        output_zip.unlink(missing_ok=True)
        logger.info("No override files to pack, skipping overrides zip")

    return file_count


def package_all(
    work_dir: Path,
    install_dir: Path,
    output_dir: Path,
    config: AppConfig,
) -> None:
    """Run the full packaging pipeline."""
    translated_dir = work_dir / "translated"
    misc_packs_dir = config.project_root / "libs" / "misc-localization-packs"

    output_dir.mkdir(parents=True, exist_ok=True)

    # Build resource pack
    rp_zip = output_dir / f"{config.slug}-localization-resourcepack.zip"
    logger.info("Building resource pack: %s", rp_zip.name)
    build_resource_pack(translated_dir, misc_packs_dir, rp_zip, config)

    # Build overrides pack
    overrides_zip = output_dir / f"{config.slug}-localization-overrides.zip"
    logger.info("Building overrides pack: %s", overrides_zip.name)
    build_overrides_pack(translated_dir, install_dir, overrides_zip, config)
