"""Read-only PoB tree experiments with build identity and restoration checks.

No RePoE hash/ID fallback is used here: candidate IDs come from this PoB's
loaded PassiveSpec. Normal, notable, keystone and current-ascendancy nodes only.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

from src import pob_bridge
from src.pob_engine import ENGINE, EngineError

PROTOCOL = 1
MODULE = Path(__file__).with_name("lua") / "synergy_tree.lua"
PRIORITY = ["CombinedDPS", "TotalDPS", "FullDPS", "IgniteDPS", "Life", "EnergyShield", "Mana",
            "EffectiveHitPool", "TotalEHP", "FireResist", "ColdResist", "LightningResist", "ChaosResist",
            "AreaOfEffectMod", "AreaOfEffectRadiusMetres", "Duration", "Cooldown", "ManaCost",
            "Speed", "Str", "Dex", "Int", "Armour", "Evasion"]
LABELS = {"Life":"Vida", "EnergyShield":"Escudo de energia", "Mana":"Mana", "Str":"Força",
          "Dex":"Destreza", "Int":"Inteligência", "CombinedDPS":"DPS combinado", "TotalDPS":"DPS de hit",
          "FullDPS":"Full DPS", "IgniteDPS":"DPS de Ignite", "Cooldown":"Cooldown",
          "Duration":"Duração", "ManaCost":"Custo de mana", "AreaOfEffectMod":"Multiplicador de área",
          "AreaOfEffectRadiusMetres":"Raio de área (m)", "FireResist":"Resistência a fogo",
          "ColdResist":"Resistência a frio", "LightningResist":"Resistência a raio",
          "ChaosResist":"Resistência a caos", "Armour":"Armadura", "Evasion":"Evasão"}


def install_extension(overlay: Path) -> None:
    """
    Install the tree extension into the private bridge copy, never into PoB.

    Supports both known pob2-mcp module shapes:
      * older:  return handlers
      * current: return { handlers = handlers, version_meta = ... }

    The preferred anchor is the handlers table declaration, so the extension is
    independent from the module's final return syntax.
    """
    target = overlay / "API" / "Handlers.lua"
    text = target.read_text(encoding="utf-8")
    marker = "-- SYNERGY_TREE_PROTOCOL_1"

    if marker not in text:
        block = marker + '\nrequire("API.SynergyTree").install(handlers)\n'

        declarations = list(
            re.finditer(
                r"(?m)^[ \t]*local[ \t]+handlers[ \t]*=[ \t]*\{\}[ \t]*$",
                text,
            )
        )

        if len(declarations) == 1:
            m = declarations[0]
            line_end = text.find("\n", m.end())
            if line_end < 0:
                text = text + "\n" + block
            else:
                line_end += 1
                text = text[:line_end] + block + text[line_end:]

        else:
            # Fallback 1: historical module return.
            old_returns = list(
                re.finditer(r"(?m)^return[ \t]+handlers[ \t]*$", text)
            )
            if len(old_returns) == 1:
                position = old_returns[0].start()
                text = text[:position] + block + text[position:]
            else:
                # Fallback 2: current module return table. Match only top-level
                # `return {` lines and require an exported `handlers = handlers`.
                table_returns = list(
                    re.finditer(r"(?m)^return[ \t]*\{[ \t]*$", text)
                )
                valid = []
                for m in table_returns:
                    tail = text[m.start():]
                    close = re.search(r"(?m)^\}[ \t]*$", tail)
                    if not close:
                        continue
                    block_text = tail[:close.end()]
                    if re.search(
                        r"(?m)^[ \t]+handlers[ \t]*=[ \t]*handlers[ \t]*,?[ \t]*$",
                        block_text,
                    ):
                        valid.append(m)

                if len(valid) == 1:
                    position = valid[0].start()
                    text = text[:position] + block + text[position:]
                else:
                    raise EngineError(
                        "Bridge não reconhecido: não encontrei uma declaração/exportação "
                        "única da tabela handlers. Seu PoB não foi alterado."
                    )

    (overlay / "API" / "SynergyTree.lua").write_bytes(MODULE.read_bytes())
    target.write_text(text, encoding="utf-8")


def array(value: Any, name: str) -> list:
    # The upstream Lua JSON encoder represents an empty table as {}.
    if value == {} or value is None:
        return []
    if not isinstance(value, list):
        raise EngineError(f"Resposta do PoB inválida: {name} não é uma lista.")
    return value


def normalize_plan(plan: dict) -> dict:
    if not isinstance(plan, dict) or plan.get("protocol") != PROTOCOL:
        raise EngineError("Protocolo de árvore ausente. Pare e inicie o motor nesta versão.")
    for key in ("changes", "add_ids", "remove_ids", "required_ids"):
        plan[key] = array(plan.get(key), key)
    for node in plan["changes"]:
        node["stats"] = array(node.get("stats"), "stats")
    plan["target"]["stats"] = array(plan["target"].get("stats"), "stats")
    return plan


def current_xml() -> tuple[str, str]:
    xml = pob_bridge.load_current_xml()
    return xml, hashlib.sha256(xml.encode("utf-8")).hexdigest()


def _response(action: str, params: dict | None = None, timeout: int = 45) -> dict:
    data = ENGINE.request(action, params or {}, timeout=timeout).get("result")
    if not isinstance(data, dict) or data.get("protocol") != PROTOCOL:
        raise EngineError("O motor ativo não tem o módulo de árvore desta versão. Pare e inicie o Motor PoB; não precisa baixar nada.")
    return data


@contextmanager
def transaction(expected_hash: str | None = None):
    """Serialize the *entire* experiment, not individual stdio messages only."""
    with ENGINE.lock:
        if not ENGINE.is_running():
            raise EngineError("Inicie o Motor PoB e volte a Simular pontos. Não precisa reinstalar ou baixar o motor.")
        xml, build_hash = current_xml()
        if expected_hash is not None and expected_hash != build_hash:
            raise EngineError("A build mudou desde a seleção. Clique em Recarregar árvore antes de comparar.")
        stamp = None
        try:
            ENGINE.load_xml(xml, "Synergy Finder - teste de pontos")
            stamp = _response("sf_tree_state")["fingerprint"]
            yield build_hash
        finally:
            # Reload the current source even on failed tests. No secret failures.
            try:
                latest_xml, latest_hash = current_xml()
                ENGINE.load_xml(latest_xml, "Synergy Finder - build original restaurada")
                restored = _response("sf_tree_state")
                if stamp is not None and latest_hash == build_hash and restored["fingerprint"] != stamp:
                    raise EngineError("Alocações não coincidem após restaurar a build.")
            except Exception as exc:
                ENGINE.stop(force=True)
                raise EngineError("Não foi possível verificar a restauração; motor parado por segurança. O arquivo original não foi modificado. " + str(exc)) from exc


def context() -> dict:
    with transaction() as build_hash:
        result = _response("sf_tree_context")
        result["nodes"] = array(result.get("nodes"), "nodes")
        result["groups"] = array(result.get("groups"), "groups")
        for node in result["nodes"]:
            node["stats"] = array(node.get("stats"), "stats")
        for group in result["groups"]:
            group["effects"] = array(group.get("effects"), "effects")
        result["build_hash"] = build_hash
    result["original_restored"] = True
    return result


def _positive_integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} deve ser um inteiro positivo.")
    return value


def validate_params(body: Any, calculate: bool = False) -> dict:
    if not isinstance(body, dict):
        raise ValueError("Pedido inválido.")
    result = {"node_id": _positive_integer(body.get("node_id"), "ID do ponto"), "mode": body.get("mode", "path")}
    if result["mode"] not in {"path", "isolated"}:
        raise ValueError("Modo inválido.")
    if not re.fullmatch(r"[0-9a-f]{64}", str(body.get("build_hash", ""))):
        raise ValueError("Recarregue a árvore: identificação da build ausente.")
    result["build_hash"] = body["build_hash"]
    if calculate:
        for key in ("group_index", "active_index"):
            result[key] = _positive_integer(body.get(key), key)
        if not isinstance(body.get("fingerprint"), str) or len(body["fingerprint"]) > 200000:
            raise ValueError("Identificação da árvore ausente.")
        result["fingerprint"] = body["fingerprint"]
    return result


def preview(body: dict) -> dict:
    params = validate_params(body)
    with transaction(params["build_hash"]) as build_hash:
        result = normalize_plan(_response("sf_tree_plan", params))
        result["build_hash"] = build_hash
    result["original_restored"] = True
    return result


def metric_rows(before: dict, after: dict) -> list[dict]:
    """Missing != zero. Never assign a percentage to an unknown denominator."""
    rows = []
    keys = set(before) | set(after)
    for key in keys:
        a, b = before.get(key), after.get(key)
        numeric = lambda v: type(v) in (int, float) and math.isfinite(v)
        if key.startswith("_") or not (numeric(a) or numeric(b) or isinstance(a, bool) or isinstance(b, bool)):
            continue
        comparable = numeric(a) and numeric(b)
        changed = not math.isclose(a, b, rel_tol=1e-7, abs_tol=1e-7) if comparable else a != b
        delta = b-a if comparable else None
        rows.append({"key":key, "label":LABELS.get(key,key), "before":a, "after":b,
                     "changed":changed, "comparable":comparable, "delta":delta,
                     "pct":(delta/abs(a)*100) if comparable and a != 0 else None})
    order = {key:i for i,key in enumerate(PRIORITY)}
    rows.sort(key=lambda r:(not r["changed"], order.get(r["key"],999), r["key"]))
    return rows


def compare(body: dict) -> dict:
    params = validate_params(body, calculate=True)
    with transaction(params["build_hash"]) as build_hash:
        result = _response("sf_tree_compare", params, timeout=120)
        result["plan"] = normalize_plan(result["plan"])
        result["control_differences"] = array(result.get("control_differences"), "control_differences")
        for key in ("baseline", "variant"):
            if not isinstance(result.get(key), dict) or not result[key]:
                raise EngineError("PoB não retornou valores para comparar. Nenhum resultado foi aprovado.")
        result["metrics"] = metric_rows(result["baseline"], result["variant"])
        result["build_hash"] = build_hash
        result["numeric_check_passed"] = not result["control_differences"]
        result["point_budget_verified"] = False
        if current_xml()[1] != build_hash:
            raise EngineError("A build foi trocada durante o cálculo. Recarregue a árvore; resultado descartado.")
    result["original_restored"] = True
    return result
