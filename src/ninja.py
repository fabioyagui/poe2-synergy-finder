"""Leitor do poe.ninja (PoE 2): uso agregado por filtro e o código do PoB de cada personagem.

Porte do `src/ninja.py` do projeto PoE 1 (2026-11-05). A decodificação (protobuf sem esquema e dicionários NDIC) é a
mesma de `src.ninja_snapshots`. Diferenças do PoE 2:
- `overview` é o `snapshotName` da liga (ex.: `runes-of-aldur`), não a `url`; não há `type=exp`.
- busca: `poe2/api/builds/<version>/search?overview=..&timemachine=..&class=..&skills=..`
- personagem: `poe2/api/builds/<version>/character?account=..&name=..&overview=..&type=0&timeMachine=..` (JSON com
  `pathOfBuildingExport`, `keystones`, `passiveSelection`...).

O uso é de quem o poe.ninja lista (acima de um corte de nível), não da população inteira.
"""
from __future__ import annotations

import base64
import json
import time
import urllib.parse
import urllib.request
import zlib

from src import storage
from src.ninja_snapshots import parse_dictionary, parse_proto

BASE = "https://poe.ninja/poe2/api"
CACHE = storage.DATA / "cache" / "ninja"
USER_AGENT = "poe2-synergy-finder (pesquisa local)"
TTL = {"index": 3600, "search": 6 * 3600, "character": 24 * 3600}


def _fetch(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _cached(kind: str, key: str, url: str, ttl: int | None) -> bytes:
    safe = urllib.parse.quote(key, safe="")[:180]
    path = CACHE / kind / safe
    if path.exists() and (ttl is None or time.time() - path.stat().st_mtime < ttl):
        return path.read_bytes()
    body = _fetch(url)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return body


def index_state() -> dict:
    return json.loads(_cached("index", "index-state", f"{BASE}/data/index-state", TTL["index"]))


def snapshot(league: str | None = None) -> dict:
    """Snapshot de builds da liga (url, nome ou snapshotName); padrão: a primeira liga de trade softcore da lista."""
    snaps = index_state().get("snapshotVersions", [])
    if league:
        want = league.casefold()
        snaps = [s for s in snaps if want in (s.get("url", "").casefold(), s.get("name", "").casefold(),
                                             s.get("snapshotName", "").casefold())]
    else:
        snaps = [s for s in snaps if not s.get("name", "").startswith(("HC ", "SSF ", "HC SSF "))
                 and s.get("url") not in ("standard", "hardcore") and not s.get("url", "").startswith("pl")]
    if not snaps:
        raise ValueError(f"liga {league!r} não encontrada no poe.ninja")
    return snaps[0]


def dictionary(digest: str) -> list[str]:
    return parse_dictionary(_cached("dictionary", digest, f"{BASE}/builds/dictionary/{digest}", None))


def decode_search(body: bytes, names_for=dictionary) -> dict:
    """{total, dims: {dimensão: [(nome, contagem)] em ordem decrescente}, characters: [(account, name)]}."""
    message = parse_proto(parse_proto(body)[0][2])
    total = next((v for f, _w, v in message if f == 1), 0)
    digests = {}
    for f, _w, v in message:
        if f == 6:
            d = parse_proto(v)
            digests[d[0][2].decode()] = d[1][2].decode()
    dims = {}
    for f, _w, v in message:
        if f != 2:
            continue
        d = parse_proto(v)
        dim, dict_name = d[0][2].decode(), d[1][2].decode()
        names = names_for(digests[dict_name]) if dict_name in digests else []
        rows = []
        for ff, _ww, vv in d[2:]:
            if ff != 3:
                continue
            entry = {k: val for k, _x, val in parse_proto(vv)}
            idx, count = entry.get(1, 0), entry.get(2, 0)
            rows.append((names[idx] if idx < len(names) else str(idx), count))
        dims[dim] = sorted(rows, key=lambda r: -r[1])
    columns = {}
    for f, _w, v in message:
        if f == 12:
            d = parse_proto(v)
            columns[d[0][2].decode()] = [x.decode("utf-8", "replace") for ff, _ww, x in d if ff == 7]
    characters = list(zip(columns.get("account", []), columns.get("name", [])))
    return {"total": total, "dims": dims, "characters": characters}


def search(league: str | None = None, moment: str = "", **filters) -> dict:
    """Uso agregado com filtros do site (class=Gemling Legionnaire, skills=Oil Grenade, ...). moment: rótulo do time
    machine ("day-3", "week-4")."""
    snap = snapshot(league)
    query = {"overview": snap["snapshotName"], **({"timemachine": moment} if moment else {}),
             **{k: v for k, v in filters.items() if v}}
    url = f'{BASE}/builds/{snap["version"]}/search?' + urllib.parse.urlencode(query)
    key = f'{snap["version"]}|' + "|".join(f"{k}={v}" for k, v in sorted(query.items()))
    out = decode_search(_cached("search", key, url, TTL["search"]))
    out.update(league=snap["name"], version=snap["version"], filters=filters, moment=moment)
    return out


def character(account: str, name: str, league: str | None = None, moment: str = "") -> dict:
    """O personagem como estava no ponto `moment` do time machine (vazio = agora)."""
    snap = snapshot(league)
    q = urllib.parse.urlencode({"account": account, "name": name, "overview": snap["snapshotName"], "type": 0,
                                "timeMachine": moment or ""})
    body = _cached("character", f'{snap["version"]}|{account}|{name}|{moment}',
                   f'{BASE}/builds/{snap["version"]}/character?{q}', TTL["character"])
    return json.loads(body)


def pob_xml(code: str) -> str:
    """Código de exportação do PoB (base64 url-safe + zlib) -> XML."""
    code = code.strip().replace("-", "+").replace("_", "/")
    code += "=" * (-len(code) % 4)
    return zlib.decompress(base64.b64decode(code)).decode("utf-8")


def usage(dims: dict, total: int, dimension: str, limit: int = 40) -> list[dict]:
    return [{"name": n, "pct": round(100 * c / total, 1), "count": c} for n, c in dims.get(dimension, [])[:limit]
            if c and total]
