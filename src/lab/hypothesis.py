"""Hipótese de patch: medir no PoB 2 atual o que as notas do próximo patch dizem, antes do PoB novo.

Duas formas, que valem para todo motor do laboratório (sessão, `verify_anchor`, juiz, etapas) enquanto a
hipótese estiver ativa:

- `gems`: troca números de gems na memória do PoB (`data.skills`): castTime, cooldown, critChance, baseMultiplier,
  storedUses, damageMultiplier, attackSpeedMultiplier, attackTime, manaCost e spiritReservationFlat (todos os
  níveis, inclusive onde o `statSet` sobrepõe o nível), baseEffectiveness e incrementalEffectiveness do statSet
  (dano base por nível das spells), `scale` de um stat por nível e `constant` de um stat fixo. Nada vai para
  disco; os XML exportados não levam essas trocas.
- `mods`: linhas de mod customizado do PoB ("20% more Damage"), aplicadas na config de cada build. Linha que o
  parser do PoB não entende é recusada (a config a descartaria calada).

Todo número medido com a hipótese ativa é estimativa da hipótese, não do patch: o resultado sai marcado
`hipotese`. Skill, support, keystone ou ascendência nova não é simulável assim.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "lua" / "synergy_hypothesis.lua"
SET_FIELDS = {"castTime", "cooldown", "critChance", "baseMultiplier", "storedUses", "damageMultiplier",
              "attackSpeedMultiplier", "attackTime", "manaCost", "spiritReservationFlat",
              "baseEffectiveness", "incrementalEffectiveness"}

_active: dict | None = None


def install_extension(overlay: Path) -> None:
    from src.pob_engine import EngineError
    target = overlay / "API" / "Handlers.lua"
    text = target.read_text(encoding="utf-8")
    mark = "-- SYNERGY_HYPOTHESIS_PROTOCOL_1"
    if mark not in text:
        anchor = 'require("API.SynergyWorkbench").install(handlers)'
        if text.count(anchor) != 1:
            raise EngineError("Extensão do workbench não localizada no bridge privado. O PoB não foi modificado.")
        text = text.replace(anchor, anchor + "\n" + mark + '\nrequire("API.SynergyHypothesis").install(handlers)', 1)
    (overlay / "API" / "SynergyHypothesis.lua").write_bytes(MODULE.read_bytes())
    target.write_text(text, encoding="utf-8")


def _number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def normalize(raw: dict) -> dict:
    """{nome?, gems?:[{skill, set?, scale?, constant?, statSet?}], mods?:[linhas], fonte?} validado;
    nomes de gem do catálogo viram o id do efeito do PoB (gem_info); ids do PoB passam direto."""
    from src.lab import data
    if not isinstance(raw, dict):
        raise ValueError("hipótese deve ser um objeto {nome, gems, mods, fonte}")
    gems = []
    for g in raw.get("gems") or []:
        if not isinstance(g, dict) or not str(g.get("skill") or "").strip():
            raise ValueError('cada gem precisa de "skill" (nome da gem ou id do efeito no PoB)')
        sets = dict(g.get("set") or {})
        unknown = set(sets) - SET_FIELDS
        if unknown:
            raise ValueError(f"campos desconhecidos em set: {sorted(unknown)}; aceitos: {sorted(SET_FIELDS)}")
        for name, block in (("set", sets), ("scale", g.get("scale") or {}), ("constant", g.get("constant") or {})):
            if not isinstance(block, dict) or not all(_number(v) for v in block.values()):
                raise ValueError(f"{name} deve ser {{campo: número}}")
        skill = str(g["skill"]).strip()
        info = data.gem_info(skill)
        if info:
            skill = info["effect"]  # id do efeito concedido (ex.: FallingThunderPlayer); o Lua confere o resto
        row = {"skill": skill, "set": sets, "scale": dict(g.get("scale") or {}), "constant": dict(g.get("constant") or {})}
        if g.get("statSet") is not None:
            if not isinstance(g["statSet"], int) or isinstance(g["statSet"], bool) or g["statSet"] < 1:
                raise ValueError("statSet deve ser o índice (1, 2, ...) do conjunto de stats")
            row["statSet"] = g["statSet"]
        gems.append(row)
    mods = [str(m).strip() for m in raw.get("mods") or [] if str(m).strip()]
    if not gems and not mods:
        raise ValueError("hipótese vazia: informe gems e/ou mods (use reset para desligar)")
    return {"nome": str(raw.get("nome") or "hipótese").strip(), "fonte": str(raw.get("fonte") or "").strip(),
            "gems": gems, "mods": mods}


def active() -> dict | None:
    return _active


def stamp() -> str:
    """Carimbo do conteúdo: vazio sem hipótese. Serve para separar medidas com hipótese de medidas do PoB."""
    if not _active:
        return ""
    body = json.dumps({"gems": _active["gems"], "mods": _active["mods"]}, sort_keys=True)
    return "hip " + hashlib.sha1(body.encode()).hexdigest()[:12]


def label() -> dict | None:
    if not _active:
        return None
    return {"nome": _active["nome"], "fonte": _active["fonte"], "gems": [g["skill"] for g in _active["gems"]],
            "mods": len(_active["mods"]),
            "aviso": "números medidos com hipótese de patch: estimativa a partir das notas, não o PoB do patch novo"}


def custom_mods() -> str:
    return "\n".join(_active["mods"]) if _active else ""


def apply(lab) -> list[dict]:
    """Aplica a hipótese ativa (ou volta ao PoB instalado) no motor deste Lab; devolve o relatório das gems."""
    out = lab.req("sf_hypothesis_apply", {"gems": _active["gems"] if _active else []})
    if not out.get("ok", True):
        raise ValueError(out.get("error") or "falha ao aplicar a hipótese")
    gems = (out.get("result") or {}).get("gems") or []
    lab.config({"customMods": custom_mods()})
    return gems if isinstance(gems, list) else []


def check_mods(lab, lines: list[str]) -> list[str]:
    """Linhas que o parser do PoB não entende."""
    if not lines:
        return []
    out = lab.req("sf_hypothesis_parse", {"lines": lines})
    if not out.get("ok", True):
        raise ValueError(out.get("error") or "falha ao conferir os mods")
    rows = (out.get("result") or {}).get("rows") or []
    return [r["line"] for r in rows if isinstance(r, dict) and not r.get("ok")]


def set_active(value: dict | None) -> None:
    global _active
    _active = value
