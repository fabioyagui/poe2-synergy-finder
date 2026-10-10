"""Import every recognized gem, with source data, tags and effect boundaries intact.

No reviewed item list. No game-specific build profile. No overwrite of original files.
The small flag vocabulary below describes source flags, not a whitelist of gems.
"""
from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path
from contextlib import nullcontext
from . import storage
from .compatibility import token, OPS

SOURCE = 'RePoE PoE2'
BASE = 'https://repoe-fork.github.io/poe2/'
FILES = ('skill_gems.min.json','skills.min.json','active_skill_types.min.json')

# Deterministic decompositions of explicit flags. Generic types are NOT interpreted
# as producing a condition: Fire does not imply "applies Ignite".
FLAG_RELATIONS = {
    'SKILLCONSUMESIGNITE':('CONSUMES','IGNITE','Ignite'),
    'SKILLCONSUMESFREEZE':('CONSUMES','FREEZE','Freeze'),
    'SKILLCONSUMESSHOCK':('CONSUMES','SHOCK','Shock'),
    'SKILLCONSUMESBLEEDING':('CONSUMES','BLEEDING','Bleeding'),
    'SKILLCONSUMESPOISON':('CONSUMES','POISON','Poison'),
    'SKILLCONSUMESDAZED':('CONSUMES','DAZED','Dazed'),
    'SKILLCONSUMESPOWERCHARGESONUSE':('CONSUMES','POWERCHARGE','Power Charge'),
    'SKILLCONSUMESFRENZYCHARGESONUSE':('CONSUMES','FRENZYCHARGE','Frenzy Charge'),
    'SKILLCONSUMESENDURANCECHARGESONUSE':('CONSUMES','ENDURANCECHARGE','Endurance Charge'),
    'CONSUMESCHARGES':('CONSUMES','CHARGES','Charges'),
    'CONSUMESFULLYBROKENARMOUR':('CONSUMES','FULLYBROKENARMOUR','Fully Broken Armour'),
    'CONSUMESRAGE':('CONSUMES','RAGE','Rage'),
    'GENERATESCHARGES':('GENERATES','CHARGES','Charges'),
    'GENERATESENERGY':('GENERATES','ENERGY','Energy'),
    'GENERATESREMNANTS':('GENERATES','REMNANT','Remnant'),
    'GENERATESINFUSION':('GENERATES','INFUSION','Infusion'),
    'CREATESFISSURE':('CREATES','FISSURE','Fissure'),
    'CREATESGROUNDEFFECT':('CREATES','GROUNDEFFECT','Ground Effect'),
    'CREATESGROUNDRUNE':('CREATES','GROUNDRUNE','Ground Rune'),
    'CANNOTCONSUMECHARGES':('PREVENTS_CONSUMPTION','CHARGES','Charges'),
}
ALIAS = {'IGNITED':'IGNITE','IGNITING':'IGNITE','FROZEN':'FREEZE','BLEED':'BLEEDING',
         'POWERCHARGES':'POWERCHARGE','FRENZYCHARGES':'FRENZYCHARGE',
         'ENDURANCECHARGES':'ENDURANCECHARGE','REMNANTS':'REMNANT','AILMENTS':'AILMENT',
         'CHANNELED':'CHANNELLING','CHANNEL':'CHANNELLING','AOE':'AREA'}
TEXT_FIELDS = {'description','support_text','stat_text','description_text','help_text'}


def concept(value):
    try:
        k=token(value)
        return ALIAS.get(k,k)
    except (ValueError,TypeError): return ''

def plain(text):
    # PoE text markup: [Id|visible text] or [Keyword]. Preserve original separately.
    return re.sub(r'\[([^\[\]]+)\]',lambda m:m.group(1).split('|')[-1],str(text))

def sources(r):
    if not isinstance(r,dict): return
    yield r
    for k in ('active_skill','support_gem','skill','granted_effect'):
        nested=r.get(k)
        if isinstance(nested,dict):
            yield nested
            for kk in ('active_skill','support_gem'):
                if isinstance(nested.get(kk),dict): yield nested[kk]

def field(records,key):
    for r in records:
        for s in sources(r):
            if key in s: return s[key]
    return None

def located(records, key):
    """Return both value and its real source path, without flattening effects."""
    for record, prefix in records:
        parts=[(record,prefix)]
        for k in ('active_skill','support_gem','skill','granted_effect'):
            child=record.get(k)
            if isinstance(child,dict):
                parts.append((child,prefix+'.'+k))
                for kk in ('active_skill','support_gem'):
                    if isinstance(child.get(kk),dict):parts.append((child[kk],prefix+'.'+k+'.'+kk))
        for obj,path in parts:
            if key in obj:return obj[key],path+'.'+key
    return None,None

def walk(value,path='',depth=0):
    if depth>35: return
    if isinstance(value,dict):
        for k,v in value.items():
            p=f'{path}.{k}' if path else str(k)
            yield p,str(k),v
            if isinstance(v,(dict,list)): yield from walk(v,p,depth+1)
    elif isinstance(value,list):
        for i,v in enumerate(value):
            p=f'{path}[{i}]'
            if isinstance(v,(dict,list)): yield from walk(v,p,depth+1)
            else: yield p,str(i),v

def texts(r,prefix):
    result=[]; seen=set()
    for path,k,v in walk(r,prefix):
        if k not in TEXT_FIELDS: continue
        items=[(path,v)] if isinstance(v,str) else [
            (p,x) for p,_,x in walk(v,path) if isinstance(x,str)
        ] if isinstance(v,(dict,list)) else []
        for p,x in items:
            if not x.strip() or x in seen: continue
            seen.add(x)
            result.append({'path':p,'text':plain(x),'original':x})
    return result

def stats(r,prefix):
    # Keep values/units exactly as exposed; no level/DPS inference.
    out=[]; seen=set()
    for path,k,v in walk(r,prefix):
        if not any(x in path.lower() for x in ('stat','quality','cost','cooldown','damage_effectiveness','crit_chance','cast_time','requirement')):
            continue
        if k in {'stats','stat_sets','statsets','stat_text','stat_requirements'}: continue
        if isinstance(v,(dict,list)):
            if isinstance(v,dict) and any(isinstance(v.get(x),str) for x in ('stat','stat_id','id')):
                sid=v.get('stat') or v.get('stat_id') or v.get('id')
                sig=(path,str(sid))
                if sig not in seen:
                    seen.add(sig);out.append({'path':path,'id':str(sid),'value':v})
            continue
        if k in {'description','support_text','text','stat_text','string'}: continue
        if v is None: continue
        # Searchable technical evidence, not an interpretation of its sign or unit.
        if isinstance(v,(str,int,float,bool)):
            sid=str(v) if k in {'id','stat','stat_id'} or k.isdigit() and isinstance(v,str) else k
            out.append({'path':path,'id':sid,'value':v})
    return out

def type_dictionary(data):
    # A string list is a vocabulary, NOT enough evidence to choose a numeric index base.
    out={}
    if isinstance(data,dict):
        for k,v in data.items():
            if isinstance(v,int): out[str(v)]=str(k)
            elif isinstance(v,str): out[str(k)]=v
            elif isinstance(v,dict):
                name=v.get('name') or v.get('id')
                if isinstance(name,str): out[str(k)]=name
    return out

def sequence(v,type_map):
    if not isinstance(v,list): return None
    out=[]
    for x in v:
        if isinstance(x,int) or isinstance(x,str) and x.isdigit(): x=type_map.get(str(x))
        if not isinstance(x,str): return None
        try: token(x)
        except ValueError:return None
        out.append(x)
    return out

def attribute(r):
    explicit=str(r.get('color') or '').lower()
    if explicit in {'r','g','b','w'}:
        return {'color':explicit,'attribute':{'r':'STR','g':'DEX','b':'INT','w':'NEUTRO'}[explicit],
                'color_source':'gem.color','weights':r.get('requirement_weights',{})}
    weights=r.get('requirement_weights')
    if isinstance(weights,dict):
        nums={k:float(v) for k,v in weights.items() if k in {'strength','dexterity','intelligence'}
              and isinstance(v,(int,float)) and not isinstance(v,bool) and v>0}
        if nums:
            maximum=max(nums.values()); winners=[k for k,v in nums.items() if v==maximum]
            if len(winners)==1:
                key=winners[0];color={'strength':'r','dexterity':'g','intelligence':'b'}[key]
                return {'color':color,'attribute':{'r':'STR','g':'DEX','b':'INT'}[color],
                        'color_source':'gem.requirement_weights (maior peso)','weights':weights}
    return {'color':'w','attribute':'NÃO INFORMADO','color_source':'ausente ou híbrido sem cor explícita',
            'weights':weights if isinstance(weights,dict) else {}}

def parse(gems,skills,types_data,progress=None):
    if not isinstance(gems,dict) or not gems or not isinstance(skills,dict) or not skills:
        raise ValueError('Os arquivos skill_gems e skills devem ser objetos JSON não vazios.')
    type_map=type_dictionary(types_data)
    idx={}; collisions=set()
    for outer,r in skills.items():
        if not isinstance(r,dict): continue
        keys=[str(outer)]
        for s in sources(r):
            keys.extend(s[k] for k in ('id','skill_id','skillId','internal_id','internalId','granted_effect_id') if isinstance(s.get(k),str))
        for key in set(keys):
            if key in idx and idx[key]!=outer: collisions.add(key)
            else: idx[key]=outer
    diag={'gems_read':len(gems),'imported':0,'grants':0,'resolved':0,'unresolved':0,
          'ambiguous_skill_ids':len(collisions),'missing_support_rules':0,'skipped_records':0,
          'missing_colors':0,'missing_descriptions':0,'relations':0,'unresolved_examples':[]}
    entries=[];links=[]
    for sid,r in gems.items():
        if not isinstance(r,dict):diag['skipped_records']+=1;continue
        base=r.get('base_item') if isinstance(r.get('base_item'),dict) else {}
        name=base.get('display_name') or r.get('display_name') or r.get('name') or str(sid)
        eid=hashlib.sha256((SOURCE+'|'+str(sid)).encode()).hexdigest()[:24]
        tags=[str(x) for x in r.get('tags',[]) if isinstance(x,str)] if isinstance(r.get('tags'),list) else []
        grants=[]
        for k in ('grants_skills','granted_skills','skills_granted'):
            v=r.get(k)
            if isinstance(v,list):grants.extend(x for x in v if isinstance(x,str))
        grants=list(dict.fromkeys(grants))
        components=[]; resolved=[]; resolved_pairs=[]
        for gid in grants:
            diag['grants']+=1
            outer=idx.get(gid) if gid not in collisions else None
            if outer is None:
                diag['unresolved']+=1
                if len(diag['unresolved_examples'])<10:diag['unresolved_examples'].append(gid)
                components.append({'id':gid,'name':gid,'resolved':False,'types':None,'minion_types':None,
                                   'texts':[],'stats':[],'raw_key':None,'cannot_be_supported':None,'types_path':None})
                continue
            diag['resolved']+=1
            sr=skills[outer];resolved.append(sr);resolved_pairs.append((sr,'skills.'+str(outer)))
            ts=None;tp=None
            for k in ('types','skill_types','active_skill_types'):
                vv,tp=located([(sr,'skills.'+str(outer))],k)
                if vv is not None:ts=sequence(vv,type_map);break
            components.append({'id':gid,'name':field([sr],'display_name') or field([sr],'name') or gid,
                               'resolved':True,'types':ts,'types_path':tp,'minion_types':sequence(field([sr],'minion_types'),type_map),
                               'cannot_be_supported':field([sr],'cannot_be_supported'),
                               'texts':texts(sr,'skills.'+str(outer)),'stats':stats(sr,'skills.'+str(outer)),
                               'raw_key':str(outer)})
        if not components:
            ts=sequence(field([r],'types'),type_map)
            if ts is not None:
                components.append({'id':str(sid),'name':name,'resolved':True,'types':ts,'types_path':located([(r,'gem')],'types')[1],'minion_types':None,
                    'texts':[],'stats':[],'raw_key':None,'cannot_be_supported':field([r],'cannot_be_supported')})
        support=str(r.get('gem_type','')).lower()=='support' or r.get('is_support') is True or 'supportgem' in str(sid).lower()
        meta='meta' in {x.lower() for x in tags} or str(r.get('gem_type','')).lower()=='meta' or any('Meta' in (c['types'] or []) for c in components)
        kind='SUPPORT' if support else 'META' if meta else 'SKILL'
        # Do not merge rules from a triggered child effect with the support effect.
        rule_pairs=[(r,'gem')]+[(sr,p) for sr,p in resolved_pairs if field([sr],'allowed_types') is not None or field([sr],'excluded_types') is not None]
        rule_records=[sr for sr,p in rule_pairs]
        rules={k:sequence(located(rule_pairs,k)[0],type_map) for k in ('allowed_types','excluded_types','added_types','added_minion_types')}
        rule_paths={k:located(rule_pairs,k)[1] for k in ('allowed_types','excluded_types','added_types','added_minion_types')}
        rules.update({k:field(rule_records,k) for k in ('supports_gems_only','ignore_minion_types')})
        if support and (rules['allowed_types'] is None or rules['excluded_types'] is None):diag['missing_support_rules']+=1
        text_rows=texts(r,'gem')
        all_texts=text_rows+[t for c in components for t in c['texts']]
        stat_rows=stats(r,'gem')+[s for c in components for s in c['stats']]
        e={'id':eid,'source':SOURCE,'source_id':str(sid),'name':str(name),'kind':kind,
           'rule_paths':rule_paths,'gem_type':r.get('gem_type'),'availability':base.get('release_state') or r.get('release_state') or 'unknown',
           **attribute(r),'tags':tags,'components':components,'rules':rules,'texts':all_texts,
           'stats':stat_rows,'grants':grants,'source_url':BASE+'skill_gems.json',
           'lineage':r.get('is_lineage'),'summary':(all_texts[0]['text'] if all_texts else ''),
           'links':[]}
        def link(rel,target,label,path,evidence,component='gem'):
            key=concept(target)
            if key:
                e['links'].append({'relation':rel,'concept':key,'label':str(label),'path':path,
                                   'evidence':str(evidence),'component':component})
        for i,t in enumerate(tags):link('HAS_TAG',t,t,f'gem.tags[{i}]',t)
        for c in components:
            for i,t in enumerate(c['types'] or []):
                if token(t) in OPS:continue
                path=f"{c.get('types_path') or 'types (normalizado)'}[{i}]"
                link('HAS_TYPE',t,t,path,t,c['id'])
                if token(t) in FLAG_RELATIONS:
                    action,target,label=FLAG_RELATIONS[token(t)]
                    link(action,target,label,path,t,c['id'])
        if support:
            for k,rel in [('allowed_types','ALLOWS_TYPE_OPERAND'),('excluded_types','EXCLUDES_TYPE_OPERAND'),
                          ('added_types','ADDS_TYPE'),('added_minion_types','ADDS_MINION_TYPE')]:
                for i,t in enumerate(rules[k] or []):
                    if token(t) in OPS:continue
                    p=f'{rule_paths[k] or k}[{i}]'
                    link(rel,t,t,p,t,'support')
                    if k=='added_types' and token(t) in FLAG_RELATIONS:
                        action,target,label=FLAG_RELATIONS[token(t)]
                        link(action,target,label,p,t,'supported_skill')
                    if k=='added_minion_types' and token(t) in FLAG_RELATIONS:
                        action,target,label=FLAG_RELATIONS[token(t)]
                        link(action,target,label,p,t,'minion_of_supported_skill')
        for tr in all_texts:
            for m in re.finditer(r'\[([^\[\]]+)\]',tr['original']):
                words=m.group(1).split('|');label=words[-1]
                link('MENTIONS',words[0],label,tr['path'],tr['text'])
                # Named charge in [Charges|Power Charge] is also independently searchable.
                if len(words)>1:link('MENTIONS',label,label,tr['path'],tr['text'])
        # Preserve stable order, remove only duplicate edges, not tags or components.
        unique={}
        for l in e['links']:
            sig=(l['relation'],l['concept'],l['path'],l['component'])
            unique.setdefault(sig,l)
        e['links']=list(unique.values());diag['relations']+=len(e['links'])
        # Full raw search includes unparsed stats. No subset/whitelist of gems.
        search_blob=json.dumps({'gem':r,'skills':resolved},ensure_ascii=False,sort_keys=True)
        from .semantics import enrich
        enrich(e)
        e["raw_dataset"]="gems"
        entries.append((e,search_blob))
        if not all_texts:diag['missing_descriptions']+=1
        if e['attribute']=='NÃO INFORMADO':diag['missing_colors']+=1
        if progress and len(entries)%100==0:progress('Indexando gems',f'{len(entries)} / {len(gems)} registros')
    diag['imported']=len(entries)
    diag['relations']=sum(len(e['links']) for e,_ in entries)
    diag['semantic_links']=sum(e.get('semantic_count',0) for e,_ in entries)
    if not entries:raise ValueError('Nenhuma entidade reconhecida. Base anterior preservada.')
    return entries,diag

def resolve_folder(folder):
    base=Path(folder).expanduser().resolve()
    for sub in ('','data/raw/repoe','poe2-synergy-finder/data/raw/repoe'):
        d=base/sub
        if all((d/n).is_file() or (d/n.replace('.min.json','.json')).is_file() for n in FILES):return d
    raise ValueError('Não encontrei os três JSONs do RePoE nesta pasta. Selecione data/raw/repoe da versão anterior.')

def import_files(folder,version=None,progress=None,_connection=None):
    d=resolve_folder(folder); data=[];hashes={};paths={}
    for name in FILES:
        p=d/name
        if not p.exists():p=d/name.replace('.min.json','.json')
        if p.stat().st_size>150*1024*1024:raise ValueError('JSON excede o limite de 150 MB por arquivo.')
        if progress:progress('Lendo dados',p.name)
        b=p.read_bytes();hashes[name]=hashlib.sha256(b).hexdigest();paths[name]=str(p)
        data.append(json.loads(b.decode('utf-8-sig')))
    if version is None and (d/'manifest.json').is_file():
        try:version=json.loads((d/'manifest.json').read_text(encoding='utf-8')).get('repoe_version')
        except (ValueError,OSError):pass
    entries,diag=parse(*data,progress=progress)
    if progress:progress('Gravando base',f"{len(entries)} gems; transação única")
    with (nullcontext(_connection) if _connection is not None else storage.connect()) as c:
        if _connection is None:c.execute('BEGIN IMMEDIATE')
        c.execute('DELETE FROM entities WHERE source=?',(SOURCE,))
        c.execute("DELETE FROM raw_records WHERE dataset IN ('gems','skills','types')")
        for ds,payload in zip(('gems','skills','types'),data):
            if isinstance(payload,dict):
                c.executemany('INSERT INTO raw_records VALUES(?,?,?)',((ds,str(k),json.dumps(v,ensure_ascii=False)) for k,v in payload.items()))
            else:c.execute('INSERT INTO raw_records VALUES(?,?,?)',(ds,'all',json.dumps(payload,ensure_ascii=False)))
        for e,blob in entries:
            c.execute('INSERT INTO entities VALUES(?,?,?,?,?,?,?,?)',(e['id'],SOURCE,e['source_id'],e['name'],e['kind'],e['color'],json.dumps(e,ensure_ascii=False),blob))
            c.executemany('INSERT INTO links VALUES(?,?,?,?,?,?,?)',((e['id'],l['component'],l['relation'],l['concept'],l['label'],l['path'],l['evidence']) for l in e['links']))
        metadata={'source':SOURCE,'repoe_version':version,'imported_at':storage.now(),'folder':str(d),'hashes':hashes,
                  'paths':paths,'diagnostics':diag,'source_url':BASE,'schema_version':1}
        storage.put_meta(c,'import',metadata)
    return metadata
