"""Visual tree + read-only PoB Calcs. No approximate math replaces engine output."""
from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

from src import tree_simulator as ts
from src.pob_engine import EngineError

MODULE = Path(__file__).with_name('lua') / 'synergy_workbench.lua'
PROTOCOL = 1


def install_extension(overlay: Path) -> None:
    target = overlay / 'API' / 'Handlers.lua'
    text = target.read_text(encoding='utf-8')
    mark = '-- SYNERGY_WORKBENCH_PROTOCOL_1'
    if mark not in text:
        anchor = 'require("API.SynergyTree").install(handlers)'
        if text.count(anchor) != 1:
            raise EngineError('Extensão da árvore não localizada no bridge privado. O PoB não foi modificado.')
        text = text.replace(anchor, anchor + '\n' + mark + '\nrequire("API.SynergyWorkbench").install(handlers)', 1)
    (overlay / 'API' / 'SynergyWorkbench.lua').write_bytes(MODULE.read_bytes())
    target.write_text(text, encoding='utf-8')


def _reply(action: str, params: dict | None = None, timeout: int = 120) -> dict:
    result = ts._response(action, params or {}, timeout=timeout)
    if result.get('workbench_protocol', result.get('visual_protocol')) != PROTOCOL:
        raise EngineError('Pare e inicie o Motor PoB nesta versão para carregar a árvore visual e os cálculos. Não é necessário baixar o motor.')
    return result


def _groups(result: dict) -> None:
    result['groups'] = ts.array(result.get('groups'), 'groups')
    for g in result['groups']:
        g['effects'] = ts.array(g.get('effects'), 'effects')


def visual_context() -> dict:
    with ts.transaction() as build_hash:
        result = _reply('sf_workbench_visual')
        result['nodes'] = ts.array(result.get('nodes'), 'nodes')
        result['edges'] = ts.array(result.get('edges'), 'edges')
        _groups(result)
        for node in result['nodes']:
            node['stats'] = ts.array(node.get('stats'), 'stats')
            node['links'] = ts.array(node.get('links'), 'links')
        for name in ['min_x', 'max_x', 'min_y', 'max_y']:
            value = result.get('bounds', {}).get(name)
            if type(value) not in (int, float) or not math.isfinite(value):
                raise EngineError('Limites da árvore ausentes: geometria não desenhada.')
        result['build_hash'] = build_hash
    result['original_restored'] = True
    return result


def selection(body: Any) -> dict:
    if not isinstance(body, dict):
        raise ValueError('Pedido inválido.')
    params = {}
    for key in ['group_index', 'active_index']:
        if body.get(key) is not None:
            params[key] = ts._positive_integer(body[key], key)
    if body.get('buff_mode') is not None:
        if body['buff_mode'] not in {'UNBUFFED', 'BUFFED', 'COMBAT', 'EFFECTIVE'}:
            raise ValueError('Modo de buffs inválido.')
        params['buff_mode'] = body['buff_mode']
    if body.get('actor') is not None:
        if body['actor'] not in {'player', 'minion'}:
            raise ValueError('Ator inválido.')
        params['actor'] = body['actor']
    if body.get('build_hash') is not None:
        if not isinstance(body['build_hash'], str) or not re.fullmatch('[0-9a-f]{64}', body['build_hash']):
            raise ValueError('Identificação da build inválida; recarregue.')
        params['build_hash'] = body['build_hash']
    return params


# Labels are UI translations. Values/units not in this map are shown as engine keys.
METRICS = {
    'CombinedDPS': ('DPS combinado', 'Dano', ''), 'TotalDPS': ('DPS de hit', 'Dano', ''),
    'FullDPS': ('Full DPS', 'Dano', ''), 'AverageDamage': ('Dano médio', 'Dano', ''),
    'AverageHit': ('Acerto médio', 'Dano', ''), 'IgniteDPS': ('DPS de Ignite', 'Dano ao longo do tempo', ''),
    'TotalDot': ('DoT total', 'Dano ao longo do tempo', ''), 'BleedDPS': ('DPS de sangramento', 'Dano ao longo do tempo', ''),
    'PoisonDPS': ('DPS de veneno', 'Dano ao longo do tempo', ''),
    'Life': ('Vida máxima', 'Recursos', ''), 'LifeUnreserved': ('Vida não reservada', 'Recursos', ''),
    'EnergyShield': ('Escudo de energia', 'Recursos', ''), 'Mana': ('Mana máxima', 'Recursos', ''),
    'ManaUnreserved': ('Mana não reservada', 'Recursos', ''), 'Spirit': ('Spirit', 'Recursos', ''),
    'LifeRegen': ('Regeneração de vida', 'Recursos', '/s'), 'ManaRegen': ('Regeneração de mana', 'Recursos', '/s'),
    'EnergyShieldRegen': ('Regeneração de ES', 'Recursos', '/s'),
    'Armour': ('Armadura', 'Defesa', ''), 'Evasion': ('Evasão', 'Defesa', ''),
    'BlockChance': ('Chance de bloqueio', 'Defesa', '%'), 'SpellBlockChance': ('Bloqueio de spells', 'Defesa', '%'),
    'TotalEHP': ('EHP total', 'Defesa', ''), 'EffectiveHitPool': ('EHP', 'Defesa', ''),
    'FireResist': ('Resistência a fogo', 'Resistências', '%'), 'ColdResist': ('Resistência a frio', 'Resistências', '%'),
    'LightningResist': ('Resistência a raio', 'Resistências', '%'), 'ChaosResist': ('Resistência a caos', 'Resistências', '%'),
    'Str': ('Força', 'Atributos', ''), 'Dex': ('Destreza', 'Atributos', ''), 'Int': ('Inteligência', 'Atributos', ''),
    'CritChance': ('Chance de crítico', 'Acerto e crítico', '%'), 'HitChance': ('Chance de acerto', 'Acerto e crítico', '%'),
    'AreaOfEffectMod': ('Multiplicador de área', 'Área e alcance', '×'),
    'AreaOfEffectRadiusMetres': ('Raio de área', 'Área e alcance', 'm'),
    'AreaOfEffectRadiusSecondaryMetres': ('Raio secundário', 'Área e alcance', 'm'),
    'AreaOfEffectRadiusTertiaryMetres': ('Raio terciário', 'Área e alcance', 'm'),
    'Cooldown': ('Cooldown', 'Ritmo e custo', 's'), 'Duration': ('Duração', 'Ritmo e custo', 's'),
    'Speed': ('Usos por segundo', 'Ritmo e custo', '/s'), 'CastTime': ('Tempo de cast', 'Ritmo e custo', 's'),
    'ManaCost': ('Custo de mana', 'Ritmo e custo', ''), 'LifeCost': ('Custo de vida', 'Ritmo e custo', ''),
    'ProjectileCount': ('Projéteis', 'Projéteis', ''),
}
CATEGORY_ORDER = ['Dano', 'Dano ao longo do tempo', 'Acerto e crítico', 'Área e alcance', 'Ritmo e custo',
                  'Projéteis', 'Recursos', 'Defesa', 'Resistências', 'Atributos', 'Outros outputs do PoB']


def metric_catalog(output: dict, breakdowns: dict, sources: dict) -> list[dict]:
    rows = []
    for key, value in output.items():
        if type(value) not in (int, float, bool, str) or key.startswith('_'):
            continue
        if type(value) in (int, float) and not math.isfinite(value):
            continue
        label, category, unit = METRICS.get(key, (key, 'Outros outputs do PoB', ''))
        rows.append({'key': key, 'label': label, 'category': category, 'unit': unit, 'value': value,
                     'breakdown_available': key in breakdowns, 'modifiers_available': bool(sources.get(key))})
    rank = {name: i for i, name in enumerate(CATEGORY_ORDER)}
    order = {key: i for i, key in enumerate(METRICS)}
    rows.sort(key=lambda r: (rank[r['category']], order.get(r['key'], 10000), r['key']))
    return rows


def calcs(body: dict) -> dict:
    params = selection(body)
    with ts.transaction(params.get('build_hash')) as build_hash:
        result = _reply('sf_workbench_calcs', params)
        output = result.get('output')
        if not isinstance(output, dict) or not output:
            raise EngineError('O PoB não retornou o output de Cálculos. Nenhum valor foi presumido.')
        result['supports'] = ts.array(result.get('supports'), 'supports')
        result['breakdown_keys'] = ts.array(result.get('breakdown_keys'), 'breakdown_keys')
        _groups(result)
        sources = result.get('modifier_sources') or {}
        for key in sources:
            sources[key] = ts.array(sources[key], 'modifier_sources')
        result['modifier_sources'] = sources
        result['metrics'] = metric_catalog(output, result.get('breakdowns') or {}, sources)
        result['build_hash'] = build_hash
        if ts.current_xml()[1] != build_hash:
            raise EngineError('Build trocada durante os cálculos; resultado descartado.')
    result['original_restored'] = True
    result['accuracy_note'] = ('Resultados da versão local do PoB sob as condições exibidas. Não validam mecânicas '
                               'não implementadas no PoB nem garantem DPS/uptime no jogo.')
    return result


def suggestions(body: dict) -> dict:
    params = selection(body)
    if not params.get('build_hash'):
        raise ValueError('Recarregue a árvore antes de avaliar pontos.')
    for key, default, maximum in [('max_points', 2, 5), ('limit', 12, 16)]:
        value = body.get(key, default)
        params[key] = ts._positive_integer(value, key)
        if value > maximum:
            raise ValueError(f'{key}: máximo {maximum}.')
    metric = body.get('metric', 'Life')
    if metric not in {'CombinedDPS', 'IgniteDPS', 'Life', 'EnergyShield', 'Armour', 'Evasion', 'Mana', 'ManaRegen',
                      'AreaOfEffectMod', 'AreaOfEffectRadiusMetres', 'Duration', 'Cooldown', 'ManaCost'}:
        raise ValueError('Métrica de avaliação inválida.')
    params['metric'] = metric
    if not isinstance(body.get('query', ''), str) or len(body.get('query', '')) > 100:
        raise ValueError('Busca deve ter até 100 caracteres.')
    params['query'] = body.get('query', '')
    if not isinstance(body.get('fingerprint'), str) or len(body['fingerprint']) > 200000:
        raise ValueError('Estado da árvore ausente.')
    params['fingerprint'] = body['fingerprint']
    with ts.transaction(params['build_hash']) as build_hash:
        result = _reply('sf_workbench_suggest', params, timeout=180)
        result['rows'] = ts.array(result.get('rows'), 'rows')
        result['errors'] = ts.array(result.get('errors'), 'errors')
        result['control_differences'] = ts.array(result.get('control_differences'), 'control_differences')
        if result['control_differences']:
            raise EngineError('Controle sem alterações divergiu; ranking descartado.')
        for row in result['rows']:
            row['plan'] = ts.normalize_plan(row['plan'])
            row['metrics'] = ts.metric_rows(row['baseline'], row['variant'])
        result['build_hash'] = build_hash
        if ts.current_xml()[1] != build_hash:
            raise EngineError('Build trocada durante avaliação; resultado descartado.')
    result['original_restored'] = True
    result['numeric_check_passed'] = True
    result['point_budget_verified'] = False
    return result
