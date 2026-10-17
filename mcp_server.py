from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

SERVER_NAME = "poe2-synergy-finder"
SERVER_VERSION = "0.19.4"
MCP_VERSION = "2025-06-18"
SUPPORTED_MCP_VERSIONS = ["2025-06-18", "2025-03-26", "2024-11-05"]
ACTIVE_TOOL: str | None = None

# The MCP process never opens the internet. It only talks to the running Finder.
DEFAULT_PORTS = range(8777, 8787)
ENV_URL = "SYNERGY_FINDER_URL"

LOG_PATH = Path(__file__).resolve().parent / "data" / "mcp" / "handshake.log"

def _log(direction: str, payload: Any) -> None:
    """Diagnostic file only; stdout remains protocol-only."""
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(f"{direction} {line}\n")
    except Exception:
        pass



class FinderError(RuntimeError):
    pass


def _configure_mcp_utf8() -> None:
    for name in ("stdin", "stdout", "stderr"):
        stream=getattr(sys,name,None)
        configure=getattr(stream,"reconfigure",None)
        if configure is not None:
            options={"encoding":"utf-8","errors":"strict"}
            if name != "stdin":
                options.update(newline="\n",write_through=True)
            if name == "stderr":
                options["errors"]="backslashreplace"
            configure(**options)


def _stderr(message: str) -> None:
    text="[synergy-mcp] "+str(message)+"\n"
    binary=getattr(sys.stderr,"buffer",None)
    if binary is not None:
        binary.write(text.encode("utf-8",errors="backslashreplace"));binary.flush()
    else:
        sys.stderr.write(text);sys.stderr.flush()


def _json_line(payload: dict) -> None:
    text=json.dumps(payload,ensure_ascii=True,allow_nan=False,separators=(",",":"))+"\n"
    binary=getattr(sys.stdout,"buffer",None)
    if binary is not None:
        binary.write(text.encode("utf-8"));binary.flush()
    else:
        sys.stdout.write(text);sys.stdout.flush()


def _request(url: str, path: str, body: dict | None = None) -> Any:
    full = url.rstrip("/") + path
    headers = {"Accept": "application/json"}
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers.update({
            "Content-Type": "application/json",
            "Origin": url.rstrip("/"),
            "X-Local-App": "poe2-explorer",
        })
    req = urllib.request.Request(full, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=180) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8", "replace"))
            message = payload.get("error") or str(payload)
        except Exception:
            message = str(exc)
        raise FinderError(f"Finder respondeu HTTP {exc.code}: {message}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise FinderError(f"Não consegui falar com o Finder em {url}: {exc}") from exc
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise FinderError("Finder retornou uma resposta que não é JSON.") from exc
    if isinstance(payload, dict) and payload.get("error"):
        raise FinderError(str(payload["error"]))
    return payload


def discover_url() -> str:
    configured=os.environ.get(ENV_URL,"").strip().rstrip("/")
    if configured:
        status=_request(configured,"/api/status")
        if isinstance(status,dict) and status.get("app_version"):
            return configured
        raise FinderError(f"SYNERGY_FINDER_URL não aponta para um Finder válido: {configured}")
    found=[]
    for port in DEFAULT_PORTS:
        url=f"http://127.0.0.1:{port}"
        try:
            status=_request(url,"/api/status")
            if isinstance(status,dict) and status.get("app_version"):
                found.append((url,str(status.get("app_version"))))
        except FinderError:
            continue
    if len(found)==1:
        return found[0][0]
    if len(found)>1:
        detail=", ".join(f"{url} (v{version})" for url,version in found)
        raise FinderError("Há várias instâncias do Synergy Finder abertas: "+detail+". Feche as instâncias antigas e deixe apenas a que contém a build atual. O MCP não escolherá uma build silenciosamente.")
    raise FinderError(
        "PoE2 Synergy Finder não está aberto. Inicie START_POE2_SYNERGY_FINDER.bat "
        "e mantenha a janela aberta antes de usar as ferramentas no Codex."
    )


def get(path: str) -> Any:
    return _request(discover_url(), path)


def post(path: str, body: dict | None = None) -> Any:
    return _request(discover_url(), path, body or {})


def _short_text(value: Any, limit: int = 240) -> str:
    text = "" if value is None else str(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _compact_build(data: dict) -> dict:
    skills = []
    for group in data.get("skills") or []:
        if not isinstance(group, dict):
            continue
        gems = []
        for gem in group.get("gems") or []:
            if isinstance(gem, dict):
                gems.append(gem.get("name") or gem.get("gem_name") or gem.get("skillId") or "?")
            else:
                gems.append(str(gem))
        skills.append({
            "label": group.get("label") or group.get("name"),
            "enabled": group.get("enabled", True),
            "gems": gems[:8],
        })
    items = data.get("items") or {}
    item_rows = []
    if isinstance(items, dict):
        source = items.get("equipped") or items.get("items") or []
        if isinstance(source, dict):
            source = list(source.values())
        for item in source or []:
            if isinstance(item, dict):
                item_rows.append({
                    "slot": item.get("slot") or item.get("slotName"),
                    "name": item.get("name") or item.get("base") or item.get("typeLine"),
                })
    tree = data.get("tree") or {}
    return {
        "level": data.get("level"),
        "class": data.get("class_name") or data.get("class"),
        "ascendancy": data.get("ascendancy"),
        "main_skill": data.get("main_skill"),
        "source": data.get("source") or data.get("source_type"),
        "skills": skills[:20],
        "items": item_rows[:20],
        "tree": {
            "allocated_nodes": tree.get("allocated_nodes"),
            "tree_version": tree.get("tree_version"),
            "specialisations": {
                str(k): len(v or [])
                for k, v in (tree.get("specialisations") or {}).items()
            } if isinstance(tree.get("specialisations"), dict) else {},
        },
    }


def _visual() -> dict:
    return post("/api/workbench/visual", {})


def _find_group(visual: dict, skill: str | None = None) -> tuple[int, int, str]:
    groups = visual.get("groups") or []
    wanted = (skill or "").casefold().strip()
    candidates = []
    for group in groups:
        if not isinstance(group, dict):
            continue
        for effect in group.get("effects") or []:
            if not isinstance(effect, dict):
                continue
            name = str(effect.get("name") or group.get("label") or "")
            candidates.append((int(group.get("index") or 0), int(effect.get("index") or 0), name))
    candidates = [x for x in candidates if x[0] > 0 and x[1] > 0]
    if not candidates:
        raise FinderError("O PoB não retornou nenhuma skill selecionável.")
    if wanted:
        exact = next((x for x in candidates if x[2].casefold() == wanted), None)
        if exact:
            return exact
        partial = next((x for x in candidates if wanted in x[2].casefold()), None)
        if partial:
            return partial
        names = ", ".join(x[2] for x in candidates[:20])
        raise FinderError(f"Skill '{skill}' não encontrada. Algumas disponíveis: {names}")
    return candidates[0]


def _metric_subset(metrics: list[dict], keys: list[str] | None, limit: int = 18) -> list[dict]:
    rows = [m for m in metrics if isinstance(m, dict)]
    if keys:
        wanted = {str(k).casefold() for k in keys}
        rows = [
            m for m in rows
            if str(m.get("key", "")).casefold() in wanted
            or str(m.get("label", "")).casefold() in wanted
        ]
    compact = []
    for m in rows[:limit]:
        compact.append({
            "key": m.get("key"),
            "label": m.get("label"),
            "value": m.get("value"),
            "unit": m.get("unit"),
            "category": m.get("category"),
            "breakdown": bool(m.get("breakdown_available")),
            "sources": bool(m.get("modifiers_available")),
        })
    return compact


def tool_build_summary(args: dict) -> dict:
    current = get("/api/pob/current")
    if not current or current.get("imported") is False:
        raise FinderError("Nenhuma build está carregada no Finder.")
    return _compact_build(current)


def tool_calcs(args: dict) -> dict:
    actor = args.get("actor", "player")
    if actor not in {"player", "minion"}:
        raise FinderError("actor deve ser player ou minion.")
    buff_mode = args.get("buff_mode", "EFFECTIVE")
    if buff_mode not in {"UNBUFFED", "BUFFED", "COMBAT", "EFFECTIVE"}:
        raise FinderError("buff_mode inválido.")
    limit = max(1, min(20, int(args.get("limit") or 18)))
    visual = _visual()
    group, active, name = _find_group(visual, args.get("skill"))
    body = {
        "build_hash": visual.get("build_hash"),
        "group_index": group,
        "active_index": active,
        "actor": actor,
        "buff_mode": buff_mode,
    }
    result = post("/api/workbench/calcs", body)
    keys = args.get("metrics")
    if keys is not None and not isinstance(keys, list):
        raise FinderError("metrics precisa ser uma lista de nomes de métricas.")
    return {
        "skill": result.get("skill") or {"name": name, "group_index": group, "active_index": active},
        "selection": result.get("selection"),
        "metrics": _metric_subset(result.get("metrics") or [], keys, limit),
        "accuracy_note": result.get("accuracy_note"),
        "build_hash": result.get("build_hash"),
    }


def tool_search_passives(args: dict) -> dict:
    visual = _visual()
    query = str(args.get("query") or "").casefold().strip()
    allocated = args.get("allocated")
    max_points = max(1, min(99, int(args.get("max_distance") or 99)))
    limit = max(1, min(30, int(args.get("limit") or 12)))
    rows = []
    for node in visual.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        if allocated is not None and bool(node.get("allocated")) != bool(allocated):
            continue
        dist = node.get("path_distance")
        if isinstance(dist, (int, float)) and dist > max_points:
            continue
        blob = " ".join([
            str(node.get("name") or ""),
            str(node.get("id") or ""),
            " ".join(str(x) for x in node.get("stats") or []),
        ]).casefold()
        if query and query not in blob:
            continue
        rows.append({
            "id": node.get("id"),
            "name": node.get("name"),
            "kind": node.get("kind"),
            "allocated": bool(node.get("allocated")),
            "path_distance": node.get("path_distance"),
            "editable": bool(node.get("editable", True)),
            "blocked_reason": node.get("blocked_reason"),
            "stats": [_short_text(x, 180) for x in (node.get("stats") or [])[:6]],
        })
        if len(rows) >= limit:
            break
    return {
        "query": args.get("query") or "",
        "results": rows,
        "returned": len(rows),
        "note": "path_distance vem do PoB; não é um score de poder.",
    }


def tool_tree_suggestions(args: dict) -> dict:
    allowed_metrics = {"CombinedDPS","IgniteDPS","Life","EnergyShield","Armour","Evasion","Mana","ManaRegen","AreaOfEffectMod","AreaOfEffectRadiusMetres","Duration","Cooldown","ManaCost"}
    metric = args.get("metric", "Life")
    if metric not in allowed_metrics:
        raise FinderError("metric inválida para suggest_tree_paths.")
    visual = _visual()
    group, active, skill_name = _find_group(visual, args.get("skill"))
    body = {
        "build_hash": visual.get("build_hash"),
        "fingerprint": visual.get("fingerprint"),
        "group_index": group,
        "active_index": active,
        "metric": metric,
        "max_points": max(1, min(5, int(args.get("max_points") or 2))),
        "limit": max(1, min(12, int(args.get("limit") or 8))),
        "query": str(args.get("query") or "")[:100],
    }
    result = post("/api/workbench/suggestions", body)
    rows = []
    for row in (result.get("rows") or [])[: body["limit"]]:
        plan = row.get("plan") or {}
        target = plan.get("target") or {}
        rows.append({
            "node_id": row.get("node_id"),
            "name": target.get("name"),
            "cost": abs(plan.get("total_delta") or 0),
            "action": plan.get("action"),
            "before": row.get("before"),
            "after": row.get("after"),
            "delta": row.get("delta"),
            "per_point": row.get("per_point"),
            "path_nodes": [
                {"id": n.get("id"), "name": n.get("name")}
                for n in (plan.get("changes") or [])[:8]
            ],
        })
    return {
        "skill": skill_name,
        "metric": result.get("metric") or body["metric"],
        "eligible": result.get("eligible"),
        "evaluated": result.get("evaluated"),
        "rows": rows,
        "point_budget_verified": bool(result.get("point_budget_verified")),
        "numeric_check_passed": bool(result.get("numeric_check_passed", True)),
        "note": "Amostra local de caminhos próximos; não é otimizador global da árvore.",
    }


def tool_preview_tree_change(args: dict) -> dict:
    mode = args.get("mode", "path")
    if mode not in {"path", "isolated"}:
        raise FinderError("mode deve ser path ou isolated.")
    visual = _visual()
    body = {
        "node_id": int(args["node_id"]),
        "mode": mode,
        "build_hash": visual.get("build_hash"),
    }
    plan = post("/api/tree-sim/preview", body)
    return {
        "target": plan.get("target"),
        "action": plan.get("action"),
        "mode": plan.get("mode"),
        "cost": abs(plan.get("total_delta") or 0),
        "ordinary_delta": plan.get("ordinary_delta"),
        "ascendancy_delta": plan.get("ascendancy_delta"),
        "isolated_hypothesis": bool(plan.get("isolated_hypothesis")),
        "point_budget_verified": bool(plan.get("point_budget_verified")),
        "changes": [
            {"id": n.get("id"), "name": n.get("name"), "stats": (n.get("stats") or [])[:4]}
            for n in (plan.get("changes") or [])[:15]
        ],
        "fingerprint": plan.get("fingerprint"),
        "build_hash": plan.get("build_hash"),
    }


def tool_compare_tree_change(args: dict) -> dict:
    mode = args.get("mode", "path")
    if mode not in {"path", "isolated"}:
        raise FinderError("mode deve ser path ou isolated.")
    visual = _visual()
    group, active, skill_name = _find_group(visual, args.get("skill"))
    preview = post("/api/tree-sim/preview", {
        "node_id": int(args["node_id"]),
        "mode": mode,
        "build_hash": visual.get("build_hash"),
    })
    result = post("/api/tree-sim/compare", {
        "node_id": int(args["node_id"]),
        "mode": mode,
        "build_hash": visual.get("build_hash"),
        "fingerprint": preview.get("fingerprint"),
        "group_index": group,
        "active_index": active,
    })
    changed = []
    keys = args.get("metrics")
    wanted = {str(k).casefold() for k in keys} if isinstance(keys, list) else None
    for row in result.get("metrics") or []:
        if not row.get("changed"):
            continue
        if wanted and str(row.get("key", "")).casefold() not in wanted and str(row.get("label", "")).casefold() not in wanted:
            continue
        changed.append({
            "key": row.get("key"),
            "label": row.get("label"),
            "before": row.get("before"),
            "after": row.get("after"),
            "delta": row.get("delta"),
            "pct": row.get("pct"),
            "comparable": row.get("comparable"),
        })
        if len(changed) >= 20:
            break
    plan = result.get("plan") or {}
    return {
        "skill": skill_name,
        "target": plan.get("target"),
        "action": plan.get("action"),
        "cost": abs(plan.get("total_delta") or 0),
        "changed_metrics": changed,
        "numeric_check_passed": bool(result.get("numeric_check_passed")),
        "original_restored": bool(result.get("original_restored")),
        "point_budget_verified": bool(result.get("point_budget_verified")),
    }


def tool_search_catalog(args: dict) -> dict:
    scope = args.get("scope", "all")
    if scope not in {"supports", "passives", "ascendancies", "all"}:
        raise FinderError("scope inválido.")
    mode = args.get("mode", "all")
    if mode not in {"match", "all", "unknown", "incompatible"}:
        raise FinderError("mode inválido.")
    params = {
        "q": str(args.get("query") or ""),
        "scope": scope,
        "mode": mode,
        "limit": str(max(1, min(30, int(args.get("limit") or 12)))),
        "offset": "0",
    }
    if args.get("kind"):
        params["kind"] = str(args["kind"])
    path = "/api/explore?" + urllib.parse.urlencode(params)
    data = get(path)
    rows = []
    for row in data.get("results") or []:
        rows.append({
            "id": row.get("id"),
            "name": row.get("name"),
            "kind": row.get("kind"),
            "attribute": row.get("attribute"),
            "tags": (row.get("tags") or [])[:10],
            "summary": _short_text(row.get("summary"), 280),
            "compatibility": row.get("compatibility"),
        })
    return {"total": data.get("total"), "results": rows}


def tool_synergies(args: dict) -> dict:
    params = {
        "q": str(args.get("mechanic") or ""),
        "limit": str(max(1, min(12, int(args.get("limit") or 8)))),
        "include_incompatible": "1" if args.get("include_incompatible") else "0",
    }
    path = "/api/interactions?" + urllib.parse.urlencode(params)
    data = get(path)
    groups = []
    for group in data.get("groups") or []:
        groups.append({
            "name": group.get("name"),
            "count": group.get("count"),
            "results": [
                {
                    "id": r.get("id"),
                    "name": r.get("name"),
                    "kind": r.get("kind"),
                    "compatibility": r.get("compatibility"),
                    "evidence": [
                        {
                            "relation": e.get("relation"),
                            "label": e.get("label"),
                            "condition": e.get("condition"),
                        }
                        for e in (r.get("evidence") or [])[:3]
                    ],
                }
                for r in (group.get("results") or [])[:5]
            ],
        })
    paths = []
    for p in (data.get("paths") or [])[:8]:
        paths.append({
            "a": (p.get("a") or {}).get("name"),
            "b": (p.get("b") or {}).get("name"),
            "kind": p.get("kind"),
            "warnings": (p.get("warnings") or [])[:4],
        })
    return {
        "topic": data.get("topic"),
        "entity_count": data.get("entity_count"),
        "groups": groups,
        "candidate_paths": paths,
        "message": data.get("message"),
    }


def _economy(path: str, args: dict, lists=(), flags=(), numbers=None) -> dict:
    params = {}
    for key, value in args.items():
        if value in (None, "", []):
            continue
        if key in lists:
            params[key] = ",".join(str(x) for x in (value if isinstance(value, list) else [value]))
        elif key in flags:
            params[key] = "1" if value else "0"
        elif numbers and key in numbers:
            low, high = numbers[key]
            params[key] = str(max(low, min(high, int(value))))
        else:
            params[key] = str(value)
    return get("/api/economy/" + path + ("?" + urllib.parse.urlencode(params) if params else ""))


def tool_economy_status(args: dict) -> dict:
    return _economy("status", {})


def tool_economy_anchors(args: dict) -> dict:
    data = _economy("anchors", args, lists=("kinds",), flags=("include_plain_reads", "include_universal"),
                    numbers={"limit": (1, 60)})
    for row in data.get("results") or []:
        row["text"] = _short_text(row.get("text"), 260)
    return data


def tool_economy_resource(args: dict) -> dict:
    data = _economy("resource", args, lists=("verbs", "kinds"), numbers={"limit_per_verb": (1, 40)})
    for group in (data.get("by_verb") or {}).values():
        for row in group.get("edges") or []:
            row["text"] = _short_text(row.get("text"), 260)
    return data


def tool_economy_lookup(args: dict) -> dict:
    return _economy("lookup", args, lists=("kinds",), numbers={"limit": (1, 30)})


def tool_verify_anchor(args: dict) -> dict:
    params = {"skill": str(args.get("skill") or ""), "level": str(max(1, min(100, int(args.get("level") or 14))))}
    if args.get("family"):
        params["family"] = str(args["family"])
    return get("/api/lab/verify-anchor?" + urllib.parse.urlencode(params))


def tool_inspect_entity(args: dict) -> dict:
    eid = str(args.get("id") or "").strip()
    if not eid:
        raise FinderError("id obrigatório.")
    data = get("/api/entity?" + urllib.parse.urlencode({"id": eid}))
    return {
        "id": data.get("id"),
        "name": data.get("name"),
        "kind": data.get("kind"),
        "summary": data.get("summary"),
        "tags": data.get("tags"),
        "texts": [
            _short_text(x.get("text") if isinstance(x, dict) else x, 300)
            for x in (data.get("texts") or [])[:12]
        ],
        "links": [
            {
                "relation": x.get("relation"),
                "label": x.get("label"),
                "condition": x.get("condition"),
                "evidence": _short_text(x.get("evidence"), 240),
            }
            for x in (data.get("links") or [])[:20]
        ],
        "stats": [
            {"id": x.get("id"), "value": x.get("value")}
            for x in (data.get("stats") or [])[:20]
        ],
    }


TOOLS = {
    "get_current_build": {
        "description": "Retorna um resumo compacto da build atualmente carregada no PoE2 Synergy Finder. Use primeiro para entender classe, ascendência, skills e quantidade de pontos sem enviar o XML inteiro.",
        "schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "call": tool_build_summary,
    },
    "get_calcs": {
        "description": "Lê os Cálculos reais do PoB para uma skill da build. Retorna só métricas compactas; use metrics para pedir apenas o necessário e economizar contexto.",
        "schema": {
            "type": "object",
            "properties": {
                "skill": {"type": "string", "description": "Nome ou trecho da skill. Omitir usa a primeira skill disponível."},
                "metrics": {"type": "array", "items": {"type": "string"}, "maxItems": 20},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 18},
                "actor": {"type": "string", "enum": ["player", "minion"], "default": "player"},
                "buff_mode": {"type": "string", "enum": ["UNBUFFED", "BUFFED", "COMBAT", "EFFECTIVE"], "default": "EFFECTIVE"},
            },
            "additionalProperties": False,
        },
        "call": tool_calcs,
    },
    "search_passives": {
        "description": "Busca localmente na árvore real carregada pelo PoB e devolve poucos pontos relevantes. Não envia a árvore inteira ao Codex.",
        "schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "allocated": {"type": "boolean", "description": "true = já alocados; false = ainda não alocados."},
                "max_distance": {"type": "integer", "minimum": 1, "maximum": 99},
                "limit": {"type": "integer", "minimum": 1, "maximum": 30, "default": 12},
            },
            "additionalProperties": False,
        },
        "call": tool_search_passives,
    },
    "suggest_tree_paths": {
        "description": "Pede ao Finder para avaliar uma amostra de caminhos próximos da árvore via PoB, por uma única métrica e limite de pontos. É uma busca local limitada, não um otimizador global.",
        "schema": {
            "type": "object",
            "properties": {
                "metric": {"type": "string", "enum": ["CombinedDPS","IgniteDPS","Life","EnergyShield","Armour","Evasion","Mana","ManaRegen","AreaOfEffectMod","AreaOfEffectRadiusMetres","Duration","Cooldown","ManaCost"]},
                "skill": {"type": "string"},
                "max_points": {"type": "integer", "minimum": 1, "maximum": 5, "default": 2},
                "limit": {"type": "integer", "minimum": 1, "maximum": 12, "default": 8},
                "query": {"type": "string", "maxLength": 100},
            },
            "required": ["metric"],
            "additionalProperties": False,
        },
        "call": tool_tree_suggestions,
    },
    "preview_tree_change": {
        "description": "Mostra caminho/dependências e custo de adicionar ou remover um ponto sem calcular números. Não altera a build.",
        "schema": {
            "type": "object",
            "properties": {
                "node_id": {"type": "integer", "minimum": 1},
                "mode": {"type": "string", "enum": ["path", "isolated"], "default": "path"},
            },
            "required": ["node_id"],
            "additionalProperties": False,
        },
        "call": tool_preview_tree_change,
    },
    "compare_tree_change": {
        "description": "Simula no PoB adicionar/remover um ponto (com caminho ou isolado), compara métricas e restaura a build original. Use depois de preview_tree_change quando a mudança for importante.",
        "schema": {
            "type": "object",
            "properties": {
                "node_id": {"type": "integer", "minimum": 1},
                "mode": {"type": "string", "enum": ["path", "isolated"], "default": "path"},
                "skill": {"type": "string"},
                "metrics": {"type": "array", "items": {"type": "string"}, "maxItems": 20},
            },
            "required": ["node_id"],
            "additionalProperties": False,
        },
        "call": tool_compare_tree_change,
    },
    "search_catalog": {
        "description": "Pesquisa a base local RePoE por supports, passivas, ascendências ou toda a base. Retorna um conjunto pequeno e não inventa score de poder.",
        "schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "scope": {"type": "string", "enum": ["supports","passives","ascendancies","all"], "default": "all"},
                "kind": {"type": "string"},
                "mode": {"type": "string", "enum": ["match","all","unknown","incompatible"], "default": "all"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 30, "default": 12},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        "call": tool_search_catalog,
    },
    "search_synergies": {
        "description": "Cruza relações semânticas RePoE para uma mecânica (ex.: Ignite, Area of Effect, Power Charge) e devolve evidências/cadeias candidatas compactas. É descoberta, não cálculo de poder.",
        "schema": {
            "type": "object",
            "properties": {
                "mechanic": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 12, "default": 8},
                "include_incompatible": {"type": "boolean", "default": False},
            },
            "required": ["mechanic"],
            "additionalProperties": False,
        },
        "call": tool_synergies,
    },
    "inspect_entity": {
        "description": "Abre um registro específico da base pelo id retornado por search_catalog/search_synergies, trazendo textos, stats e evidências sem JSON bruto da fonte.",
        "schema": {
            "type": "object",
            "properties": {"id": {"type": "string"}},
            "required": ["id"],
            "additionalProperties": False,
        },
        "call": tool_inspect_entity,
    },
    "economy_status": {
        "description": "Mapa de economia de recursos (método das âncoras): comece aqui. Devolve o método, os verbos e a lista de recursos por categoria.",
        "schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "call": tool_economy_status,
    },
    "economy_anchors": {
        "description": "Âncoras candidatas ranqueadas: efeitos que REPLICAM, LEEM ou CONSOMEM um recurso para dano 'more', ou destravam teto/custo. by_resource mostra onde há mais multiplicadores possíveis. Palpite por regra sobre texto do jogo, não pontuação de poder.",
        "schema": {
            "type": "object",
            "properties": {
                "resource": {"type": "string", "description": "Opcional: limita a um recurso (ex.: power charge, freeze, rage)."},
                "kinds": {"type": "array", "items": {"type": "string"}, "description": "SKILL, SUPPORT, PASSIVE, NOTABLE, KEYSTONE, ASCENDANCY_NODE, META, UNIQUE (uniques do PoB), MOD (mods de item do PoB)."},
                "ascendancy": {"type": "string", "description": "Esconde nós de outras ascendências."},
                "include_plain_reads": {"type": "boolean", "default": False},
                "include_universal": {"type": "boolean", "default": False},
                "limit": {"type": "integer", "minimum": 1, "maximum": 60, "default": 40},
            },
            "additionalProperties": False,
        },
        "call": tool_economy_anchors,
    },
    "economy_resource": {
        "description": "Um recurso em detalhe: quem PRODUCES, CONSUMES, READS, REPLICATES, UNLOCKS, LIMITS e AMPLIFIES, com o texto exato. Use verbs=[PRODUCES, UNLOCKS] para listar conectores de uma âncora.",
        "schema": {
            "type": "object",
            "properties": {
                "resource": {"type": "string"},
                "verbs": {"type": "array", "items": {"type": "string"}},
                "kinds": {"type": "array", "items": {"type": "string"}},
                "ascendancy": {"type": "string"},
                "limit_per_verb": {"type": "integer", "minimum": 1, "maximum": 40, "default": 25},
            },
            "required": ["resource"],
            "additionalProperties": False,
        },
        "call": tool_economy_resource,
    },
    "economy_lookup": {
        "description": "Texto completo de skills, supports e passivas cujo nome ou texto contém a busca, com os recursos e verbos detectados em cada um.",
        "schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "kinds": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer", "minimum": 1, "maximum": 30, "default": 30},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        "call": tool_economy_lookup,
    },
    "verify_anchor": {
        "description": "Mede no PoB, numa build mínima (arma branca, sem supports), quanto o dano de uma skill sobe com cargas e com cada estado do inimigo. Confirma ou derruba uma âncora do mapa: 'specific' são multiplicadores próprios da skill; 'generic' (shock, armadura quebrada) quase toda skill tem. Leva alguns segundos.",
        "schema": {
            "type": "object",
            "properties": {
                "skill": {"type": "string", "description": "Nome exato da skill ativa (ex.: Falling Thunder)."},
                "family": {"type": "string", "description": "Opcional: Quarterstaff, Spear, Mace, Bow, Crossbow, Elemental, Occult, Primal. Define a classe e a arma branca."},
                "level": {"type": "integer", "minimum": 1, "maximum": 100, "default": 14, "description": "Nível do personagem e do inimigo."},
            },
            "required": ["skill"],
            "additionalProperties": False,
        },
        "call": tool_verify_anchor,
    },
}



def _codex_safe_schema(schema: dict) -> dict:
    """
    Codex 0.154.0 can reject otherwise-valid MCP tool schemas containing
    JSON-Schema validation keywords. Keep the exposed schema deliberately
    small and validate/range-limit inside each local tool implementation.
    """
    if not isinstance(schema, dict):
        return {"type": "object", "properties": {}}

    out = {"type": "object", "properties": {}}
    props = schema.get("properties") or {}
    for name, spec in props.items():
        if not isinstance(spec, dict):
            out["properties"][name] = {}
            continue

        item = {}
        typ = spec.get("type")
        if typ in {"string", "integer", "number", "boolean", "object", "array"}:
            item["type"] = typ

        desc = spec.get("description")
        if isinstance(desc, str) and desc:
            item["description"] = desc

        if typ == "array":
            child = spec.get("items") or {}
            child_type = child.get("type") if isinstance(child, dict) else None
            item["items"] = {"type": child_type} if child_type in {"string","integer","number","boolean","object"} else {}

        # Intentionally omit enum/default/minimum/maximum/maxItems/maxLength/
        # additionalProperties. The server enforces semantic constraints.
        out["properties"][name] = item

    required = schema.get("required")
    if isinstance(required, list) and required:
        out["required"] = [str(x) for x in required]

    return out


def _tool_list() -> list[dict]:
    names = [ACTIVE_TOOL] if ACTIVE_TOOL else list(TOOLS)
    return [
        {
            "name": name,
            "description": TOOLS[name]["description"],
            "inputSchema": _codex_safe_schema(TOOLS[name]["schema"]),
        }
        for name in names
        if name in TOOLS
    ]


def _result_text(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def dispatch(message: dict) -> dict | None:
    method = message.get("method")
    request_id = message.get("id")
    params = message.get("params") or {}

    if method == "initialize":
        requested = str(params.get("protocolVersion") or MCP_VERSION)
        # MCP version negotiation: echo the requested version when supported.
        # Codex CLI 0.154.0 currently requests 2025-06-18.
        negotiated = requested if requested in SUPPORTED_MCP_VERSIONS else MCP_VERSION
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": negotiated,
                "capabilities": {
                    "tools": {"listChanged": False}
                },
                "serverInfo": {
                    "name": SERVER_NAME,
                    "title": "PoE2 Synergy Finder",
                    "version": SERVER_VERSION,
                },
                "instructions": (
                    "Use the Synergy Finder tools for compact local PoE2 build analysis. "
                    "PoB is the numerical validator; RePoE is used for mechanical discovery. "
                    "Prefer small tool results and bounded tree suggestions."
                ),
            },
        }

    if method in {
        "notifications/initialized",
        "notifications/cancelled",
        "notifications/roots/list_changed",
    }:
        return None

    if method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "tools": _tool_list()
            },
        }

    if method == "tools/call":
        name = str(params.get("name") or "")
        arguments = params.get("arguments") or {}
        if ACTIVE_TOOL and name != ACTIVE_TOOL:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "isError": True,
                    "content": [{"type": "text", "text": f"Esta instância MCP expõe somente: {ACTIVE_TOOL}"}],
                },
            }
        meta = TOOLS.get(name)
        if meta is None:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "isError": True,
                    "content": [{"type": "text", "text": f"Ferramenta desconhecida: {name}"}],
                },
            }
        try:
            payload = meta["call"](arguments)
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [{"type": "text", "text": _result_text(payload)}],
                    "isError": False,
                },
            }
        except Exception as exc:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "isError": True,
                    "content": [{"type": "text", "text": str(exc)}],
                },
            }

    if method in {"resources/list", "resources/templates/list", "prompts/list"}:
        if method == "resources/templates/list":
            key = "resourceTemplates"
        elif method.startswith("resources"):
            key = "resources"
        else:
            key = "prompts"
        return {"jsonrpc": "2.0", "id": request_id, "result": {key: []}}

    if request_id is not None:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32601, "message": f"Método MCP não suportado: {method}"},
        }
    return None


def serve() -> int:
    _configure_mcp_utf8()
    _stderr("MCP stdio iniciado. O stdout é reservado ao protocolo.")
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            message = json.loads(raw)
            if not isinstance(message, dict):
                raise ValueError("Mensagem JSON-RPC deve ser objeto.")
            _log("IN", message)
            reply = dispatch(message)
            if reply is not None:
                _log("OUT", reply)
                _json_line(reply)
        except Exception as exc:
            _stderr("Mensagem inválida: " + str(exc))
    return 0


def self_test() -> int:
    print("Synergy Finder MCP", SERVER_VERSION)
    print("Protocolos MCP:", ", ".join(SUPPORTED_MCP_VERSIONS))
    print("Ferramentas:", ", ".join([ACTIVE_TOOL] if ACTIVE_TOOL else TOOLS))
    try:
        url = discover_url()
        status = _request(url, "/api/status")
        print("Finder:", url, "v" + str(status.get("app_version")))
        print("OK")
        return 0
    except Exception as exc:
        print("Finder não encontrado:", exc)
        print("O MCP está instalado; abra o Finder antes de usar no Codex.")
        return 2


def main() -> int:
    global ACTIVE_TOOL
    _configure_mcp_utf8()
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--tool", choices=sorted(TOOLS), help="Expõe somente uma tool MCP.")
    args = parser.parse_args()
    ACTIVE_TOOL = args.tool
    return self_test() if args.self_test else serve()


if __name__ == "__main__":
    raise SystemExit(main())
