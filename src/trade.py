from __future__ import annotations

"""Small PoE2 trade helper used by the local build page.

The Finder does not keep credentials or scrape listings. It uses the same public
trade2 endpoints used by the official web client. Searches only happen after an
explicit click in the UI.
"""

from datetime import datetime, timezone
import json
import re
import threading
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from . import VERSION, storage

BASE = "https://www.pathofexile.com"
STATS_URL = BASE + "/api/trade2/data/stats"
CACHE = storage.DATA / "trade" / "stats-poe2.json"
CACHE_MAX_AGE_SECONDS = 24 * 60 * 60
USER_AGENT = f"PoE2-Synergy-Finder/{VERSION} (local build helper; public trade2 API)"
_LOCK = threading.Lock()

_NUM = re.compile(r"\d+(?:[.,]\d+)?")
_VALUE_NUM = re.compile(r"[+-]?\d+(?:[.,]\d+)?")
_MARKUP = re.compile(r"\[([^\[\]]+)\]")
_SPACES = re.compile(r"\s+")
_TRAILING_TAG = re.compile(r"\s*\((?:implicit|explicit|rune|enchant|crafted|fractured)\)\s*$", re.I)
_ROLL_RANGE = re.compile(r"(?<=\d)\(\s*([+-]?\d+(?:[.,]\d+)?)\s*-\s*([+-]?\d+(?:[.,]\d+)?)\s*\)")


def _plain(text: str) -> str:
    text = str(text or "")
    # PoB can render the current roll followed by its tier range, e.g.
    # ``+28(27-32) to maximum Mana``. Trade2 expects only the rendered value.
    text = _ROLL_RANGE.sub("", text)
    text = _MARKUP.sub(lambda m: m.group(1).split("|")[-1], text)
    return _SPACES.sub(" ", text.replace("\u00a0", " ")).strip()


def roll_ranges(text: str) -> list[dict]:
    out=[]
    for lo,hi in _ROLL_RANGE.findall(str(text or "")):
        def number(v):
            n=float(v.replace(",", "."))
            return int(n) if n.is_integer() else n
        try:out.append({"min":number(lo),"max":number(hi)})
        except ValueError:pass
    return out


def stat_pattern(text: str) -> str:
    """Normalize rendered item text to the shape used by the trade stat table."""
    text = _TRAILING_TAG.sub("", _plain(text))
    text = _NUM.sub("#", text)
    return text.casefold()


def numeric_values(text: str) -> list[float]:
    out = []
    for raw in _VALUE_NUM.findall(_plain(text)):
        try:
            value = float(raw.replace(",", "."))
            out.append(int(value) if value.is_integer() else value)
        except ValueError:
            pass
    return out


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load_cache() -> dict | None:
    try:
        if not CACHE.exists():
            return None
        age = datetime.now(timezone.utc).timestamp() - CACHE.stat().st_mtime
        if age > CACHE_MAX_AGE_SECONDS:
            return None
        data = json.loads(CACHE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) and isinstance(data.get("result"), list) else None
    except Exception:
        return None


def _request_json(url: str, *, body: dict | None = None, timeout: int = 20) -> dict:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    request = Request(url, data=data, headers=headers, method="POST" if body is not None else "GET")
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read(8 * 1024 * 1024 + 1)
            if len(raw) > 8 * 1024 * 1024:
                raise RuntimeError("Resposta do trade excedeu o limite local de segurança.")
            payload = json.loads(raw.decode("utf-8"))
            if not isinstance(payload, dict):
                raise RuntimeError("O trade retornou uma resposta inesperada.")
            return payload
    except HTTPError as exc:
        detail = ""
        try:
            detail = exc.read(4096).decode("utf-8", "replace")
            parsed = json.loads(detail)
            if isinstance(parsed, dict):
                detail = str(parsed.get("error", {}).get("message") or parsed.get("error") or detail)
        except Exception:
            pass
        if exc.code == 429:
            raise RuntimeError("O trade2 aplicou rate limit. Aguarde alguns segundos e tente novamente.") from exc
        if exc.code == 403:
            raise RuntimeError("O trade2 recusou a requisição pública. Tente abrir o site oficial e repetir a busca.") from exc
        raise RuntimeError(f"Trade2 respondeu HTTP {exc.code}{': '+detail[:180] if detail else ''}.") from exc
    except (URLError, TimeoutError) as exc:
        raise RuntimeError(f"Não foi possível alcançar o trade2: {exc}.") from exc


def stats_catalog(force: bool = False) -> dict:
    if not force:
        cached = _load_cache()
        if cached:
            return cached
    with _LOCK:
        if not force:
            cached = _load_cache()
            if cached:
                return cached
        payload = _request_json(STATS_URL)
        if not isinstance(payload.get("result"), list):
            raise RuntimeError("Catálogo de stats do trade2 não tem o formato esperado.")
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        tmp = CACHE.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.replace(CACHE)
        return payload


def _stat_rows(payload: dict) -> list[dict]:
    rows = []
    for group in payload.get("result") or []:
        if not isinstance(group, dict):
            continue
        group_label = str(group.get("label") or group.get("id") or "Stat")
        group_id = str(group.get("id") or "")
        for entry in group.get("entries") or []:
            if not isinstance(entry, dict) or not entry.get("id") or not entry.get("text"):
                continue
            rows.append({
                "id": str(entry["id"]),
                "text": _plain(entry["text"]),
                "pattern": stat_pattern(entry["text"]),
                "group": group_label,
                "group_id": group_id,
                "type": entry.get("type") or "",
            })
    return rows


def match_item_mods(lines: list[str], payload: dict | None = None) -> list[dict]:
    payload = payload or stats_catalog()
    by_pattern: dict[str, list[dict]] = {}
    for row in _stat_rows(payload):
        by_pattern.setdefault(row["pattern"], []).append(row)

    # Prefer concrete item affixes over pseudo aggregates for text copied from an item.
    order = {"explicit": 0, "implicit": 1, "rune": 2, "enchant": 3, "fractured": 4, "crafted": 5, "pseudo": 9}
    out = []
    seen = set()
    for line in lines or []:
        raw = str(line or "")
        rendered = _plain(raw)
        if not rendered or rendered in seen:
            continue
        seen.add(rendered)
        candidates = by_pattern.get(stat_pattern(rendered), [])
        candidates = sorted(candidates, key=lambda x: (order.get(x.get("group_id", ""), 6), x["id"]))
        values = numeric_values(rendered)
        ranges = roll_ranges(raw)
        if candidates:
            best = candidates[0]
            out.append({
                "text": rendered,
                "raw_text": raw.strip(),
                "roll_ranges": ranges,
                "matched": True,
                "id": best["id"],
                "trade_text": best["text"],
                "group": best["group"],
                "values": values,
                "min": values[0] if len(values) == 1 else None,
                "max": None,
                "alternatives": len(candidates) - 1,
            })
        else:
            out.append({
                "text": rendered,
                "raw_text": raw.strip(),
                "roll_ranges": ranges,
                "matched": False,
                "id": "",
                "trade_text": "",
                "group": "",
                "values": values,
                "min": values[0] if len(values) == 1 else None,
                "max": None,
                "alternatives": 0,
            })
    return out


def _slot_item(summary: dict, slot: str) -> dict:
    slots = ((summary or {}).get("items") or {}).get("slots") or []
    target = str(slot or "")
    found = next((x for x in slots if str(x.get("slot") or "") == target), None)
    if not found or not isinstance(found.get("item"), dict):
        raise ValueError("O slot selecionado não existe mais na build atual.")
    return found["item"]


def _trade_lines(item: dict) -> list[str]:
    rows = item.get("trade_lines") or item.get("preview") or []
    return [str(x) for x in rows if str(x).strip()][:24]


def prepare_item(summary: dict, slot: str) -> dict:
    item = _slot_item(summary, slot)
    mods = match_item_mods(_trade_lines(item))
    matched = sum(1 for x in mods if x["matched"])
    return {
        "slot": slot,
        "item": {
            "name": item.get("name") or item.get("base_type") or "Item",
            "base_type": item.get("base_type") or "",
            "rarity": item.get("rarity") or "",
            "ilvl": item.get("ilvl"),
            "preview": item.get("preview") or [],
            "icon": item.get("icon") or "",
        },
        "mods": mods,
        "matched": matched,
        "unmatched": len(mods) - matched,
        "league": summary.get("league") or "Standard",
        "note": "Os filtros detectados são comparados com o catálogo público atual do trade2. Revise os valores antes de buscar.",
    }


def _number_or_none(value):
    if value is None or value == "":
        return None
    try:
        n = float(value)
        return int(n) if n.is_integer() else n
    except (TypeError, ValueError):
        return None


def build_search_query(item: dict, filters: list[dict] | None = None, *, base_only: bool = False, online: bool = True) -> dict:
    rarity = str(item.get("rarity") or "").casefold()
    base_type = str(item.get("base_type") or "").strip()
    name = str(item.get("name") or "").strip()
    query: dict = {"status": {"option": "online" if online else "any"}, "stats": []}
    if base_type:
        query["type"] = base_type
    # Named uniques should search by the unique name. Rare/magic generated names must not.
    if rarity == "unique" and name and name != base_type:
        query["name"] = name

    stat_filters = []
    if not base_only:
        for f in filters or []:
            if not isinstance(f, dict) or not f.get("enabled", True) or not f.get("id"):
                continue
            value = {}
            minimum = _number_or_none(f.get("min"))
            maximum = _number_or_none(f.get("max"))
            if minimum is not None:
                value["min"] = minimum
            if maximum is not None:
                value["max"] = maximum
            row = {"id": str(f["id"]), "disabled": False}
            if value:
                row["value"] = value
            stat_filters.append(row)
    if stat_filters:
        query["stats"] = [{"type": "and", "filters": stat_filters, "disabled": False}]

    return {"query": query, "sort": {"price": "asc"}}


def search_item(summary: dict, slot: str, *, league: str, filters: list[dict] | None = None, base_only: bool = False, online: bool = True) -> dict:
    item = _slot_item(summary, slot)
    league = str(league or summary.get("league") or "Standard").strip() or "Standard"
    if len(league) > 120:
        raise ValueError("Nome de liga inválido.")
    payload = build_search_query(item, filters, base_only=base_only, online=online)
    endpoint = f"{BASE}/api/trade2/search/poe2/{quote(league, safe='')}"
    result = _request_json(endpoint, body=payload, timeout=25)
    search_id = str(result.get("id") or "")
    if not search_id:
        raise RuntimeError("O trade2 não devolveu um ID de busca.")
    url = f"{BASE}/trade2/search/poe2/{quote(league, safe='')}/{quote(search_id, safe='')}"
    return {
        "id": search_id,
        "total": result.get("total"),
        "url": url,
        "league": league,
        "query": payload,
        "created_at": _now_iso(),
    }
