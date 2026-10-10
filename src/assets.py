from __future__ import annotations

"""Resolve PoE2 item/gem artwork without bundling GGG art in the project."""

import json
import re
import threading
from pathlib import Path
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from . import VERSION, storage

BASE_ITEMS_URL = "https://repoe-fork.github.io/poe2/base_items.min.json"
SKILL_GEMS_URL = "https://repoe-fork.github.io/poe2/skill_gems.min.json"
CACHE_DIR = storage.DATA / "assets"
BASE_CACHE = CACHE_DIR / "base_items.min.json"
GEM_CACHE = CACHE_DIR / "skill_gems.min.json"
# Backward-compatible name used by older tests/integrations.
CACHE = BASE_CACHE
USER_AGENT = f"PoE2-Synergy-Finder/{VERSION} (local visual asset resolver)"
_LOCK = threading.Lock()
_WS = re.compile(r"\s+")
_MAX_DATASET_BYTES = 40 * 1024 * 1024


def _key(value: str) -> str:
    return _WS.sub(" ", str(value or "")).strip().casefold()


def _load_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _download_json(url: str, cache: Path, label: str) -> dict:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urlopen(request, timeout=12) as response:
            raw = response.read(_MAX_DATASET_BYTES + 1)
    except (URLError, TimeoutError) as exc:
        raise RuntimeError(f"Não foi possível baixar o índice visual {label} do RePoE: {exc}.") from exc
    if len(raw) > _MAX_DATASET_BYTES:
        raise RuntimeError(f"O índice visual {label} do RePoE excedeu o limite local de segurança.")
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict) or not data:
        raise RuntimeError(f"O índice visual {label} do RePoE tem formato inesperado.")
    cache.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache.with_suffix(cache.suffix + ".tmp")
    tmp.write_bytes(raw)
    tmp.replace(cache)
    return data


def _snapshot_candidates(filename: str) -> list[Path]:
    root = storage.DATA / "raw" / "snapshots"
    if not root.exists():
        return []
    return sorted(root.glob(f"*/{filename}"), key=lambda p: p.stat().st_mtime, reverse=True)


def _dataset(cache: Path, filename: str, url: str, label: str) -> dict:
    data = _load_json(cache)
    if data:
        return data
    # Reuse a RePoE snapshot already downloaded by the Finder. This makes the
    # visual resolver survive a project-folder move as long as data/ moved too.
    for path in _snapshot_candidates(filename):
        data = _load_json(path)
        if data:
            return data
    with _LOCK:
        data = _load_json(cache)
        return data or _download_json(url, cache, label)


def base_items() -> dict:
    return _dataset(BASE_CACHE, "base_items.min.json", BASE_ITEMS_URL, "de itens")


def skill_gems() -> dict:
    return _dataset(GEM_CACHE, "skill_gems.min.json", SKILL_GEMS_URL, "de gems")


def _index(data: dict) -> dict[str, dict]:
    """Index base items by displayed name."""
    result: dict[str, dict] = {}
    for metadata_id, row in data.items():
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or row.get("display_name") or "").strip()
        visual = row.get("visual_identity") if isinstance(row.get("visual_identity"), dict) else {}
        dds = str(visual.get("dds_file") or "").strip()
        if not name or not dds:
            continue
        candidate = {
            "name": name,
            "metadata_id": str(metadata_id),
            "dds": dds,
            "width": int(row.get("inventory_width") or 1),
            "height": int(row.get("inventory_height") or 1),
            "item_class": str(row.get("item_class") or ""),
            "release_state": str(row.get("release_state") or ""),
            "asset_kind": "item",
        }
        k = _key(name)
        old = result.get(k)
        if old is None or (old.get("release_state") != "released" and candidate["release_state"] == "released"):
            result[k] = candidate
    return result


def _gem_index(data: dict) -> dict[str, dict]:
    """Index skill/support gems by their in-game display name.

    RePoE exposes the real skill icon as ``icon_dds_file`` in skill_gems;
    resolving gems only through base_items loses many active/support icons.
    """
    result: dict[str, dict] = {}
    for metadata_id, row in data.items():
        if not isinstance(row, dict):
            continue
        base = row.get("base_item") if isinstance(row.get("base_item"), dict) else {}
        name = str(base.get("display_name") or row.get("display_name") or row.get("name") or "").strip()
        dds = str(row.get("icon_dds_file") or "").strip()
        if not name or not dds:
            continue
        release_state = str(base.get("release_state") or row.get("release_state") or "")
        candidate = {
            "name": name,
            "metadata_id": str(metadata_id),
            "dds": dds,
            "width": 1,
            "height": 1,
            "item_class": "Gem",
            "release_state": release_state,
            "asset_kind": "gem",
            "gem_type": str(row.get("gem_type") or ""),
            "color": str(row.get("color") or ""),
        }
        k = _key(name)
        old = result.get(k)
        if old is None or (old.get("release_state") != "released" and candidate["release_state"] == "released"):
            result[k] = candidate
    return result


def image_url(dds: str) -> str:
    clean = str(dds or "").replace("\\", "/").lstrip("/")
    if not clean.startswith("Art/") or not clean.lower().endswith(".dds"):
        return ""
    return "https://image.ggpk.exposed/poe2/" + quote(clean, safe="/") + "?format=png"


def resolve_names(names: list[str]) -> dict:
    names = [str(x).strip() for x in names if str(x).strip()][:200]
    if not names:
        return {"assets": {}, "source": "RePoE base_items + skill_gems + ggpk.exposed"}

    # Load independently. If the gem dataset cannot be refreshed but the item
    # dataset is already cached, equipment artwork should still render.
    item_error = gem_error = ""
    try:
        item_idx = _index(base_items())
    except Exception as exc:
        item_idx = {}
        item_error = str(exc)
    try:
        gem_idx = _gem_index(skill_gems())
    except Exception as exc:
        gem_idx = {}
        gem_error = str(exc)

    if not item_idx and not gem_idx:
        raise RuntimeError(gem_error or item_error or "Nenhum índice visual pôde ser carregado.")

    out = {}
    for name in names:
        # Prefer the dedicated gem icon dataset when a name exists in both.
        row = gem_idx.get(_key(name)) or item_idx.get(_key(name))
        if row:
            out[name] = {**row, "url": image_url(row["dds"])}

    warnings = [x for x in (item_error, gem_error) if x]
    return {
        "assets": out,
        "resolved": len(out),
        "requested": len(names),
        "source": "RePoE base_items + skill_gems metadata · artwork served by ggpk.exposed",
        "warning": " | ".join(warnings),
    }
