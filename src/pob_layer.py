"""Camada de dados do PoB 2: árvore nova a partir do export oficial da GGG, antes do PoB novo sair.

O PoB instalado continua intacto. A camada fica em `<engine>/pob-layer/` com os arquivos que mudam
(`TreeData/<versão>/`, `GameVersions.lua`) e o motor lê dela primeiro (prelúdio Lua em `lua_prelude`). Quando o
PoB oficial da versão sair, `remove_version` tira a versão da camada e o PoB novo assume.

Árvore (`build_tree`):
1. baixa `data.json` e `assets/` de github.com/grindinggear/poe2-skilltree-export no ref pedido;
2. roda o `Export/Scripts/passivetree_ggg.lua` do próprio PoB (src/lua/synergy_layer_tree.lua, comando export);
3. reaplica o que o PoB corrigiu à mão sobre o export da GGG (receitas de anoint, flags `applyToArmour`/`sinister`,
   nós trocáveis, textos e nós que o export não traz). O delta sai da versão base: export da GGG da base contra a
   árvore do PoB instalado para ela. Onde a GGG mexeu no nó, a correção antiga não é aplicada e volta como conflito.

Backtest de 2026-11-07: export GGG 0.5.5 + delta da 0.5.4 = árvore 0.5.5 lançada pelo PoB (commit 49e9392),
idêntica em nós, ligações, stats e flags. Ficam de fora o desenho das ascendências (distância fixa sem o
Ascendancy.dat) e o que só existe nos arquivos do jogo para nós novos (receitas de anoint de nó novo).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from . import pob_engine

LAYER_DIR = pob_engine.USER_ENGINE_DIR / "pob-layer"
SOURCE_DIR = pob_engine.USER_ENGINE_DIR / "pob-layer-src"
MANIFEST = "manifest.json"
GGG_TREE_REPO = "grindinggear/poe2-skilltree-export"
TREE_TOOL = Path(__file__).resolve().parent / "lua" / "synergy_layer_tree.lua"
DATA_TOOL = Path(__file__).resolve().parent / "lua" / "synergy_layer_data.lua"
# Caminhos relativos ao src do PoB que a camada pode sobrepor; o resto vai sempre ao PoB instalado.
LAYER_PREFIXES = ("TreeData/", "GameVersions.lua", "Data/")
# Extrator de bundles do cliente (o mesmo que o CONTRIBUTING.md do PoB indica), conferido pelo sha256 da release.
BUN_VERSION = "0.2.4"
BUN_URL = f"https://github.com/zao/ooz/releases/download/v{BUN_VERSION}/bun-{BUN_VERSION}-x64-Release.zip"
BUN_SHA256 = "e6d7e728a8b02d2203a80f41bdf8f13c524afda2d393773930b8dfc0afd94af4"
BUN_FILES = ("bun_extract_file.exe", "libbun.dll", "libooz.dll")
BUN_DIR = pob_engine.USER_ENGINE_DIR / "tools" / f"bun-{BUN_VERSION}"
POB_RAW = "https://raw.githubusercontent.com/PathOfBuildingCommunity/PathOfBuilding-PoE2"
SPEC_REF = "dev"
# Scripts do Export do PoB que geram Data/. statdesc vai primeiro (o "Run All" do PoB faz o mesmo). Ficam de fora
# passivetree/passivetree_ggg (árvore: build_tree) e assets (imagens; pede ferramentas de DDS).
DATA_SCRIPTS = ("statdesc", "enums", "bases", "mods", "skills", "minions", "miscdata", "essence", "soulcores", "costs",
                "bossData", "modScalability", "pantheons", "worldAreas", "skillGemList", "spectreList",
                "legionPassives", "flavourText", "uModsToText")
PRELUDE_MARK = "-- PoE2 Synergy Finder: camada pob-layer"


class LayerError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _get(url: str, timeout: int = 60) -> bytes:
    req = Request(url, headers={"User-Agent": "poe2-synergy-finder"})
    with urlopen(req, timeout=timeout) as r:
        return r.read()


def pob_root() -> Path:
    """Raiz do checkout do PoB (pai do src configurado)."""
    src = pob_engine._expand(pob_engine.load_config().get("pob_src_path"))
    if not src or not (src / "Export" / "Scripts" / "passivetree_ggg.lua").is_file():
        raise LayerError("PoB não configurado ou sem Export/Scripts/passivetree_ggg.lua.")
    return src.parent


def luajit() -> Path:
    lua = pob_engine._expand(pob_engine.load_config().get("luajit_path"))
    if not lua or not lua.is_file():
        raise LayerError("LuaJIT não configurado: use Build atual → Motor PoB → Detectar.")
    return lua


def run_tool(*args: str, root: Path | None = None, timeout: int = 600) -> dict:
    """Roda um comando do synergy_layer_tree.lua e devolve o relatório (última linha JSON da saída)."""
    root = root or pob_root()
    runtime = root / "runtime"
    env = dict(os.environ, PATH=str(runtime) + os.pathsep + os.environ.get("PATH", ""))
    p = subprocess.run([str(luajit()), str(TREE_TOOL), args[0], str(root), *map(str, args[1:])],
                       cwd=str(runtime), env=env, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout)
    lines = [l for l in p.stdout.splitlines() if l.startswith("{")]
    if p.returncode != 0 or not lines:
        tail = (p.stderr or p.stdout).strip().splitlines()[-5:]
        raise LayerError(f"{args[0]} falhou: " + " | ".join(tail))
    return json.loads(lines[-1])


def fetch_ggg_tree(ref: str, dest: Path | None = None) -> Path:
    """Baixa data.json e assets/ do export da GGG no ref (commit, tag ou branch). Devolve a pasta de trabalho
    (`<dest>/TreeData/{data.json,assets}`), no formato que o passivetree_ggg.lua espera."""
    if not re.fullmatch(r"[\w.\-/]+", ref):
        raise LayerError(f"ref inválido: {ref!r}")
    work = dest or SOURCE_DIR / ref.replace("/", "_")
    tree_dir = work / "TreeData"
    (tree_dir / "assets").mkdir(parents=True, exist_ok=True)
    raw = f"https://raw.githubusercontent.com/{GGG_TREE_REPO}/{ref}/"
    if not (tree_dir / "data.json").is_file():
        (tree_dir / "data.json").write_bytes(_get(raw + "data.json"))
    listing = json.loads(_get(f"https://api.github.com/repos/{GGG_TREE_REPO}/contents/assets?ref={ref}"))
    for item in listing:
        name = item.get("name", "")
        if item.get("type") != "file" or not re.fullmatch(r"[\w.\-]+", name):
            continue
        target = tree_dir / "assets" / name
        if not target.is_file() or target.stat().st_size != item.get("size"):
            target.write_bytes(_get(raw + "assets/" + name))
    return work


def ggg_tree_commits(limit: int = 10) -> list[dict]:
    """Últimos commits do export da GGG (a mensagem costuma ser a versão do jogo, ex.: '0.5.5')."""
    data = json.loads(_get(f"https://api.github.com/repos/{GGG_TREE_REPO}/commits?per_page={int(limit)}"))
    return [{"ref": c["sha"][:10], "data": c["commit"]["author"]["date"], "versao": c["commit"]["message"].splitlines()[0]}
            for c in data]


def export_tree(work: Path, version: str, root: Path | None = None) -> Path:
    (work / "TreeData" / version).mkdir(parents=True, exist_ok=True)  # o script do PoB não cria a pasta
    report = run_tool("export", work, version, root=root)
    return Path(report["arquivo"])


def _manifest(layer: Path) -> dict:
    try:
        return json.loads((layer / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"versoes": {}}


def _write_manifest(layer: Path, data: dict):
    layer.mkdir(parents=True, exist_ok=True)
    (layer / MANIFEST).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def pob_tree_versions(src: Path) -> list[str]:
    text = (src / "GameVersions.lua").read_text(encoding="utf-8")
    m = re.search(r"treeVersionList\s*=\s*\{([^}]*)\}", text)
    return re.findall(r'"([^"]+)"', m.group(1)) if m else []


def write_game_versions(layer: Path, src: Path, versions: list[str]):
    """GameVersions.lua da camada: o do PoB instalado mais as versões da camada que ele ainda não tem."""
    base = (src / "GameVersions.lua").read_text(encoding="utf-8")
    known = set(pob_tree_versions(src))
    extra = [v for v in versions if v not in known]
    target = layer / "GameVersions.lua"
    if not extra:
        if target.exists():
            target.unlink()
        return
    lines = [base.rstrip(), "", "-- PoE2 Synergy Finder: versões da camada pob-layer (export da GGG), gerado."]
    for v in extra:
        num = float(v.replace("_", ".")) if re.fullmatch(r"\d+_\d+", v) else 99.0
        lines.append(f'table.insert(treeVersionList, "{v}")')
        lines.append(f'treeVersions["{v}"] = {{ display = "{v} (GGG)", num = {num} }}')
    lines.append("latestTreeVersion = treeVersionList[#treeVersionList]")
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_tree(version: str, ref: str, base_version: str | None = None, base_ref: str | None = None,
               layer: Path | None = None, root: Path | None = None) -> dict:
    """Gera TreeData/<version> na camada a partir do export da GGG em `ref`. Com `base_version` e `base_ref`,
    reaplica as correções do PoB: delta entre o export da GGG em `base_ref` e a árvore do PoB instalado em
    `base_version`."""
    layer = layer or LAYER_DIR
    if not re.fullmatch(r"\d+_\d+[\w]*", version):
        raise LayerError(f"versão inválida: {version!r} (ex.: 1_0)")
    root = root or pob_root()
    src = root / "src"
    work = fetch_ggg_tree(ref)
    tree_file = export_tree(work, version, root)
    report = {"versao": version, "ggg_ref": ref, "base": None, "criado": _now()}
    if base_version and base_ref:
        pob_tree = src / "TreeData" / base_version / "tree.lua"
        if not pob_tree.is_file():
            raise LayerError(f"o PoB instalado não tem TreeData/{base_version}/tree.lua")
        base_work = fetch_ggg_tree(base_ref)
        base_file = export_tree(base_work, base_version, root)
        delta_file = work / f"delta_{base_version}.lua"
        delta = run_tool("delta", base_file, pob_tree, delta_file, root=root)
        applied = run_tool("apply", tree_file, delta_file, tree_file, root=root)
        report["base"] = {"versao": base_version, "ggg_ref": base_ref, "nos_corrigidos_pelo_pob": delta["nos"],
                          "nos_so_pob": delta.get("nos_so_pob", 0), "aplicados": applied["aplicados"],
                          "ja_iguais": applied["ja_iguais"], "conflitos": applied["conflitos"],
                          "nos_sumidos": applied["nos_sumidos"], "nos_inseridos": applied.get("nos_inseridos", [])}
    target = layer / "TreeData" / version
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(tree_file.parent, target)
    run_tool("tojson", target / "tree.lua", target / "tree.json", root=root)
    data = _manifest(layer)
    data["versoes"][version] = report
    _write_manifest(layer, data)
    write_game_versions(layer, src, list(data["versoes"]))
    return report


def install_bun(target: Path | None = None) -> Path:
    """bun_extract_file.exe e DLLs em `<engine>/tools/bun-<versão>/`; baixa a release fixada e confere o sha256."""
    import hashlib
    import io
    import zipfile
    target = target or BUN_DIR
    if all((target / f).is_file() for f in BUN_FILES):
        return target
    payload = _get(BUN_URL, timeout=120)
    digest = hashlib.sha256(payload).hexdigest()
    if digest != BUN_SHA256:
        raise LayerError(f"sha256 do extrator não confere: {digest}")
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(payload)) as z:
        for name in BUN_FILES:
            (target / name).write_bytes(z.read(name))
    return target


def find_game_dir() -> Path | None:
    """Pasta do cliente do PoE 2 com Bundles2 (Steam) ou Content.ggpk (cliente da GGG)."""
    candidates = []
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\GrindingGearGames\Path of Exile 2") as k:
            candidates.append(Path(winreg.QueryValueEx(k, "InstallLocation")[0]))
    except OSError:
        pass
    steam = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Steam"
    libraries = [steam]
    try:
        vdf = (steam / "steamapps" / "libraryfolders.vdf").read_text(encoding="utf-8", errors="replace")
        libraries += [Path(p.replace("\\\\", "\\")) for p in re.findall(r'"path"\s+"([^"]+)"', vdf)]
    except OSError:
        pass
    candidates += [lib / "steamapps" / "common" / "Path of Exile 2" for lib in libraries]
    # Com os dois clientes instalados, vale o atualizado por último (aqui o da GGG parou em julho e o Steam em
    # novembro). O extrator quer a pasta no Steam e o arquivo Content.ggpk no cliente da GGG.
    found = []
    for c in candidates:
        for data, arg in ((c / "Bundles2" / "_.index.bin", c), (c / "Content.ggpk", c / "Content.ggpk")):
            if data.is_file():
                found.append((data.stat().st_mtime, arg))
    return max(found)[1] if found else None


def _files_differ(a: Path, b: Path) -> bool:
    """Conteúdo diferente, sem contar quebra de linha (o checkout do PoB vem com CRLF e o export grava LF)."""
    return not b.is_file() or _no_cr(a) != _no_cr(b)


def _lua_syntax_errors(files: list[Path]) -> dict[Path, str]:
    """{arquivo: erro} dos .lua que o LuaJIT não compila (só compila, não executa)."""
    lua_files = [f for f in files if f.suffix == ".lua"]
    if not lua_files:
        return {}
    code = ("for path in io.lines() do local f, err = loadfile(path) "
            "if not f then io.write(path, '\\t', (err:gsub('\\n', ' ')), '\\n') end end")
    p = subprocess.run([str(luajit()), "-e", code], input="\n".join(map(str, lua_files)), capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=600)
    out = {}
    for line in p.stdout.splitlines():
        path, _, err = line.partition("\t")
        out[Path(path)] = err[-300:]
    return out


def _no_cr(f: Path) -> bytes:
    return f.read_bytes().replace(b"\r\n", b"\n")


def build_data(game_dir: Path | None = None, scripts: tuple[str, ...] | None = None, layer: Path | None = None,
               root: Path | None = None, spec_ref: str | None = SPEC_REF, timeout: int = 3600) -> dict:
    """Roda os scripts de Export do PoB contra os arquivos do cliente instalado, numa cópia de trabalho do src, e
    leva para `<camada>/Data/` só os arquivos que ficaram diferentes do PoB instalado.

    O esquema dos .dat (`Export/spec.lua`) muda quando a GGG acrescenta colunas; o do PoB instalado pode estar
    atrás do cliente (2026-11-07: Mods com 693 bytes por linha no cliente, 677 no spec do PoB 0.23.1). Com
    `spec_ref`, usa o spec.lua desse branch do PoB no GitHub (o `dev` costuma sair antes)."""
    layer = layer or LAYER_DIR
    root = root or pob_root()
    src = root / "src"
    game = Path(game_dir) if game_dir else find_game_dir()
    if not game or not ((game / "Bundles2" / "_.index.bin").is_file() or game.suffix == ".ggpk" and game.is_file()):
        raise LayerError("cliente do PoE 2 não encontrado (pasta com Bundles2/_.index.bin ou o Content.ggpk)")
    bun = install_bun()
    work = SOURCE_DIR / "data-work" / "src"
    if work.parent.exists():
        shutil.rmtree(work.parent)
    work.mkdir(parents=True)
    for d in ("Classes", "Data", "Export", "Modules", "Assets"):
        shutil.copytree(src / d, work / d)
    shutil.copy2(src / "GameVersions.lua", work / "GameVersions.lua")
    (work / "TreeData").mkdir()
    for f in BUN_FILES:
        shutil.copy2(bun / f, work / "Export" / "ggpk" / f)
    if spec_ref:
        (work / "Export" / "spec.lua").write_bytes(_get(f"{POB_RAW}/{spec_ref}/src/Export/spec.lua"))
    runtime = root / "runtime"
    env = dict(os.environ, PATH=str(runtime) + os.pathsep + os.environ.get("PATH", ""))
    order = scripts or DATA_SCRIPTS
    p = subprocess.run([str(luajit()), str(DATA_TOOL), str(root), str(work), str(game), ",".join(order)],
                       cwd=str(work / "Export"), env=env, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout)
    (work.parent / "export.log").write_text(p.stderr, encoding="utf-8")
    lines = [l for l in p.stdout.splitlines() if l.startswith("{")]
    if p.returncode != 0 or not lines:
        tail = (p.stderr or p.stdout).strip().splitlines()[-6:]
        raise LayerError("export dos dados falhou: " + " | ".join(tail))
    report = json.loads(lines[-1])
    changed = []
    for f in sorted((work / "Data").rglob("*")):
        if f.is_file():
            rel = f.relative_to(work / "Data").as_posix()
            if _files_differ(f, src / "Data" / rel):
                changed.append(rel)
    # Script que falha no meio deixa arquivo pela metade (2026-11-07: bossData -> BossSkills.lua). Só vai para a
    # camada o que o LuaJIT consegue compilar.
    broken = _lua_syntax_errors([work / "Data" / rel for rel in changed])
    changed = [rel for rel in changed if (work / "Data" / rel) not in broken]
    target = layer / "Data"
    if target.exists():
        shutil.rmtree(target)
    for rel in changed:
        (target / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(work / "Data" / rel, target / rel)
    summary = {"criado": _now(), "jogo": str(game), "spec": spec_ref or "instalado", "liga": report.get("liga"),
               "dat": report.get("dat"),
               "scripts": report.get("scripts"), "arquivos_mudados": changed,
               "descartados": {str(p.relative_to(work / "Data").as_posix()): e for p, e in broken.items()}}
    data = _manifest(layer)
    data["dados"] = summary
    _write_manifest(layer, data)
    return summary


def remove_data(layer: Path | None = None) -> dict:
    """Tira os Data/ da camada (o PoB instalado volta a valer)."""
    layer = layer or LAYER_DIR
    if (layer / "Data").exists():
        shutil.rmtree(layer / "Data")
    data = _manifest(layer)
    data.pop("dados", None)
    _write_manifest(layer, data)
    return status(layer)


def remove_version(version: str, layer: Path | None = None, root: Path | None = None) -> dict:
    """Tira uma versão da camada (ex.: quando o PoB oficial dela sair)."""
    layer = layer or LAYER_DIR
    data = _manifest(layer)
    data["versoes"].pop(version, None)
    target = layer / "TreeData" / version
    if target.exists():
        shutil.rmtree(target)
    _write_manifest(layer, data)
    write_game_versions(layer, (root or pob_root()) / "src", list(data["versoes"]))
    return status(layer)


def status(layer: Path | None = None) -> dict:
    layer = layer or LAYER_DIR
    data = _manifest(layer)
    return {"camada": str(layer), "ativa": bool(data["versoes"] or data.get("dados")), "versoes": data["versoes"],
            "dados": data.get("dados")}


def resolve(src: Path, rel: str, layer: Path | None = None) -> Path:
    """Arquivo do PoB com a camada por cima: `<camada>/<rel>` se existir e estiver num prefixo da camada, senão
    `<src>/<rel>`."""
    layer = layer or LAYER_DIR
    rel = rel.replace("\\", "/")
    if rel.startswith(LAYER_PREFIXES) and (layer / rel).is_file():
        return layer / rel
    return Path(src) / rel


def lua_prelude(layer: Path | None = None) -> str:
    """Código Lua que faz o motor ler os caminhos da camada antes dos do PoB. Vazio sem camada ativa."""
    layer = layer or LAYER_DIR
    if not status(layer)["ativa"]:
        return ""
    path = str(layer.resolve()).replace("\\", "/")
    prefixes = ", ".join(f'"{p}"' for p in LAYER_PREFIXES)
    return f"""{PRELUDE_MARK} (gerado; o PoB instalado não é alterado)
do
  local LAYER, PREFIXES = [[{path}]], {{ {prefixes} }}
  local raw_open, raw_loadfile = io.open, loadfile
  local function layered(p)
    if type(p) ~= "string" then return nil end
    local rel = p:gsub("\\\\", "/")
    for _, pre in ipairs(PREFIXES) do
      if rel:sub(1, #pre) == pre then
        local candidate = LAYER .. "/" .. rel
        local f = raw_open(candidate, "rb")
        if f then f:close(); return candidate end
        return nil
      end
    end
  end
  io.open = function(p, mode, ...)
    if mode == nil or mode:sub(1, 1) == "r" then
      local c = layered(p)
      if c then return raw_open(c, mode, ...) end
    end
    return raw_open(p, mode, ...)
  end
  loadfile = function(p, ...)
    local c = layered(p)
    return raw_loadfile(c or p, ...)
  end
end
"""


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="python -m src.pob_layer", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("tree", help="gera TreeData/<versão> na camada a partir do export da GGG")
    t.add_argument("--versao", required=True, help="nome da versão no PoB, ex.: 1_0")
    t.add_argument("--ref", required=True, help="commit, tag ou branch do poe2-skilltree-export")
    t.add_argument("--base", help="versão do PoB instalado cujo delta reaplicar, ex.: 0_5")
    t.add_argument("--base-ref", help="ref do export da GGG que corresponde à --base")
    d = sub.add_parser("data", help="gera Data/ na camada a partir dos arquivos do cliente instalado")
    d.add_argument("--jogo", help="pasta do cliente (padrão: Steam ou cliente da GGG achados no registro)")
    d.add_argument("--scripts", help="scripts do Export separados por vírgula (padrão: DATA_SCRIPTS)")
    d.add_argument("--spec", default=SPEC_REF, help="branch do PoB de onde vem o Export/spec.lua ('' = o instalado)")
    sub.add_parser("remove-data", help="tira os Data/ da camada")
    sub.add_parser("commits", help="últimos commits do export da GGG")
    sub.add_parser("status", help="versões na camada")
    r = sub.add_parser("remove", help="tira uma versão da camada")
    r.add_argument("versao")
    a = ap.parse_args(argv)
    if a.cmd == "tree":
        out = build_tree(a.versao, a.ref, a.base, a.base_ref)
    elif a.cmd == "data":
        out = build_data(a.jogo, tuple(a.scripts.split(",")) if a.scripts else None, spec_ref=a.spec or None)
    elif a.cmd == "remove-data":
        out = remove_data()
    elif a.cmd == "commits":
        out = ggg_tree_commits()
    elif a.cmd == "remove":
        out = remove_version(a.versao)
    else:
        out = status()
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
