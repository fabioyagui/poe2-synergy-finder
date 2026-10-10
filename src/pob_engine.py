from __future__ import annotations

import json
import io
import os
from pathlib import Path
import queue
import shutil
import subprocess
import threading
import time
import urllib.request
import zipfile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENGINE_DIR = PROJECT_ROOT / "engine"
BRIDGE_DIR = ENGINE_DIR / "pob-api"
BRIDGE_PATCH_VERSION = "0.12.6-support-mod-pipeline-diagnostics"
CONFIG_PATH = PROJECT_ROOT / "data" / "pob" / "engine_config.json"

# Generated/runtime engine files must not live inside a OneDrive-synced project
# folder. Windows/OneDrive can keep handles on directories while the Finder is
# rebuilding its patched PoB bridge, which used to make shutil.rmtree() fail
# with WinError 5. Heavyweight PoB downloads and bridge overlays therefore use
# a machine-local stable directory. Existing project-local source files remain
# supported as read-only inputs.
def _stable_user_engine_dir() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / "PoE2 Synergy Finder" / "engine"
    return ENGINE_DIR

USER_ENGINE_DIR = _stable_user_engine_dir()
USER_POB_CHECKOUT = USER_ENGINE_DIR / "PathOfBuilding-PoE2"
BRIDGE_OVERLAY_DIR = USER_ENGINE_DIR / "pob-api-v0126"

UPSTREAM_BRIDGE_BASE = "https://raw.githubusercontent.com/zgrummons/pob2-mcp/main/pob-api/"
UPSTREAM_BRIDGE_FILES = {
    "bootstrap.lua": "bootstrap.lua",
    "utf8.lua": "utf8.lua",
    "API/Server.lua": "API/Server.lua",
    "API/Handlers.lua": "API/Handlers.lua",
    "API/BuildOps.lua": "API/BuildOps.lua",
}
UPSTREAM_BRIDGE_LICENSE = (
    "https://raw.githubusercontent.com/zgrummons/pob2-mcp/main/LICENSE"
)
UPSTREAM_HEADLESS = (
    "https://raw.githubusercontent.com/PathOfBuildingCommunity/"
    "PathOfBuilding-PoE2/master/src/HeadlessWrapper.lua"
)
POB2_ARCHIVE_URL = (
    "https://github.com/PathOfBuildingCommunity/"
    "PathOfBuilding-PoE2/archive/refs/heads/master.zip"
)
POB2_CHANNEL = "master"
LOCAL_POB_CHECKOUT = ENGINE_DIR / "PathOfBuilding-PoE2"

DEFAULT_CONFIG = {
    "luajit_path": "",
    "pob_src_path": "",
    "runtime_dll_path": "",
    "bridge_path": str(BRIDGE_DIR),
}

COMMON_LUAJIT = [
    r"C:\msys64\ucrt64\bin\luajit.exe",
    r"C:\msys64\mingw64\bin\luajit.exe",
]

def _expand(path: str | Path | None) -> Path | None:
    if not path:
        return None
    return Path(os.path.expandvars(os.path.expanduser(str(path)))).resolve()

def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        try:
            value = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                cfg.update({k: str(v) for k, v in value.items() if k in cfg})
        except Exception:
            pass
    return cfg


def _write_config(cfg: dict) -> dict:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    return cfg


def save_config(values: dict) -> dict:
    cfg = load_config()
    for key in cfg:
        if key in values and values[key] is not None:
            cfg[key] = str(values[key]).strip()
    return _write_config(cfg)

def _runtime_lua_dir_from_src(p: Path | None) -> Path | None:
    """Return the runtime/lua directory that belongs to a PoB program path.

    PoB appears in more than one Windows layout:
      * source checkout:   repo/src + repo/runtime/lua
      * packaged/GUI:      install/Launch.lua + install/Modules + install/lua
      * portable variants: program path + program/runtime/lua

    v0.19.1 only understood the first layout, so a perfectly valid installed
    PoB under %APPDATA% was rejected after the Finder was moved.
    """
    if not p:
        return None
    candidates = [
        p.parent / "runtime" / "lua",
        p / "runtime" / "lua",
        p / "lua",
    ]
    seen = set()
    for candidate in candidates:
        try:
            key = str(candidate.resolve()).casefold()
        except Exception:
            key = str(candidate).casefold()
        if key in seen:
            continue
        seen.add(key)
        if _valid_runtime_lua_dir(candidate):
            return candidate
    return None

def _runtime_root_from_src(p: Path | None) -> Path | None:
    lua_dir = _runtime_lua_dir_from_src(p)
    return lua_dir.parent if lua_dir else None

def _valid_runtime_lua_dir(lua_dir: Path | None) -> bool:
    if not lua_dir or not lua_dir.is_dir():
        return False
    # Launch.lua requires xml directly; these are representative pure-Lua deps.
    required = ["xml.lua"]
    return all((lua_dir / name).exists() for name in required)

def _valid_pob_src(p: Path | None) -> bool:
    return bool(
        p and p.is_dir()
        and (p / "Launch.lua").exists()
        and (p / "Modules").is_dir()
        and _valid_runtime_lua_dir(_runtime_lua_dir_from_src(p))
    )

def _valid_bridge(p: Path | None) -> bool:
    if not (
        p and p.is_dir()
        and (p / "bootstrap.lua").exists()
        and (p / "HeadlessWrapper.lua").exists()
        and (p / "API" / "Server.lua").exists()
        and (p / "API" / "Handlers.lua").exists()
        and (p / "API" / "BuildOps.lua").exists()
    ):
        return False

    try:
        wrapper = (p / "HeadlessWrapper.lua").read_text(encoding="utf-8")
    except Exception:
        return False

    if "_SimpleGraphic.def.lua" in wrapper:
        return (p / "_SimpleGraphic.def.lua").exists()

    return True


def _repair_moved_project_config(cfg: dict, persist: bool = False) -> tuple[dict, list[str]]:
    """Repair absolute paths that became stale after the Finder was moved.

    Only project-owned resources are rebased automatically. External LuaJIT or
    custom user paths are never guessed over a still-valid configured path.
    """
    out = dict(cfg)
    repaired: list[str] = []

    bridge = _expand(out.get("bridge_path"))
    if not _valid_bridge(bridge) and _valid_bridge(BRIDGE_DIR):
        out["bridge_path"] = str(BRIDGE_DIR)
        repaired.append("bridge_path")

    pob = _expand(out.get("pob_src_path"))
    if not _valid_pob_src(pob):
        for candidate in (LOCAL_POB_CHECKOUT / "src", USER_POB_CHECKOUT / "src"):
            if _valid_pob_src(candidate):
                out["pob_src_path"] = str(candidate)
                pob = candidate
                repaired.append("pob_src_path")
                break

    # A moved checkout carries its own runtime. Prefer that over a stale
    # absolute runtime path saved before the move.
    runtime = _expand(out.get("runtime_dll_path"))
    program_runtime = _runtime_root_from_src(pob) if _valid_pob_src(pob) else None
    if program_runtime:
        if not (runtime and runtime.exists()) or runtime.resolve() != program_runtime.resolve():
            out["runtime_dll_path"] = str(program_runtime)
            repaired.append("runtime_dll_path")

    if persist and repaired:
        _write_config(out)
    return out, repaired

def _find_luajit() -> str:
    found = shutil.which("luajit") or shutil.which("luajit.exe")
    if found:
        return str(Path(found).resolve())

    userprofile = os.environ.get("USERPROFILE", "")
    candidates = list(COMMON_LUAJIT)
    if userprofile:
        candidates.extend([
            str(Path(userprofile) / "scoop" / "shims" / "luajit.exe"),
            str(Path(userprofile) / "scoop" / "apps" / "luajit" / "current" / "luajit.exe"),
            str(Path(userprofile) / "AppData" / "Local" / "Programs" / "LuaJIT" / "bin" / "luajit.exe"),
        ])
    for c in candidates:
        p = Path(c)
        if p.exists():
            return str(p.resolve())
    return ""

def _project_family_root() -> Path:
    return PROJECT_ROOT.parent.parent

def _sibling_engine_roots() -> list[Path]:
    family = _project_family_root()
    if not family.exists():
        return []
    roots = []
    for version_dir in family.glob("poe2-synergy-finder-v*"):
        p = version_dir / "poe2-synergy-finder" / "engine"
        if p.exists():
            roots.append(p)
    return sorted(roots, key=lambda p: str(p).lower(), reverse=True)


def _bounded_checkout_search(root: Path, max_depth: int = 5, max_dirs: int = 1400) -> list[Path]:
    """Find old/moved PathOfBuilding-PoE2 checkouts without scanning a whole drive."""
    try:
        root = root.resolve()
    except Exception:
        return []
    if not root.exists() or not root.is_dir():
        return []
    found: list[Path] = []
    seen_dirs = 0
    skip = {".git", "node_modules", "__pycache__", "backups", "database", "snapshots"}
    for current, dirs, _files in os.walk(root, onerror=lambda _e: None):
        seen_dirs += 1
        if seen_dirs > max_dirs:
            break
        here = Path(current)
        try:
            depth = len(here.relative_to(root).parts)
        except Exception:
            depth = max_depth
        dirs[:] = [d for d in dirs if d not in skip and not d.startswith(".")]
        if here.name.casefold() == "pathofbuilding-poe2".casefold():
            candidate = here / "src"
            if _valid_pob_src(candidate):
                found.append(candidate)
            dirs[:] = []
            continue
        if depth >= max_depth:
            dirs[:] = []
    return found


def _portable_search_roots() -> list[Path]:
    roots = [PROJECT_ROOT.parent, _project_family_root()]
    user = os.environ.get("USERPROFILE")
    onedrive = os.environ.get("OneDrive") or os.environ.get("ONEDRIVE")
    if user:
        roots.append(Path(user) / "Documents")
    if onedrive:
        roots.append(Path(onedrive) / "Documents")
    result = []
    seen = set()
    for root in roots:
        try:
            key = str(root.resolve()).casefold()
        except Exception:
            continue
        if key not in seen and root.exists():
            seen.add(key); result.append(root)
    return result

def _pob_install_candidates() -> list[Path]:
    out = []
    appdata = os.environ.get("APPDATA")
    local = os.environ.get("LOCALAPPDATA")
    user = os.environ.get("USERPROFILE")

    roots = [
        LOCAL_POB_CHECKOUT / "src",
        USER_POB_CHECKOUT / "src",
    ]
    if appdata:
        roots.extend([
            Path(appdata) / "Path of Building Community (PoE2)",
            Path(appdata) / "Path of Building Community",
        ])
    if local:
        roots.extend([
            Path(local) / "Path of Building Community (PoE2)",
            Path(local) / "Programs" / "Path of Building Community (PoE2)",
        ])
    if user:
        roots.extend([
            Path(user) / "Documents" / "PathOfBuilding-PoE2" / "src",
            Path(user) / "Projects" / "PathOfBuilding-PoE2" / "src",
            Path(user) / "Downloads" / "PathOfBuilding-PoE2" / "src",
        ])

    for engine_root in _sibling_engine_roots():
        roots.append(engine_root / "PathOfBuilding-PoE2" / "src")

    # Fast exact candidates first.
    for r in roots:
        if _valid_pob_src(r):
            out.append(r)
        for suffix in ("src", "program", "app"):
            candidate = r / suffix
            if _valid_pob_src(candidate):
                out.append(candidate)

    # If the project was moved/copied in a custom folder, search only a bounded
    # set of nearby/Documents roots when the exact candidates did not work.
    if not out:
        for root in _portable_search_roots():
            out.extend(_bounded_checkout_search(root))
            if out:
                break

    seen = set()
    result = []
    for p in out:
        try:
            key = str(p.resolve()).casefold()
        except Exception:
            key = str(p).casefold()
        if key not in seen:
            seen.add(key)
            result.append(p)
    return result

def _runtime_candidates(pob_src: Path | None = None) -> list[Path]:
    values = []
    if pob_src:
        # checkout, portable and installed-GUI layouts
        values.append(pob_src.parent / "runtime")
        values.append(pob_src / "runtime")
        values.append(pob_src)

    # Keep GUI install as a fallback for DLL discovery only; it is not a valid
    # source checkout unless its sibling runtime/lua exists.
    appdata = os.environ.get("APPDATA")
    if appdata:
        values.extend([
            Path(appdata) / "Path of Building Community (PoE2)",
            Path(appdata) / "Path of Building Community",
        ])

    seen = set()
    result = []
    for p in values:
        if p.exists():
            key = str(p).lower()
            if key not in seen:
                seen.add(key)
                result.append(p)
    return result

def auto_detect(save=True) -> dict:
    cfg, _repaired = _repair_moved_project_config(load_config(), persist=False)

    lua = _expand(cfg.get("luajit_path"))
    if not (lua and lua.exists()):
        cfg["luajit_path"] = _find_luajit()

    pob = _expand(cfg.get("pob_src_path"))
    if not _valid_pob_src(pob):
        # The runtime field often already points at the packaged PoB install in
        # %APPDATA%.  In that layout Launch.lua/Modules and lua/xml.lua live in
        # the SAME directory, so try it before doing a broader search.
        runtime_hint = _expand(cfg.get("runtime_dll_path"))
        hinted = []
        if runtime_hint:
            hinted.extend([runtime_hint, runtime_hint / "program", runtime_hint / "src"])
        candidates = [x for x in hinted if _valid_pob_src(x)]
        if not candidates:
            candidates = _pob_install_candidates()
        cfg["pob_src_path"] = str(candidates[0]) if candidates else ""

    pob = _expand(cfg.get("pob_src_path"))
    runtime = _expand(cfg.get("runtime_dll_path"))
    program_runtime = _runtime_root_from_src(pob) if pob else None
    if program_runtime:
        cfg["runtime_dll_path"] = str(program_runtime)
    elif not (runtime and runtime.exists() and _valid_runtime_lua_dir(runtime / "lua")):
        candidates = [x for x in _runtime_candidates(pob) if _valid_runtime_lua_dir(x / "lua")]
        cfg["runtime_dll_path"] = str(candidates[0]) if candidates else ""

    bridge = _expand(cfg.get("bridge_path"))
    if not _valid_bridge(bridge):
        sibling_bridge = next(
            (r / "pob-api" for r in _sibling_engine_roots() if _valid_bridge(r / "pob-api")),
            None,
        )
        cfg["bridge_path"] = str(sibling_bridge or BRIDGE_DIR)

    if save:
        save_config(cfg)
    return setup_status(cfg)

def _check_luajit_version(path: Path | None) -> dict:
    if not (path and path.exists()):
        return {"ok": False, "detail": "LuaJIT não encontrado."}
    try:
        p = subprocess.run(
            [str(path), "-v"],
            capture_output=True,
            text=True,
            timeout=4,
        )
        output = (p.stdout or p.stderr or "").strip()
        return {"ok": p.returncode == 0, "detail": output or f"exit {p.returncode}"}
    except Exception as exc:
        return {"ok": False, "detail": str(exc)}

def _check_pob_luajit_syntax(lua: Path | None, pob_src: Path | None) -> dict:
    """
    Compile a representative PoB module with the same LuaJIT we will use.
    This catches moving-dev syntax (for example `??`) before launching PoB.
    """
    if not (lua and lua.exists()):
        return {"ok": False, "detail": "LuaJIT não disponível para teste."}
    if not (pob_src and (pob_src / "Modules" / "Main.lua").exists()):
        return {"ok": False, "detail": "Modules/Main.lua não encontrado."}
    try:
        out = os.devnull
        p = subprocess.run(
            [str(lua), "-b", str(pob_src / "Modules" / "Main.lua"), out],
            cwd=str(pob_src),
            capture_output=True,
            text=True,
            timeout=8,
        )
        detail = (p.stderr or p.stdout or "").strip()
        return {
            "ok": p.returncode == 0,
            "detail": detail or "Modules/Main.lua é compatível com este LuaJIT.",
        }
    except Exception as exc:
        return {"ok": False, "detail": str(exc)}

def setup_status(config=None) -> dict:
    if config is None:
        cfg, repaired = _repair_moved_project_config(load_config(), persist=True)
    else:
        cfg, repaired = _repair_moved_project_config(config, persist=False)
    lua = _expand(cfg.get("luajit_path"))
    pob = _expand(cfg.get("pob_src_path"))
    runtime = _expand(cfg.get("runtime_dll_path"))
    bridge = _expand(cfg.get("bridge_path")) or BRIDGE_DIR

    lua_check = _check_luajit_version(lua)
    pob_ok = _valid_pob_src(pob)
    syntax_check = _check_pob_luajit_syntax(lua, pob) if pob_ok else {
        "ok": False,
        "detail": "Aguardando checkout PoB2 válido."
    }
    bridge_ok = _valid_bridge(bridge)

    runtime_files = []
    runtime_lua_ok = False
    runtime_lua_dir = None
    if runtime and runtime.exists():
        for name in ("lua-utf8.dll", "lzip.dll", "lcurl.dll", "lua51.dll"):
            if (runtime / name).exists():
                runtime_files.append(name)
        runtime_lua_dir = runtime / "lua"
        runtime_lua_ok = _valid_runtime_lua_dir(runtime_lua_dir)

    headless_local = bool(
        (pob / "HeadlessWrapper.lua").exists() if pob else False
    )
    headless_bridge = bool((bridge / "HeadlessWrapper.lua").exists())

    return {
        "config": cfg,
        "repaired_paths": repaired,
        "checks": {
            "luajit": {
                "ok": bool(lua_check["ok"]),
                "path": str(lua) if lua else "",
                "detail": lua_check["detail"],
            },
            "pob_src": {
                "ok": pob_ok,
                "path": str(pob) if pob else "",
                "detail": (
                    "Programa PoB2 completo: Launch.lua, Modules e runtime Lua compatível encontrados."
                    if pob_ok
                    else (
                        "Launch.lua/Modules com runtime Lua compatível não foram localizados. "
                        "Use 'Detectar / reparar caminhos' ou 'Baixar PoB2 headless'."
                    )
                ),
            },
            "pob_syntax": {
                "ok": bool(syntax_check["ok"]),
                "path": str(pob / "Modules" / "Main.lua") if pob else "",
                "detail": syntax_check["detail"],
            },
            "runtime": {
                "ok": bool(runtime and runtime.exists() and runtime_lua_ok),
                "path": str(runtime) if runtime else "",
                "files": runtime_files,
                "runtime_lua": str(runtime_lua_dir) if runtime_lua_dir else "",
                "xml_module": bool(runtime_lua_dir and (runtime_lua_dir / "xml.lua").exists()),
                "detail": (
                    f"runtime/lua válido (xml.lua encontrado); {len(runtime_files)} DLL(s) reconhecida(s)."
                    if runtime and runtime.exists() and runtime_lua_ok
                    else (
                        "Runtime encontrado, mas runtime/lua/xml.lua está ausente. "
                        "A instalação GUI sozinha não basta para o modo headless."
                        if runtime and runtime.exists()
                        else "Runtime do checkout headless não localizado."
                    )
                ),
            },
            "bridge": {
                "ok": bridge_ok,
                "path": str(bridge),
                "headless_in_pob": headless_local,
                "headless_in_bridge": headless_bridge,
                "detail": (
                    "Bridge stdio encontrado."
                    if bridge_ok else "Bridge stdio ainda não foi baixado."
                ),
            },
        },
        "pob_channel": POB2_CHANNEL,
        "ready": bool(
            lua_check["ok"] and pob_ok and syntax_check["ok"] and runtime_lua_ok
            and bridge_ok and (headless_local or headless_bridge)
        ),
    }

def _safe_extract_zip(zf: zipfile.ZipFile, target: Path):
    target = target.resolve()
    for member in zf.infolist():
        dest = (target / member.filename).resolve()
        if target not in dest.parents and dest != target:
            raise EngineError(f"ZIP contém caminho inseguro: {member.filename}")
    zf.extractall(target)

def install_pob_checkout() -> dict:
    """
    Download a clean official dev-branch checkout as a GitHub ZIP.
    Git is not required.
    """
    req = urllib.request.Request(
        POB2_ARCHIVE_URL,
        headers={"User-Agent": "PoE2-Synergy-Finder/0.11.3"},
    )
    with urllib.request.urlopen(req, timeout=90) as response:
        payload = response.read()

    # Keep new downloads in a stable per-user location so moving or renaming
    # the Finder project does not break the PoB source/runtime paths.
    target_checkout = USER_POB_CHECKOUT
    USER_ENGINE_DIR.mkdir(parents=True, exist_ok=True)
    temp_root = USER_ENGINE_DIR / "_pob_download"
    if temp_root.exists():
        shutil.rmtree(temp_root)
    temp_root.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            _safe_extract_zip(zf, temp_root)

        dirs = [p for p in temp_root.iterdir() if p.is_dir()]
        if len(dirs) != 1:
            raise EngineError("Estrutura inesperada no ZIP oficial do PoB2.")
        extracted = dirs[0]

        src = extracted / "src"
        runtime_lua = extracted / "runtime" / "lua"
        if not (
            (src / "Launch.lua").exists()
            and (src / "Modules").is_dir()
            and (runtime_lua / "xml.lua").exists()
        ):
            raise EngineError(
                "O ZIP baixado não contém src/Launch.lua + Modules + runtime/lua/xml.lua."
            )

        if target_checkout.exists():
            shutil.rmtree(target_checkout)
        shutil.move(str(extracted), str(target_checkout))
    finally:
        if temp_root.exists():
            shutil.rmtree(temp_root, ignore_errors=True)

    save_config({
        "pob_src_path": str(target_checkout / "src"),
        "runtime_dll_path": str(target_checkout / "runtime"),
    })
    return auto_detect(save=True)

def _download_text(url: str, timeout=30) -> str:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "PoE2-Synergy-Finder/0.11"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read().decode("utf-8")

def install_bridge() -> dict:
    """
    Downloads source files at runtime from upstream projects instead of
    redistributing them inside Synergy Finder.
    """
    BRIDGE_DIR.mkdir(parents=True, exist_ok=True)
    for remote, relative in UPSTREAM_BRIDGE_FILES.items():
        target = BRIDGE_DIR / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            _download_text(UPSTREAM_BRIDGE_BASE + remote),
            encoding="utf-8",
        )

    # The vanilla bootstrap expects HeadlessWrapper.lua in cwd.
    # Keep a copy in the bridge directory; EngineClient can use a generated
    # bootstrap shim if the PoB installation does not contain the wrapper.
    wrapper_text = _download_text(UPSTREAM_HEADLESS)
    (BRIDGE_DIR / "HeadlessWrapper.lua").write_text(
        wrapper_text,
        encoding="utf-8",
    )

    simple_path = BRIDGE_DIR / "_SimpleGraphic.def.lua"
    if "_SimpleGraphic.def.lua" in wrapper_text:
        helper_url = (
            "https://raw.githubusercontent.com/PathOfBuildingCommunity/"
            f"PathOfBuilding-PoE2/{POB2_CHANNEL}/src/_SimpleGraphic.def.lua"
        )
        simple_path.write_text(
            _download_text(helper_url),
            encoding="utf-8",
        )
    elif simple_path.exists():
        simple_path.unlink()

    (BRIDGE_DIR / "UPSTREAM_LICENSE_GPL-3.0.txt").write_text(
        _download_text(UPSTREAM_BRIDGE_LICENSE),
        encoding="utf-8",
    )
    save_config({"bridge_path": str(BRIDGE_DIR)})
    return setup_status()


def _patch_buildops_exact_support_compat(text: str) -> str:
    """Patch upstream BuildOps.get_skills to expose PoB's own support verdict."""
    if "SYNERGY_FINDER_EXACT_SUPPORT_COMPAT" in text:
        return text

    start = text.find("function M.get_skills()")
    end = text.find("\nfunction M.set_main_selection", start)
    if start < 0 or end < 0:
        raise EngineError("BuildOps upstream mudou: get_skills() não localizado.")

    segment = text[start:end]
    pos = segment.rfind("  return result")
    if pos < 0:
        raise EngineError("BuildOps upstream mudou: retorno de get_skills() não localizado.")

    insert_at = start + pos
    lua_block = "\n".join([
        "  -- SYNERGY_FINDER_EXACT_SUPPORT_COMPAT",
        '  result.compatibilitySource = "pob_calcLib.canGrantedEffectSupportActiveSkill"',
        "  result.compatibleSupports = {}",
        "  result.appliedSupports = {}",
        "  result.mainSkillEffectName = nil",
        "",
        "  local env = build.calcsTab and (build.calcsTab.calcsEnv or build.calcsTab.mainEnv) or nil",
        "  local mainSkill = env and env.player and env.player.mainSkill or nil",
        "  if mainSkill then",
        "    if mainSkill.activeEffect and mainSkill.activeEffect.grantedEffect then",
        "      result.mainSkillEffectName = mainSkill.activeEffect.grantedEffect.name",
        "    end",
        "",
        "    local seenApplied = {}",
        "    for _, effect in ipairs(mainSkill.effectList or {}) do",
        "      local ge = effect and effect.grantedEffect",
        "      if ge and ge.support then",
        "        local src = effect.srcInstance",
        "        local n = (src and src.nameSpec) or ge.name",
        "        if n and not seenApplied[n] then",
        "          seenApplied[n] = true",
        "          table.insert(result.appliedSupports, n)",
        "        end",
        "      end",
        "    end",
        "    table.sort(result.appliedSupports)",
        "",
        '    if type(calcLib) == "table" and type(calcLib.canGrantedEffectSupportActiveSkill) == "function" then',
        "      local seenCompat = {}",
        "      for _, gemData in pairs((build.data and build.data.gems) or {}) do",
        "        local ge = gemData and gemData.grantedEffect",
        "        if ge and ge.support then",
        "          local okCheck, compatible = pcall(",
        "            calcLib.canGrantedEffectSupportActiveSkill,",
        "            ge,",
        "            mainSkill",
        "          )",
        "          if okCheck and compatible then",
        "            local n = gemData.name or gemData.nameSpec or ge.name",
        "            if n and not seenCompat[n] then",
        "              seenCompat[n] = true",
        "              table.insert(result.compatibleSupports, n)",
        "            end",
        "          end",
        "        end",
        "      end",
        "      table.sort(result.compatibleSupports)",
        "    end",
        "  end",
        "",
    ])
    return text[:insert_at] + lua_block + text[insert_at:]



def _patch_buildops_calcs_output(text: str) -> str:
    """
    Teach the bridge to export either sidebar/main output or detailed Calcs-tab
    output, and keep mainActiveSkillCalcs synchronized with mainActiveSkill.
    """
    if "SYNERGY_FINDER_CALCS_OUTPUT_V0123" in text:
        return text

    # Replace export_stats with a scope-aware scalar exporter.
    start = text.find("function M.export_stats(fields)")
    end = text.find("\n-- Read current tree", start)
    if start < 0 or end < 0:
        raise EngineError("BuildOps upstream mudou: export_stats não localizado.")

    replacement = "\n".join([
        "function M.export_stats(fields, options)",
        "  -- SYNERGY_FINDER_CALCS_OUTPUT_V0123",
        "  if not build or not build.calcsTab then",
        "    return nil, 'build not initialized'",
        "  end",
        "  if build.calcsTab.BuildOutput then",
        "    build.calcsTab:BuildOutput()",
        "  end",
        "  options = options or {}",
        "  local scope = options.scope or 'main'",
        "  local output",
        "  if scope == 'calcs' then",
        "    output = build.calcsTab.calcsOutput",
        "  else",
        "    output = build.calcsTab.mainOutput",
        "    scope = 'main'",
        "  end",
        "  if not output then",
        "    return nil, 'no output available for scope ' .. tostring(scope)",
        "  end",
        "  local result = {}",
        "  if options.allScalars then",
        "    for k, v in pairs(output) do",
        "      local t = type(v)",
        "      if t == 'number' or t == 'boolean' or t == 'string' then",
        "        result[k] = v",
        "      end",
        "    end",
        "  else",
        "    local wanted = fields or {",
        '      "Life", "EnergyShield", "Mana", "Spirit", "Ward",',
        '      "Armour", "Evasion",',
        '      "FireResist", "ColdResist", "LightningResist", "ChaosResist",',
        '      "BlockChance", "SpellBlockChance",',
        '      "LifeRegen", "ManaRegen",',
        '      "TotalDPS", "FullDPS", "CombinedDPS"',
        "    }",
        "    for _, k in ipairs(wanted) do",
        "      if type(output[k]) ~= 'nil' then",
        "        result[k] = output[k]",
        "      end",
        "    end",
        "  end",
        "  result._meta = result._meta or {}",
        "  result._meta.outputScope = scope",
        "  if build.targetVersion then",
        "    result._meta.treeVersion = tostring(build.targetVersion)",
        "  end",
        "  if build.characterLevel then",
        "    result._meta.level = tonumber(build.characterLevel)",
        "  end",
        "  if build.buildName then",
        "    result._meta.buildName = tostring(build.buildName)",
        "  end",
        "  return result",
        "end",
    ])
    text = text[:start] + replacement + text[end:]

    # Synchronise the active skill used by MAIN and CALCS passes.
    target = (
        "  if params.mainActiveSkill ~= nil then\n"
        "    g.mainActiveSkill = tonumber(params.mainActiveSkill) or g.mainActiveSkill\n"
        "  end"
    )
    replacement2 = (
        "  if params.mainActiveSkill ~= nil then\n"
        "    g.mainActiveSkill = tonumber(params.mainActiveSkill) or g.mainActiveSkill\n"
        "    g.mainActiveSkillCalcs = tonumber(params.mainActiveSkill) or g.mainActiveSkillCalcs or g.mainActiveSkill\n"
        "  end"
    )
    if target not in text:
        raise EngineError(
            "BuildOps upstream mudou: set_main_selection/mainActiveSkill não localizado."
        )
    text = text.replace(target, replacement2, 1)

    return text


def _patch_handlers_calcs_output(text: str) -> str:
    """Pass output scope/allScalars from JSON-RPC to BuildOps.export_stats."""
    if "SYNERGY_FINDER_CALCS_HANDLER_V0123" in text:
        return text

    old = "\n".join([
        "handlers.get_stats = function(params)",
        "  local fields = params and params.fields or nil",
        "  local stats, err = BuildOps.export_stats(fields)",
        "  if not stats then",
        "    return { ok = false, error = err }",
        "  end",
        "  return { ok = true, stats = stats }",
        "end",
    ])
    new = "\n".join([
        "handlers.get_stats = function(params)",
        "  -- SYNERGY_FINDER_CALCS_HANDLER_V0123",
        "  local fields = params and params.fields or nil",
        "  local options = {",
        "    scope = params and params.scope or 'main',",
        "    allScalars = params and params.allScalars == true or false,",
        "  }",
        "  local stats, err = BuildOps.export_stats(fields, options)",
        "  if not stats then",
        "    return { ok = false, error = err }",
        "  end",
        "  return { ok = true, stats = stats }",
        "end",
    ])
    if old not in text:
        raise EngineError("Handlers upstream mudou: get_stats não localizado.")
    return text.replace(old, new, 1)




def _patch_buildops_native_support_whatif(text: str) -> str:
    if "SYNERGY_FINDER_NATIVE_GEM_WHATIF_V0125" in text:
        return text

    marker = "\n-- Get basic config values."
    pos = text.find(marker)
    if pos < 0:
        raise EngineError("BuildOps upstream mudou: marcador após calc_with não localizado.")

    lua = r'''
-- SYNERGY_FINDER_NATIVE_GEM_WHATIF_V0125
local function sf_scalar_snapshot(output)
  local out = {}
  for k, v in pairs(output or {}) do
    local t = type(v)
    if t == "number" or t == "boolean" or t == "string" then
      out[k] = v
    end
  end
  return out
end

local function sf_support_name(effect)
  local ge = effect and effect.grantedEffect
  local src = effect and effect.srcInstance
  local gd = src and src.gemData
  return (gd and gd.name) or (src and src.nameSpec) or (ge and ge.name)
end

local function sf_simple_mod_rows(modList, cfg, modName)
  local rows = {}
  if not modList or not modList.Tabulate then return rows end

  local ok, tab = pcall(function()
    return modList:Tabulate("INC", cfg, modName)
  end)
  if not ok or type(tab) ~= "table" then return rows end

  for _, entry in ipairs(tab) do
    local mod = entry and (entry.mod or entry)
    if mod then
      table.insert(rows, {
        name = mod.name,
        value = mod.value,
        source = mod.source,
      })
    end
  end
  return rows
end

local function sf_safe_scalar(v)
  local t = type(v)
  if t == "number" or t == "string" or t == "boolean" then
    return v
  end
  if t == "table" then
    if type(v.value) == "number" or type(v.value) == "string" or type(v.value) == "boolean" then
      return v.value
    end
    if v.mod and (
      type(v.mod.value) == "number"
      or type(v.mod.value) == "string"
      or type(v.mod.value) == "boolean"
    ) then
      return v.mod.value
    end
  end
  return nil
end

local function sf_sort_key_rows(rows)
  table.sort(rows, function(a, b)
    return tostring(a.key or a.name or "") < tostring(b.key or b.name or "")
  end)
  return rows
end

local function sf_support_pipeline(effect, env, calcs)
  local ege = effect and effect.grantedEffect
  local src = effect and effect.srcInstance
  local gd = src and src.gemData

  local out = {
    name = (gd and gd.name) or (src and src.nameSpec) or (ege and ege.name),
    id = ege and ege.id or nil,
    gemId = gd and gd.id or nil,
    level = effect and effect.level or nil,
    quality = effect and effect.quality or nil,
    statSets = {},
    mergedMods = {},
    mergeError = nil,
  }
  if not ege then return out end

  for index, set in ipairs(ege.statSets or {}) do
    local detail = {
      index = index,
      label = set.label,
      constantStats = {},
      statMapKeys = {},
      builtStats = {},
      buildError = nil,
    }

    for _, pair in ipairs(set.constantStats or {}) do
      table.insert(detail.constantStats, {
        key = pair[1],
        value = sf_safe_scalar(pair[2]),
      })
    end
    sf_sort_key_rows(detail.constantStats)

    for key, _ in pairs(set.statMap or {}) do
      table.insert(detail.statMapKeys, key)
    end
    table.sort(detail.statMapKeys)

    if calcLib and calcLib.buildSkillInstanceStats then
      local okBuilt, builtOrErr = pcall(
        calcLib.buildSkillInstanceStats,
        effect,
        ege,
        set,
        env and env.useAltGemQualityStats
      )
      if okBuilt and type(builtOrErr) == "table" then
        for key, value in pairs(builtOrErr) do
          local scalar = sf_safe_scalar(value)
          if scalar ~= nil then
            table.insert(detail.builtStats, {
              key = key,
              value = scalar,
            })
          end
        end
        sf_sort_key_rows(detail.builtStats)
      else
        detail.buildError = tostring(builtOrErr)
      end
    else
      detail.buildError = "calcLib.buildSkillInstanceStats unavailable"
    end

    table.insert(out.statSets, detail)
  end

  if calcs and calcs.mergeSkillInstanceMods and env and env.player then
    local supportModList = new("ModList", env.player.modDB)
    local okMerge, mergeErr = pcall(function()
      calcs.mergeSkillInstanceMods(env, supportModList, effect)
    end)
    if okMerge then
      for _, mod in ipairs(supportModList) do
        local value = sf_safe_scalar(mod.value)
        table.insert(out.mergedMods, {
          name = mod.name,
          type = mod.type,
          value = value,
          source = mod.source,
          flags = sf_safe_scalar(mod.flags),
          keywordFlags = sf_safe_scalar(mod.keywordFlags),
        })
      end
      sf_sort_key_rows(out.mergedMods)
    else
      out.mergeError = tostring(mergeErr)
    end
  else
    out.mergeError = "calcs.mergeSkillInstanceMods unavailable"
  end

  return out
end

local function sf_skill_snapshot(env, calcs)
  local actor = env and env.player
  local skill = actor and actor.mainSkill
  local out = {
    name = nil,
    supportNames = {},
    supportDetails = {},
    areaInc = nil,
    areaMore = nil,
    areaPrimaryInc = nil,
    areaSecondaryInc = nil,
    areaTertiaryInc = nil,
    durationInc = nil,
    cooldownRecoveryInc = nil,
    projectileSpeedInc = nil,
    areaMods = {},
    areaPrimaryMods = {},
  }
  if not skill then return out end

  local ae = skill.activeEffect
  local ge = ae and ae.grantedEffect
  out.name = ge and ge.name or nil

  local seen = {}
  for _, effect in ipairs(skill.effectList or {}) do
    local ege = effect and effect.grantedEffect
    if ege and ege.support then
      local n = sf_support_name(effect)
      if n and not seen[n] then
        seen[n] = true
        table.insert(out.supportNames, n)
        local detail = sf_support_pipeline(effect, env, calcs)
        detail.name = n
        detail.modSource = ege.modSource
        table.insert(out.supportDetails, detail)
      end
    end
  end
  table.sort(out.supportNames)

  local ml = skill.skillModList
  local cfg = skill.skillCfg
  if ml then
    local ok, val

    ok, val = pcall(function()
      return ml:Sum("INC", cfg, "AreaOfEffect")
    end)
    if ok then out.areaInc = val end

    ok, val = pcall(function()
      return ml:More(cfg, "AreaOfEffect")
    end)
    if ok then out.areaMore = val end

    ok, val = pcall(function()
      return ml:Sum("INC", cfg, "AreaOfEffect", "AreaOfEffectPrimary")
    end)
    if ok then out.areaPrimaryInc = val end

    ok, val = pcall(function()
      return ml:Sum("INC", cfg, "AreaOfEffect", "AreaOfEffectSecondary")
    end)
    if ok then out.areaSecondaryInc = val end

    ok, val = pcall(function()
      return ml:Sum("INC", cfg, "AreaOfEffect", "AreaOfEffectTertiary")
    end)
    if ok then out.areaTertiaryInc = val end

    ok, val = pcall(function()
      return ml:Sum("INC", cfg, "Duration", "SkillEffectDuration")
    end)
    if ok then out.durationInc = val end

    ok, val = pcall(function()
      return ml:Sum("INC", cfg, "CooldownRecovery")
    end)
    if ok then out.cooldownRecoveryInc = val end

    ok, val = pcall(function()
      return ml:Sum("INC", cfg, "ProjectileSpeed")
    end)
    if ok then out.projectileSpeedInc = val end

    out.areaMods = sf_simple_mod_rows(ml, cfg, "AreaOfEffect")
    out.areaPrimaryMods = sf_simple_mod_rows(ml, cfg, "AreaOfEffectPrimary")
  end

  return out
end

local function sf_find_gem_data(name)
  for _, gd in pairs((build.data and build.data.gems) or {}) do
    if gd and gd.name == name then
      return gd
    end
  end
end

local function sf_is_support_instance(inst)
  local gd = inst and inst.gemData
  local ge = gd and gd.grantedEffect
  return ge and ge.support == true
end

local function sf_current_support_name(inst)
  local gd = inst and inst.gemData
  return (gd and gd.name) or (inst and inst.nameSpec)
end

function M.compare_support_setup_native(params)
  if not build or not build.skillsTab or not build.calcsTab then
    return nil, "build not initialized"
  end
  params = params or {}

  local groupIndex = tonumber(params.groupIndex)
  local names = params.supports
  if not groupIndex then return nil, "missing groupIndex" end
  if type(names) ~= "table" then return nil, "supports must be a table" end
  if #names > 5 then return nil, "maximum 5 supports" end

  local skillSetId = build.skillsTab.activeSkillSetId or 1
  local skillSet = build.skillsTab.skillSets[skillSetId]
  local socketGroup = skillSet and skillSet.socketGroupList[groupIndex]
  if not socketGroup then
    return nil, "socket group not found at index " .. tostring(groupIndex)
  end

  local oldDisplayGroup = build.skillsTab.displayGroup
  build.skillsTab.displayGroup = socketGroup

  build.mainSocketGroup = groupIndex
  build.calcsTab.input.skill_number = groupIndex
  socketGroup.mainActiveSkill = socketGroup.mainActiveSkill or 1
  socketGroup.mainActiveSkillCalcs = socketGroup.mainActiveSkill

  build.calcsTab:BuildOutput()
  local calcFunc, calcBase = build.calcsTab:GetMiscCalculator()
  if not calcFunc or not calcBase then
    build.skillsTab.displayGroup = oldDisplayGroup
    return nil, "PoB GetMiscCalculator unavailable"
  end

  local calcs = build.calcsTab.calcs
  if not calcs or not calcs.initEnv or not calcs.perform then
    build.skillsTab.displayGroup = oldDisplayGroup
    return nil, "PoB calculator module unavailable"
  end

  local baseEnv = calcs.initEnv(build, "CALCULATOR")
  calcs.perform(baseEnv)
  local baseSkill = sf_skill_snapshot(baseEnv, calcs)

  local requested = {}
  local requestedSeen = {}
  for _, rawName in ipairs(names) do
    local name = tostring(rawName)
    local key = string.lower(name)

    if requestedSeen[key] then
      build.skillsTab.displayGroup = oldDisplayGroup
      return nil, "duplicate support: " .. name
    end
    requestedSeen[key] = true

    local gd = sf_find_gem_data(name)
    if not gd or not gd.grantedEffect or not gd.grantedEffect.support then
      build.skillsTab.displayGroup = oldDisplayGroup
      return nil, "support gem not found: " .. name
    end

    if calcLib and calcLib.canGrantedEffectSupportActiveSkill
      and baseEnv.player and baseEnv.player.mainSkill then
      local okCompat, compatible = pcall(
        calcLib.canGrantedEffectSupportActiveSkill,
        gd.grantedEffect,
        baseEnv.player.mainSkill
      )
      if not okCompat or not compatible then
        build.skillsTab.displayGroup = oldDisplayGroup
        return nil, "PoB says support is incompatible: " .. name
      end
    end

    table.insert(requested, gd)
  end

  local gemList = socketGroup.gemList
  local original = copyTable(gemList, true)
  local originalDisplayGemList = socketGroup.displayGemList

  local keepByName = {}
  local currentSupportSlots = {}
  for idx, inst in ipairs(gemList) do
    if sf_is_support_instance(inst) then
      local n = sf_current_support_name(inst)
      table.insert(currentSupportSlots, idx)
      if n then keepByName[string.lower(n)] = idx end
    end
  end

  local requestedByName = {}
  for _, gd in ipairs(requested) do
    requestedByName[string.lower(gd.name)] = gd
  end

  local replacementSlots = {}
  local preserved = {}
  for _, idx in ipairs(currentSupportSlots) do
    local inst = gemList[idx]
    local n = sf_current_support_name(inst)
    local key = n and string.lower(n)
    if key and requestedByName[key] then
      preserved[key] = true
    else
      table.insert(replacementSlots, idx)
    end
  end

  local newSupports = {}
  for _, gd in ipairs(requested) do
    if not preserved[string.lower(gd.name)] then
      table.insert(newSupports, gd)
    end
  end

  local result
  local okRun, runErr = xpcall(function()
    local usedReplacementSlots = 0

    for i, gd in ipairs(newSupports) do
      local idx = replacementSlots[i]
      local gemInstance

      if idx then
        usedReplacementSlots = usedReplacementSlots + 1
        gemInstance = gemList[idx]
      else
        idx = #gemList + 1
        gemList[idx] = {
          level = gd.naturalMaxLevel,
          quality = build.skillsTab.defaultGemQuality or 0,
          count = 1,
          enabled = true,
          enableGlobal1 = true,
          enableGlobal2 = true,
          gemId = gd.id,
          nameSpec = gd.name,
          skillId = gd.grantedEffectId,
          corrupted = build.skillsTab.defaultCorruptionState,
          corruptLevel = build.skillsTab.defaultCorruptionLevel,
        }
        gemInstance = gemList[idx]
      end

      -- These are the exact temporary fields changed by upstream
      -- GemSelectControl:CalcOutputWithThisGem.
      gemInstance.level = build.skillsTab:ProcessGemLevel(gd)
      gemInstance.gemData = gd
      gemInstance.displayEffect = nil
    end

    -- If fewer supports were selected, delete only unused support slots.
    local removeSlots = {}
    for i = usedReplacementSlots + 1, #replacementSlots do
      table.insert(removeSlots, replacementSlots[i])
    end
    table.sort(removeSlots, function(a, b) return a > b end)
    for _, idx in ipairs(removeSlots) do
      table.remove(gemList, idx)
    end

    -- Deliberately no ProcessSocketGroup or BuildOutput here.
    local variantOutput = calcFunc(nil, false, nil)

    -- Fresh environment is diagnostic proof of what really applied.
    local variantEnv = calcs.initEnv(build, "CALCULATOR")
    calcs.perform(variantEnv)
    local variantSkill = sf_skill_snapshot(variantEnv, calcs)

    local requestedNames = {}
    for _, gd in ipairs(requested) do
      table.insert(requestedNames, gd.name)
    end

    local appliedSet = {}
    for _, n in ipairs(variantSkill.supportNames or {}) do
      appliedSet[string.lower(n)] = true
    end

    local rejected = {}
    for _, n in ipairs(requestedNames) do
      if not appliedSet[string.lower(n)] then
        table.insert(rejected, n)
      end
    end

    result = {
      calculator = "PoB GetMiscCalculator / slot-faithful GemSelect preview",
      baseline = sf_scalar_snapshot(calcBase),
      variant = sf_scalar_snapshot(variantOutput),
      baselineSkill = baseSkill,
      variantSkill = variantSkill,
      requestedSupports = requestedNames,
      appliedSupports = variantSkill.supportNames,
      rejectedSupports = rejected,
    }
  end, debug.traceback)

  wipeTable(gemList)
  for _, inst in ipairs(original) do
    table.insert(gemList, copyTable(inst, true))
  end

  socketGroup.displayGemList = originalDisplayGemList
  build.skillsTab.displayGroup = oldDisplayGroup
  build.buildFlag = true
  pcall(function() build.calcsTab:BuildOutput() end)

  if not okRun then
    return nil, runErr
  end
  return result
end
'''
    return text[:pos] + "\n" + lua + text[pos:]



def _patch_handlers_native_support_whatif(text: str) -> str:
    if "SYNERGY_FINDER_NATIVE_GEM_HANDLER_V0125" in text:
        return text

    marker = "\nhandlers.get_config = function(params)"
    pos = text.find(marker)
    if pos < 0:
        raise EngineError("Handlers upstream mudou: marcador get_config não localizado.")

    lua = r'''
handlers.compare_support_setup_native = function(params)
  -- SYNERGY_FINDER_NATIVE_GEM_HANDLER_V0125
  local result, err = BuildOps.compare_support_setup_native(params or {})
  if not result then
    return { ok = false, error = err or "native support comparison failed" }
  end
  return { ok = true, result = result }
end
'''
    return text[:pos] + "\n" + lua + text[pos:]


def _prepare_bridge_overlay(source_bridge: Path) -> Path:
    """Patch a private bridge copy in machine-local storage.

    The project itself may be inside OneDrive.  A previous implementation kept
    this generated overlay under PROJECT_ROOT/engine and deleted it on every
    start. OneDrive or a stale Lua process could hold a directory handle and
    make that delete fail with WinError 5.  The normal target now lives under
    %LOCALAPPDATA%; if even that target is temporarily locked, create a fresh
    sibling overlay for this start instead of failing the whole engine.
    """
    if not _valid_bridge(source_bridge):
        raise EngineError("Bridge de origem inválido.")

    target = BRIDGE_OVERLAY_DIR
    if source_bridge.resolve() == target.resolve():
        raise EngineError("Selecione o bridge de origem, nao a copia temporaria pob-api-v0126.")

    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        try:
            shutil.rmtree(target)
        except OSError as exc:
            # Windows can transiently lock a generated bridge directory.  The
            # overlay is disposable, so use a fresh directory rather than
            # requiring admin rights or asking the user to fight OneDrive.
            if isinstance(exc, PermissionError) or getattr(exc, "winerror", None) in {5, 32}:
                target = target.parent / (
                    f"{target.name}-{os.getpid()}-{time.time_ns()}"
                )
            else:
                raise

    try:
        shutil.copytree(source_bridge, target)
    except OSError as exc:
        if target == BRIDGE_OVERLAY_DIR and (
            isinstance(exc, PermissionError) or getattr(exc, "winerror", None) in {5, 32}
        ):
            target = target.parent / (
                f"{target.name}-{os.getpid()}-{time.time_ns()}"
            )
            shutil.copytree(source_bridge, target)
        else:
            raise

    buildops = target / "API" / "BuildOps.lua"
    patched = _patch_buildops_exact_support_compat(
        buildops.read_text(encoding="utf-8")
    )
    patched = _patch_buildops_calcs_output(patched)
    patched = _patch_buildops_native_support_whatif(patched)
    buildops.write_text(patched, encoding="utf-8")

    handlers = target / "API" / "Handlers.lua"
    patched_handlers = _patch_handlers_calcs_output(
        handlers.read_text(encoding="utf-8")
    )
    patched_handlers = _patch_handlers_native_support_whatif(patched_handlers)
    handlers.write_text(patched_handlers, encoding="utf-8")

    from src.tree_simulator import install_extension
    install_extension(target)
    from src.workbench import install_extension as install_workbench
    install_workbench(target)

    for generated in (
        target / "bootstrap.local.lua",
        target / "HeadlessWrapper.local.lua",
    ):
        if generated.exists():
            generated.unlink()

    return target

def _make_bootstrap_shim(bridge: Path, pob_src: Path) -> Path:
    upstream_bootstrap = (bridge / "bootstrap.lua").read_text(encoding="utf-8")
    upstream_wrapper = (bridge / "HeadlessWrapper.lua").read_text(encoding="utf-8")

    patched_wrapper = upstream_wrapper
    if "_SimpleGraphic.def.lua" in upstream_wrapper:
        helper = bridge / "_SimpleGraphic.def.lua"
        if not helper.exists():
            raise EngineError(
                "HeadlessWrapper requer _SimpleGraphic.def.lua, mas o helper não foi baixado."
            )
        simple_path = str(helper.resolve()).replace("\\", "\\\\")
        patched_wrapper = patched_wrapper.replace(
            'dofile("_SimpleGraphic.def.lua")',
            f'dofile("{simple_path}")',
        )

    local_wrapper = bridge / "HeadlessWrapper.local.lua"
    local_wrapper.write_text(patched_wrapper, encoding="utf-8")

    wrapper_path = str(local_wrapper.resolve()).replace("\\", "\\\\")
    patched_bootstrap = upstream_bootstrap.replace(
        "dofile('HeadlessWrapper.lua')",
        f"dofile('{wrapper_path}')",
    )
    target = bridge / "bootstrap.local.lua"
    target.write_text(patched_bootstrap, encoding="utf-8")
    return target

class EngineError(RuntimeError):
    pass

COMPARE_FIELDS = [
    "TotalDPS","FullDPS","CombinedDPS","SkillDPS","AverageDamage",
    "AverageBurstDamage","WithDotDPS","TotalDot","TotalDotDPS",
    "IgniteDPS","IgniteDamage","BleedDPS","PoisonDPS",
    "Speed","HitSpeed","CastSpeed","CastTime",
    "Cooldown","CooldownTime","SkillCooldown","Duration","SkillDuration",
    "AreaOfEffectMod","AreaOfEffectRadius","AreaOfEffectRadiusMetres",
    "AreaOfEffectRadiusSecondary","AreaOfEffectRadiusSecondaryMetres",
    "AreaOfEffectRadiusTertiary","AreaOfEffectRadiusTertiaryMetres",
    "ManaCost","LifeCost","RageCost",
    "CritChance","EffectiveCritChance","PreEffectiveCritChance","HitChance",
    "IgniteChance","IgniteDuration",
    "Life","EnergyShield","Mana","Spirit","Ward","Armour","Evasion",
    "FireResist","ColdResist","LightningResist","ChaosResist",
    "BlockChance","SpellBlockChance","LifeRegen","ManaRegen",
]

def _support_attribute(gem: dict) -> dict:
    vals = {
        "STR": float(gem.get("reqStr") or 0),
        "DEX": float(gem.get("reqDex") or 0),
        "INT": float(gem.get("reqInt") or 0),
    }
    positive = [k for k,v in vals.items() if v > 0]
    if not positive:
        return {"attribute":"NONE","attributes":[],"weights":vals}
    top = max(vals.values())
    tops = [k for k,v in vals.items() if v == top and v > 0]
    return {
        "attribute": tops[0] if len(tops) == 1 else "HYBRID",
        "attributes": positive,
        "weights": vals,
    }

def _delta_rows(before: dict, after: dict) -> list[dict]:
    rows=[]
    keys=[k for k in COMPARE_FIELDS if k in before or k in after]
    for key in keys:
        a,b=before.get(key),after.get(key)
        if isinstance(a,(int,float)) or isinstance(b,(int,float)):
            av,bv=float(a or 0),float(b or 0)
            delta=bv-av
            rows.append({
                "key":key,"before":a,"after":b,"delta":delta,
                "pct":None if av == 0 else delta/abs(av)*100,
                "changed":abs(delta)>1e-12,
            })
        elif a != b:
            rows.append({"key":key,"before":a,"after":b,"delta":None,"pct":None,"changed":True})
    rows.sort(key=lambda r:(not r["changed"], keys.index(r["key"])))
    return rows


SKILL_METRIC_PRIORITY = [
    "AreaOfEffectMod","AreaOfEffectRadiusMetres",
    "AreaOfEffectModSecondary","AreaOfEffectRadiusSecondaryMetres",
    "AreaOfEffectModTertiary","AreaOfEffectRadiusTertiaryMetres",
    "Duration","DurationSecondary","DurationTertiary","SkillDuration",
    "Cooldown","CooldownTime","SkillCooldown",
    "ManaCost","LifeCost","RageCost",
    "TotalDPS","FullDPS","CombinedDPS","SkillDPS",
    "AverageDamage","AverageHit","AverageBurstDamage","WithDotDPS",
    "TotalDot","TotalDotDPS","IgniteDPS","IgniteDamage",
    "BleedDPS","PoisonDPS","HitSpeed","Speed","CastSpeed","CastTime",
    "ProjectileCount","ProjectileSpeedMod","BounceCount",
    "CritChance","EffectiveCritChance","HitChance","IgniteChance",
    "IgniteDuration",
]

GLOBAL_METRIC_PRIORITY = [
    "Life","EnergyShield","Mana","Spirit","Ward","Armour","Evasion",
    "FireResist","ColdResist","LightningResist","ChaosResist",
    "BlockChance","SpellBlockChance","LifeRegen","ManaRegen",
]

def _scalar_metric_rows(before: dict, after: dict, scope: str, changed_only=True):
    rows=[]
    keys=set(before.keys()) | set(after.keys())
    keys.discard("_meta")
    for key in keys:
        a,b=before.get(key),after.get(key)
        # Numeric and boolean output is safe for mechanical comparison.
        if isinstance(a,bool) or isinstance(b,bool):
            changed=(a != b)
            if changed or not changed_only:
                rows.append({
                    "key":key,"before":a,"after":b,
                    "delta":None,"pct":None,"changed":changed,"scope":scope,
                })
            continue
        if isinstance(a,(int,float)) or isinstance(b,(int,float)):
            av=float(a or 0);bv=float(b or 0)
            delta=bv-av
            changed=abs(delta)>1e-12
            if changed or not changed_only:
                rows.append({
                    "key":key,"before":a,"after":b,"delta":delta,
                    "pct":None if av==0 else delta/abs(av)*100,
                    "changed":changed,"scope":scope,
                })
    priority = SKILL_METRIC_PRIORITY if scope=="skill" else GLOBAL_METRIC_PRIORITY
    rank={k:i for i,k in enumerate(priority)}
    rows.sort(key=lambda r:(rank.get(r["key"],9999),r["key"].casefold()))
    return rows

def _comparison_rows(main_before: dict, main_after: dict, calcs_before: dict, calcs_after: dict):
    # Detailed skill output is authoritative for skill mechanics.
    skill_changed=_scalar_metric_rows(calcs_before,calcs_after,"skill",True)
    seen={r["key"] for r in skill_changed}
    global_changed=[
        r for r in _scalar_metric_rows(main_before,main_after,"character",True)
        if r["key"] not in seen
    ]

    # Keep a concise stable reference set rather than hundreds of unchanged raw keys.
    stable=[]
    for key in SKILL_METRIC_PRIORITY + GLOBAL_METRIC_PRIORITY:
        if key in seen:
            continue
        source_before=calcs_before if key in calcs_before else main_before
        source_after=calcs_after if key in calcs_after else main_after
        scope="skill" if key in calcs_before or key in calcs_after else "character"
        if key not in source_before and key not in source_after:
            continue
        a,b=source_before.get(key),source_after.get(key)
        if (
            (isinstance(a,(int,float,bool)) or isinstance(b,(int,float,bool)))
            and a == b
        ):
            stable.append({
                "key":key,"before":a,"after":b,
                "delta":0 if not isinstance(a,bool) else None,
                "pct":0 if isinstance(a,(int,float)) and not isinstance(a,bool) and a else None,
                "changed":False,"scope":scope,
            })

    return skill_changed + global_changed + stable


def _native_metric_rows(before: dict, after: dict):
    rows = _scalar_metric_rows(before or {}, after or {}, "native", True)
    stable = []
    changed_keys = {r["key"] for r in rows}

    for key in SKILL_METRIC_PRIORITY + GLOBAL_METRIC_PRIORITY:
        if key in changed_keys:
            continue
        if key not in (before or {}) and key not in (after or {}):
            continue
        a = (before or {}).get(key)
        b = (after or {}).get(key)
        if a == b and (
            isinstance(a, (int, float, bool))
            or isinstance(b, (int, float, bool))
        ):
            stable.append({
                "key": key,
                "before": a,
                "after": b,
                "delta": 0 if not isinstance(a, bool) else None,
                "pct": (
                    0
                    if isinstance(a, (int, float))
                    and not isinstance(a, bool)
                    and a
                    else None
                ),
                "changed": False,
                "scope": "native",
            })
    return rows + stable


class EngineClient:
    def __init__(self):
        self.proc: subprocess.Popen | None = None
        self.stdout_q = queue.Queue()
        self.stderr_q = queue.Queue()
        self.lock = threading.RLock()
        self.ready_meta = None
        self.config = None

    def is_running(self):
        return bool(self.proc and self.proc.poll() is None)

    @staticmethod
    def _reader(stream, q):
        try:
            for line in iter(stream.readline, ""):
                q.put(line.rstrip("\r\n"))
        finally:
            try:
                stream.close()
            except Exception:
                pass

    def _await_json(self, timeout=20):
        deadline = time.time() + timeout
        junk = []
        while time.time() < deadline:
            if self.proc and self.proc.poll() is not None and self.stdout_q.empty():
                err = "\n".join(self.stderr_tail(40))
                raise EngineError(f"PoB headless encerrou antes de responder.\n{err}")
            try:
                line = self.stdout_q.get(timeout=0.1)
            except queue.Empty:
                continue
            if not line:
                continue
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                junk.append(line)
        err = "\n".join(self.stderr_tail(40))
        extra = ("\nstdout não-JSON: " + " | ".join(junk[-5:])) if junk else ""
        raise EngineError(f"Timeout aguardando resposta do PoB.{extra}\n{err}")

    def stderr_tail(self, limit=30):
        values = []
        while True:
            try:
                values.append(self.stderr_q.get_nowait())
            except queue.Empty:
                break
        # Put nothing back; diagnostics are a tail.
        return values[-limit:]

    def start(self, config=None):
        with self.lock:
            if self.is_running():
                return self.status()

            st = setup_status(config)
            if not st["ready"]:
                raise EngineError("Pré-requisitos incompletos. Use 'Diagnosticar motor' primeiro.")

            cfg = st["config"]
            lua = _expand(cfg["luajit_path"])
            pob = _expand(cfg["pob_src_path"])
            runtime = _expand(cfg["runtime_dll_path"])
            bridge = _expand(cfg["bridge_path"])
            assert lua and pob and bridge

            runtime_bridge = _prepare_bridge_overlay(bridge)
            bootstrap = runtime_bridge / "bootstrap.lua"
            if not (pob / "HeadlessWrapper.lua").exists():
                bootstrap = _make_bootstrap_shim(runtime_bridge, pob)

            env = os.environ.copy()

            program_runtime = _runtime_root_from_src(pob)
            runtime_roots = []
            seen_runtime = set()
            for r in [program_runtime, runtime]:
                if not (r and r.exists()):
                    continue
                try:
                    key = str(r.resolve()).casefold()
                except Exception:
                    key = str(r).casefold()
                if key in seen_runtime:
                    continue
                seen_runtime.add(key)
                runtime_roots.append(r)

            lua_paths = []
            for r in runtime_roots:
                lua_dir = r / "lua"
                if _valid_runtime_lua_dir(lua_dir):
                    lua_paths += [
                        str(lua_dir / "?.lua"),
                        str(lua_dir / "?" / "init.lua"),
                    ]
            env["LUA_PATH"] = ";".join(lua_paths + [env.get("LUA_PATH", ""), ";;"])

            cpaths = []
            for r in runtime_roots:
                cpaths += [
                    str(r / "?.dll"),
                    str(r / "lib" / "?.dll"),
                ]
            env["LUA_CPATH"] = ";".join(cpaths + [env.get("LUA_CPATH", ""), ";;"])

            creationflags = 0
            if os.name == "nt":
                creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

            self.stdout_q = queue.Queue()
            self.stderr_q = queue.Queue()
            self.proc = subprocess.Popen(
                [str(lua), str(bootstrap)],
                cwd=str(pob),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env=env,
                creationflags=creationflags,
            )
            threading.Thread(
                target=self._reader, args=(self.proc.stdout, self.stdout_q),
                daemon=True
            ).start()
            threading.Thread(
                target=self._reader, args=(self.proc.stderr, self.stderr_q),
                daemon=True
            ).start()

            ready = self._await_json(timeout=35)
            if not ready.get("ok") or not ready.get("ready"):
                self.stop(force=True)
                raise EngineError(f"Bridge iniciou sem ready banner: {ready}")
            self.ready_meta = ready
            self.config = cfg

            ping = self.request("ping", {}, timeout=8)
            if not ping.get("ok"):
                self.stop(force=True)
                raise EngineError(f"PoB iniciou, mas ping falhou: {ping}")
            return self.status()

    def request(self, action: str, params=None, timeout=20):
        with self.lock:
            if not self.is_running():
                raise EngineError("Motor PoB não está rodando.")
            msg = json.dumps(
                {"action": action, "params": params or {}},
                ensure_ascii=False
            )
            try:
                self.proc.stdin.write(msg + "\n")
                self.proc.stdin.flush()
            except Exception as exc:
                raise EngineError(f"Falha enviando comando ao PoB: {exc}") from exc

            result = self._await_json(timeout=timeout)
            if result.get("ok") is False:
                raise EngineError(result.get("error") or f"Ação {action} falhou.")
            return result

    def load_xml(self, xml: str, name="Synergy Finder build"):
        return self.request(
            "load_build_xml",
            {"xml": xml, "name": name},
            timeout=35,
        )

    def calculate_snapshot(self, fields=None):
        stats = self.request(
            "get_stats",
            {"fields": fields} if fields else {},
            timeout=25,
        )
        skills = self.request("get_skills", {}, timeout=15)
        items = self.request("get_items", {}, timeout=15)
        tree = self.request("get_tree", {}, timeout=15)
        config = self.request("get_config", {}, timeout=15)
        info = self.request("get_build_info", {}, timeout=15)
        return {
            "stats": stats.get("stats", {}),
            "skills": skills.get("skills", []),
            "items": items.get("items", []),
            "tree": tree.get("tree", {}),
            "config": config.get("config", {}),
            "build_info": info.get("info", {}),
        }

    def list_support_gems(self, search="", max_results=1600):
        result=self.request("list_gems",{
            "type":"support","search":search or None,
            "maxResults":int(max_results),"dedupeByName":True,
        },timeout=25)
        gems=result.get("result",{}).get("gems",[])
        out=[]
        for gem in gems:
            row=dict(gem);row.update(_support_attribute(row));out.append(row)
        return out

    def get_skill_groups(self):
        return self.request("get_skills",{},timeout=20).get("skills",{})


    def get_compatible_support_gems(self, group_index: int):
        group_index = int(group_index)
        skills = self.get_skill_groups()
        group = next(
            (g for g in skills.get("groups", [])
             if int(g.get("index", 0)) == group_index),
            None,
        )
        if not group:
            raise EngineError(f"Grupo {group_index} não existe.")

        self.request(
            "set_main_selection",
            {
                "mainSocketGroup": group_index,
                "mainActiveSkill": int(group.get("mainActiveSkill") or 1),
            },
            timeout=20,
        )
        skills = self.get_skill_groups()

        if skills.get("compatibilitySource") != "pob_calcLib.canGrantedEffectSupportActiveSkill":
            raise EngineError(
                "A compatibilidade exata do PoB não foi carregada. "
                "Pare e reinicie o motor usando a v0.12.2."
            )

        allowed = {
            str(n).casefold()
            for n in skills.get("compatibleSupports", [])
        }
        catalog = self.list_support_gems(max_results=2500)

        group_after = next(
            (g for g in skills.get("groups", [])
             if int(g.get("index", 0)) == group_index),
            group,
        )
        active = next(
            (g for g in group_after.get("gems", [])
             if g.get("isSupport") is not True),
            None,
        )

        active_tags = set()
        if active:
            active_tags.update(
                str(x).casefold()
                for x in active.get("tagKeys", [])
                if x
            )
            for part in str(active.get("tags") or "").split(","):
                if part.strip():
                    active_tags.add(part.strip().casefold())

        result = []
        for gem in catalog:
            if str(gem.get("name", "")).casefold() not in allowed:
                continue

            tags = {
                str(x).casefold()
                for x in gem.get("tagKeys", [])
                if x
            }
            for part in str(gem.get("tags") or "").split(","):
                if part.strip():
                    tags.add(part.strip().casefold())

            row = dict(gem)
            row["pobCompatible"] = True
            row["sharedTags"] = sorted(
                t for t in (active_tags & tags)
                if t != "support"
            )
            result.append(row)

        # Relevance ordering only. This is not a power score.
        result.sort(
            key=lambda x: (
                -len(x.get("sharedTags", [])),
                str(x.get("name", "")).casefold(),
            )
        )

        return {
            "group_index": group_index,
            "main_skill": (
                active.get("name")
                if active else skills.get("mainSkillEffectName")
            ),
            "supports": result,
            "applied_supports": skills.get("appliedSupports", []),
            "compatibility_source": skills.get("compatibilitySource"),
        }

    def compare_support_setup(self, xml: str, group_index: int, support_names: list[str]):
        names = [str(x).strip() for x in support_names if str(x).strip()]
        if len(names) > 5:
            raise EngineError("O Virtual Linker aceita no máximo 5 supports.")
        if len({x.casefold() for x in names}) != len(names):
            raise EngineError("Não use o mesmo support duas vezes.")

        group_index = int(group_index)
        if group_index < 1:
            raise EngineError("Grupo inválido.")

        catalog = self.list_support_gems(max_results=2500)
        by_name = {str(g.get("name", "")).casefold(): g for g in catalog}
        missing = [n for n in names if n.casefold() not in by_name]
        if missing:
            raise EngineError("O PoB não reconheceu: " + ", ".join(missing))

        try:
            self.load_xml(xml, "Synergy Finder native baseline")
            skills = self.get_skill_groups()
            group = next(
                (
                    g for g in skills.get("groups", [])
                    if int(g.get("index", 0)) == group_index
                ),
                None,
            )
            if not group:
                raise EngineError(f"Grupo {group_index} não existe.")

            self.request(
                "set_main_selection",
                {
                    "mainSocketGroup": group_index,
                    "mainActiveSkill": int(group.get("mainActiveSkill") or 1),
                },
                timeout=20,
            )

            skills = self.get_skill_groups()
            base_group = next(
                (
                    g for g in skills.get("groups", [])
                    if int(g.get("index", 0)) == group_index
                ),
                group,
            )
            base_supports = [
                g for g in base_group.get("gems", [])
                if g.get("isSupport") is True
            ]
            active = [
                g for g in base_group.get("gems", [])
                if g.get("isSupport") is not True
            ]
            if not active:
                raise EngineError("A active skill do grupo não foi reconhecida.")

            native = self.request(
                "compare_support_setup_native",
                {"groupIndex": group_index, "supports": names},
                timeout=60,
            ).get("result", {})

            before = native.get("baseline", {})
            after = native.get("variant", {})
            applied_names = native.get("appliedSupports", [])
            rejected_names = native.get("rejectedSupports", [])

            before_names = [
                g.get("name") for g in base_supports if g.get("name")
            ]
            before_cf = {x.casefold() for x in before_names}
            selected_cf = {x.casefold() for x in names}

            support_meta = []
            for n in names:
                g = by_name[n.casefold()]
                att = _support_attribute(g)
                support_meta.append({
                    "name": g.get("name"),
                    "tier": g.get("tier"),
                    "maxLevel": g.get("maxLevel"),
                    "tags": g.get("tags"),
                    "tagKeys": g.get("tagKeys", []),
                    "attribute": att["attribute"],
                    "attributes": att["attributes"],
                })

            return {
                "group_index": group_index,
                "main_skill": active[0].get("name"),
                "baseline_supports": before_names,
                "selected_supports": names,
                "added_supports": [
                    n for n in names if n.casefold() not in before_cf
                ],
                "removed_supports": [
                    n for n in before_names
                    if n.casefold() not in selected_cf
                ],
                "baseline_stats": before,
                "variant_stats": after,
                "metrics": _native_metric_rows(before, after),
                "baseline_group": base_group,
                "variant_group": None,
                "support_catalog": support_meta,
                "applied_supports": applied_names,
                "rejected_supports": rejected_names,
                "compatibility_source": "PoB GetMiscCalculator + effectList",
                "variant_valid": len(rejected_names) == 0,
                "native_calculator": native.get("calculator"),
                "baseline_skill_probe": native.get("baselineSkill", {}),
                "variant_skill_probe": native.get("variantSkill", {}),
                "output_diagnostics": {
                    "baseline_native_scalars": len(before),
                    "variant_native_scalars": len(after),
                    "baseline_support_effects": len(
                        native.get("baselineSkill", {}).get("supportNames", [])
                    ),
                    "variant_support_effects": len(
                        native.get("variantSkill", {}).get("supportNames", [])
                    ),
                    "baseline_area_mods": len(
                        native.get("baselineSkill", {}).get("areaMods", [])
                    ),
                    "variant_area_mods": len(
                        native.get("variantSkill", {}).get("areaMods", [])
                    ),
                },
            }
        finally:
            try:
                self.load_xml(xml, "Synergy Finder restored baseline")
            except Exception:
                pass


    def stop(self, force=False):
        with self.lock:
            if not self.proc:
                return {"running": False}
            if self.proc.poll() is None and not force:
                try:
                    self.request("quit", {}, timeout=3)
                except Exception:
                    pass
            if self.proc.poll() is None:
                try:
                    self.proc.terminate()
                    self.proc.wait(timeout=3)
                except Exception:
                    try:
                        self.proc.kill()
                    except Exception:
                        pass
            self.proc = None
            self.ready_meta = None
            return {"running": False}

    def status(self):
        return {
            "running": self.is_running(),
            "ready": self.ready_meta,
            "setup": setup_status(self.config),
            "pid": self.proc.pid if self.is_running() else None,
        }

ENGINE = EngineClient()
