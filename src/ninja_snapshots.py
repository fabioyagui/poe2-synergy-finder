"""Snapshots do poe.ninja (PoE 2): uso por ascendência e por ascendência + skill em marcos fixos de cada liga.

O poe.ninja apaga as ligas antigas (a 0.4 já não existe lá), e os retrotestes do roteiro de starter precisam do dia
3 de cada liga. Este módulo guarda, por liga, os marcos do time machine do site (`hour-12`, `day-1`, `day-3`,
`week-1`, `week-4`, ...) em `data/ninja/<liga>/<marco>.json`. Marco já salvo não é baixado de novo: o time machine
congela cada marco.

Formato da API (lido em 2026-11-07, sem esquema publicado):
- `GET /poe2/api/data/index-state` (JSON): ligas, `snapshotVersions[].version/snapshotName/timeMachineLabels`.
- `GET /poe2/api/builds/<version>/search?overview=<snapshotName>&timemachine=<marco>[&class=<Ascendência>]`
  (protobuf): campo 1 = total de personagens; campo 2 = dimensões (`class`, `skills`, `keypassives`, ...) com
  entradas {1: índice no dicionário (0 omitido), 2: contagem}; campo 6 = {1: dicionário, 2: hash}.
- `GET /poe2/api/builds/dictionary/<hash>` (binário "NDIC"): uint32 com a quantidade no byte 12, depois um varint
  de tamanho por nome e os nomes em UTF-8 em sequência.
O total da busca são os personagens que o poe.ninja lista (acima de um corte de nível); a fatia de uma skill é a
dos personagens da ascendência que a usam, não a de skill principal.
"""
from __future__ import annotations

import json
import struct
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

BASE = "https://poe.ninja/poe2/api"
ROOT = Path(__file__).resolve().parents[1] / "data" / "ninja"
LABELS = ("hour-12", "day-1", "day-3", "day-6", "week-1", "week-2", "week-4", "week-8")
TOP_SKILLS = 40
PAUSE = 0.4  # segundos entre pedidos, para não pesar no site


def _get(url: str, timeout: int = 60) -> bytes:
    req = Request(url, headers={"User-Agent": "poe2-synergy-finder (snapshots semanais)"})
    with urlopen(req, timeout=timeout) as r:
        return r.read()


def _varint(b: bytes, i: int) -> tuple[int, int]:
    r = s = 0
    while True:
        c = b[i]
        i += 1
        r |= (c & 0x7F) << s
        s += 7
        if c < 0x80:
            return r, i


def parse_proto(b: bytes) -> list[tuple[int, int, object]]:
    """Mensagem protobuf sem esquema: [(campo, tipo, valor)]."""
    out, i = [], 0
    while i < len(b):
        key, i = _varint(b, i)
        field, wire = key >> 3, key & 7
        if wire == 0:
            v, i = _varint(b, i)
        elif wire == 2:
            n, i = _varint(b, i)
            v, i = b[i:i + n], i + n
        elif wire == 1:
            v, i = b[i:i + 8], i + 8
        elif wire == 5:
            v, i = b[i:i + 4], i + 4
        else:
            raise ValueError(f"tipo protobuf não suportado: {wire}")
        out.append((field, wire, v))
    return out


def parse_dictionary(b: bytes) -> list[str]:
    """Dicionário NDIC do poe.ninja: nomes na ordem do índice."""
    if b[:4] != b"NDIC":
        raise ValueError("não é um dicionário NDIC")
    count = struct.unpack_from("<I", b, 12)[0]
    for start in range(16, len(b)):
        i, lens = start, []
        try:
            for _ in range(count):
                n, i = _varint(b, i)
                lens.append(n)
        except IndexError:
            break
        if all(lens) and i + sum(lens) == len(b):
            names, o = [], i
            for n in lens:
                names.append(b[o:o + n].decode("utf-8"))
                o += n
            return names
    raise ValueError("dicionário NDIC sem tabela de tamanhos reconhecível")


def parse_search(b: bytes) -> dict:
    """{total, dims: {dimensão: [(índice, contagem)]}, dicts: {dicionário: hash}} de uma resposta de busca."""
    msg = parse_proto(parse_proto(b)[0][2])
    out = {"total": 0, "dims": {}, "dicts": {}}
    for field, _, v in msg:
        if field == 1:
            out["total"] = v
        elif field == 2:
            sub = parse_proto(v)
            name = next(x[2].decode() for x in sub if x[0] == 1)
            dict_name = next((x[2].decode() for x in sub if x[0] == 2), name)
            entries = []
            for f, _, e in sub:
                if f == 3:
                    kv = {k: val for k, _, val in parse_proto(e)}
                    entries.append((kv.get(1, 0), kv.get(2, 0)))
            out["dims"][name] = {"dicionario": dict_name, "entradas": entries}
        elif field == 6:
            sub = parse_proto(v)
            name = next(x[2].decode() for x in sub if x[0] == 1)
            out["dicts"][name] = next(x[2].decode() for x in sub if x[0] == 2)
    return out


class Client:
    def __init__(self, pause: float = PAUSE):
        self.pause = pause
        self._dicts: dict[str, list[str]] = {}

    def _fetch(self, url: str) -> bytes:
        data = _get(url)
        time.sleep(self.pause)
        return data

    def index(self) -> dict:
        return json.loads(self._fetch(f"{BASE}/data/index-state"))

    def dictionary(self, h: str) -> list[str]:
        if h not in self._dicts:
            self._dicts[h] = parse_dictionary(self._fetch(f"{BASE}/builds/dictionary/{h}"))
        return self._dicts[h]

    def search(self, version: str, overview: str, label: str, ascendancy: str | None = None) -> dict:
        url = f"{BASE}/builds/{version}/search?overview={overview}&timemachine={label}"
        if ascendancy:
            url += "&class=" + quote(ascendancy)
        return parse_search(self._fetch(url))

    def counts(self, result: dict, dim: str, top: int | None = None) -> dict[str, int]:
        d = result["dims"].get(dim)
        if not d:
            return {}
        names = self.dictionary(result["dicts"][d["dicionario"]])
        rows = sorted(((c, names[i]) for i, c in d["entradas"] if i < len(names)), reverse=True)
        return {n: c for c, n in rows[:top] if c}


def leagues(index: dict, include: str = "softcore") -> list[dict]:
    """Ligas com time machine. include: 'softcore' (trade e SSF, sem HC nem Standard; o critério da starter é SSF),
    'all'."""
    out = []
    for s in index.get("snapshotVersions", []):
        name = s.get("name", "")
        if s.get("url", "").startswith("pl"):
            continue  # ligas privadas
        if include == "softcore" and (name.startswith(("HC ", "HC SSF ")) or name in ("Standard", "Hardcore")):
            continue
        out.append(s)
    return out


def capture(league: dict, label: str, client: Client, root: Path = ROOT) -> Path | None:
    """Grava `<root>/<liga>/<marco>.json`; devolve o caminho, ou None se o marco já existe ou ainda não saiu."""
    target = root / league["url"] / f"{label}.json"
    if target.exists() or label not in league.get("timeMachineLabels", []):
        return None
    overall = client.search(league["version"], league["snapshotName"], label)
    classes = client.counts(overall, "class")
    by_class = {}
    for asc, n in classes.items():
        r = client.search(league["version"], league["snapshotName"], label, asc)
        by_class[asc] = {"total": r["total"], "skills": client.counts(r, "skills", TOP_SKILLS),
                         "keypassives": client.counts(r, "keypassives", 15)}
    data = {"liga": league["name"], "url": league["url"], "marco": label, "versao": league["version"],
            "capturado": datetime.now(timezone.utc).replace(microsecond=0).isoformat(), "fonte": "poe.ninja",
            "total": overall["total"], "ascendencias": classes,
            "skills": client.counts(overall, "skills", TOP_SKILLS * 2), "por_ascendencia": by_class}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    return target


def capture_all(labels=LABELS, include: str = "softcore", root: Path = ROOT, only: str | None = None) -> dict:
    client = Client()
    idx = client.index()
    report = {"capturados": [], "pulados": 0, "erros": []}
    for lg in leagues(idx, include):
        if only and only not in (lg["url"], lg["name"]):
            continue
        for label in labels:
            try:
                path = capture(lg, label, client, root)
            except Exception as exc:  # um marco ruim não derruba os outros
                report["erros"].append(f"{lg['url']}/{label}: {exc}")
                continue
            if path:
                report["capturados"].append(str(path.relative_to(root)))
            else:
                report["pulados"] += 1
    return report


def shares(path: Path, top: int = 10) -> list[tuple[str, float]]:
    """[(ascendência, %)] de um snapshot salvo."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    total = data["total"] or 1
    return [(k, round(100 * v / total, 1)) for k, v in list(data["ascendencias"].items())[:top]]


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="python -m src.ninja_snapshots", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("capture", help="baixa os marcos que ainda não estão salvos")
    c.add_argument("--liga", help="url ou nome de uma liga (padrão: trade e SSF softcore)")
    c.add_argument("--todas", action="store_true", help="inclui HC, SSF e Standard")
    c.add_argument("--marcos", help="marcos separados por vírgula (padrão: " + ",".join(LABELS) + ")")
    s = sub.add_parser("show", help="fatias por ascendência de um snapshot salvo")
    s.add_argument("liga")
    s.add_argument("marco", nargs="?", default="day-3")
    a = ap.parse_args(argv)
    if a.cmd == "capture":
        labels = tuple(a.marcos.split(",")) if a.marcos else LABELS
        out = capture_all(labels, "all" if a.todas else "softcore", only=a.liga)
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 1 if out["erros"] and not out["capturados"] else 0
    for name, pct in shares(ROOT / a.liga / f"{a.marco}.json", 25):
        print(f"{pct:5.1f}%  {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
