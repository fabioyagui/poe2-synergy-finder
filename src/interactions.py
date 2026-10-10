"""Cross-category mechanical discovery with provenance, not a build/DPS scorer.
A path is a research hypothesis. Its conditions, recipient and source version
remain attached. Incompatible supports and mutually exclusive ascendancies do
not silently become working builds.
"""
from __future__ import annotations
from .semantics import SEMANTIC,PRODUCERS,LABELS
from .importer import concept
from .catalog import compatibility, match

GROUPS=[('produces','Produz / habilita',PRODUCERS),('modifies','Modifica',{'AMPLIFIES','REDUCES','MODIFIES'}),
        ('requires','Requer / consome',{'REQUIRES','CONSUMES'}),('prevents','Impede',{'PREVENTS','PREVENTS_CONSUMPTION'}),
        ('mentions','Só menciona',{'MENTIONS'})]

def build(catalog,q='',skill_id='',component='',include_incompatible=False,ascendancy='',limit=12):
    limit=max(1,min(50,int(limit)))
    skill=catalog.entries.get(skill_id)
    if skill_id and (not skill or skill['kind'] not in {'SKILL','META'}):raise ValueError('Skill selecionada não encontrada.')
    terms={}
    for e in catalog.ordered:
        if not e.get('selectable',True) or e.get('metadata_only'):continue
        for l in e['links']:
            if l['relation'] not in SEMANTIC|{'MENTIONS'}:continue
            d=terms.setdefault(l['concept'],{'key':l['concept'],'name':l['label'],'entities':set(),'semantic':set()})
            d['entities'].add(e['id'])
            if l['relation'] in SEMANTIC:d['semantic'].add(e['id'])
    wanted=concept(q)
    topic=terms.get(wanted)
    if not topic:
        exact=next((d for d in terms.values() if concept(d['name'])==wanted),None)
        topic=exact
    suggestions=[{'key':v['key'],'name':v['name'],'count':len(v['entities']),'semantic_count':len(v['semantic'])}
                 for v in terms.values() if not q or match(v['name'],q) or match(v['key'],q)]
    suggestions.sort(key=lambda v:(-v['semantic_count'],-v['count'],v['name']))
    if not topic:return {'topic':None,'topics':suggestions[:50],'groups':[],'paths':[],
                        'message':'Escolha uma mecânica da base. O catálogo continua pesquisando nomes e stats sem interpretação.'}
    target=topic['key'];rows=[];unverified=0;hidden_incompatible=0
    for e in catalog.ordered:
        if not e.get('selectable',True) or e.get('metadata_only'):continue
        if ascendancy and e.get('ascendancy_id') and e['ascendancy_id']!=ascendancy:continue
        ls=[l for l in e['links'] if l['concept']==target and l['relation'] in SEMANTIC|{'MENTIONS'}]
        if not ls:continue
        comp={'status':'not_applicable','label':'Não é regra de encaixe','reason':'Passivas exigem alocação; disponibilidade no jogo ainda precisa ser conferida.'}
        if e['kind']=='SUPPORT' and skill:
            comp=compatibility(skill,e,component)
            if comp['status']=='incompatible' and not include_incompatible:hidden_incompatible+=1;continue
            if comp['status']=='unknown':unverified+=1
        elif e['kind']=='SUPPORT':comp={'status':'unknown','label':'Sem skill-alvo','reason':'Escolha uma skill para verificar tipos do support.'}
        row={**catalog.brief(e),'evidence':ls,'compatibility':comp,'ascendancy_id':e.get('ascendancy_id',''),
             'ascendancy':e.get('ascendancy',''),'source_version':catalog.version_for(e)}
        rows.append(row)
    grouped=[]
    for key,label,relations in GROUPS:
        group=[]
        for r in rows:
            es=[l for l in r['evidence'] if l['relation'] in relations]
            if key=='mentions' and any(l['relation'] in SEMANTIC for l in r['evidence']):continue
            if not es:continue
            group.append({**r,'evidence':es})
        grouped.append({'key':key,'name':label,'count':len(group),'results':group[:limit]})
    # Controlled two-edge join. No semantic propagation through generic tags,
    # no union of effects and no assertion that every result is a valid build.
    starts=[(r,l) for r in rows for l in r['evidence'] if l['relation'] in PRODUCERS and not str(l.get('scope','')).startswith('minion')]
    ends=[(r,l) for r in rows for l in r['evidence'] if l['relation'] in {'AMPLIFIES','REQUIRES','CONSUMES','PREVENTS'}]
    paths=[];seen=set();exclusive=0
    for a,la in starts:
        for b,lb in ends:
            if a['id']==b['id']:continue
            if any(str(r.get('availability','')).lower() in {'legacy','unreleased','disabled','unavailable'} for r in (a,b)):continue
            if a['compatibility']['status']=='incompatible' or b['compatibility']['status']=='incompatible':continue
            aa=a.get('ascendancy_id');ba=b.get('ascendancy_id')
            if aa and ba and aa!=ba:exclusive+=1;continue
            # A minion modifier cannot improve a player-applied ailment by name alone.
            if lb['relation']=='AMPLIFIES' and str(lb.get('scope','')).startswith('minion') and not str(la.get('scope','')).startswith('minion'):continue
            sig=(a['id'],b['id'],la['relation'],lb['relation'],la['component'],lb['component'])
            if sig in seen:continue
            seen.add(sig)
            warnings=['Hipótese de interação; não é uma build validada nem cálculo de ganho.']
            if la.get('condition') or lb.get('condition'):warnings.append('Condições da fonte ainda precisam ser satisfeitas; veja os dois efeitos completos.')
            if la['relation']=='ENABLES':warnings.append('Chance de aplicação não garante frequência nem uptime.')
            if a['source_version']!=b['source_version'] or not a['source_version'] or not b['source_version']:
                warnings.append('Versões diferentes ou não identificadas: atualize as fontes antes de validar a combinação.')
            for r,l in [(a,la),(b,lb)]:
                if r.get('availability') not in {'released'}:warnings.append(r['name']+': disponibilidade atual não confirmada pela fonte.')
                if r['kind']=='SUPPORT':
                    if r['compatibility']['status']=='unknown':warnings.append(r['name']+': compatibilidade não verificada.')
                    if l['component'] not in {'supported_skill','support','entity'}:warnings.append(r['name']+': alcance do efeito = '+str(l.get('scope',l['component']))+'. Confira se afeta a mesma entidade; não foi transferido automaticamente à skill principal.')
                if r['kind'] in {'PASSIVE','NOTABLE','KEYSTONE','ASCENDANCY_NODE'}:warnings.append(r['name']+': exige alocação; caminho e custo em pontos não calculados.')
            if a['kind']==b['kind']=='SUPPORT':warnings.append('A combinação simultânea de supports não foi simulada; tipos adicionados, grupos e sockets podem mudar a validade.')
            paths.append({'a':a,'b':b,'from_effect':la,'to_effect':lb,'concept':target,'label':topic['name'],
                'kind':'possible_conflict' if lb['relation']=='PREVENTS' else 'consumption' if lb['relation']=='CONSUMES' else 'interaction',
                'warnings':list(dict.fromkeys(warnings))})
            if len(paths)>=32:break
        if len(paths)>=32:break
    return {'topic':{'key':target,'name':topic['name']},'topics':suggestions[:50],'groups':grouped,'paths':paths,
            'entity_count':len(rows),'hidden_incompatible':hidden_incompatible,'unknown_compatibility':unverified,
            'mutually_exclusive_pairs_skipped':exclusive,'path_limit':32,'source_warnings':catalog.source_warnings(),
            'message':'As relações usam evidências de flags, stats ou frases. Uma menção ou tag não cria uma cadeia. Cadeias são candidatas para investigação.'}
