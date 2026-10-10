"""Full passive corpus import, with original IDs, stats, ascendancy ownership.
The RePoE tree is not assumed to use the official site's camelCase node schema.
Root containers are discovered by node shape; invalid files never replace a base.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from contextlib import nullcontext
from . import storage
from .importer import BASE, concept, plain, texts
from .translations import Translator
from .semantics import enrich

SOURCE='RePoE PoE2 Tree'
TREE_FILES=('passive_skill_trees/Default.min.json','ascendancies.min.json',
    'stat_translations/passive_skill_stat_descriptions.min.json','stat_translations/stat_descriptions.min.json')
TREE_KINDS={'PASSIVE','NOTABLE','KEYSTONE','ASCENDANCY_NODE','ASCENDANCY','JEWEL_SOCKET','TREE_DECORATION','TREE_START'}

def stable_id(sid):return hashlib.sha256((SOURCE+'|'+str(sid)).encode()).hexdigest()[:24]

def is_node(value):
    return isinstance(value,dict) and isinstance(value.get('name'),str) and (
        isinstance(value.get('stats'),(dict,list)) and any(k in value for k in ('hash','is_notable','is_keystone','isNotable','isKeystone','skill_points')))

def node_container(tree):
    if not isinstance(tree,dict):raise ValueError('Árvore deve ser um objeto JSON.')
    candidates=[]
    def visit(obj,path,depth):
        if not isinstance(obj,dict) or depth>4:return
        nodes={str(k):v for k,v in obj.items() if is_node(v)}
        if nodes:candidates.append((nodes,path))
        for k,v in obj.items():
            if isinstance(v,dict) and not is_node(v):visit(v,path+'.'+str(k),depth+1)
    visit(tree,'tree',0)
    if not candidates:raise ValueError('Nenhum nó reconhecido na árvore. Campos da raiz: '+', '.join(list(tree)[:20]))
    candidates.sort(key=lambda r:len(r[0]),reverse=True)
    if len(candidates)>1 and len(candidates[0][0])==len(candidates[1][0]):
        raise ValueError('Mais de uma árvore com o mesmo tamanho. A importação exige um arquivo Default, não Atlas.')
    return candidates[0]

def parse(tree,ascendancies,translations=None):
    nodes,path=node_container(tree)
    if not isinstance(ascendancies,dict):raise ValueError('Ascendências devem ser um objeto JSON.')
    asc={str(k):v for k,v in ascendancies.items() if isinstance(v,dict) and isinstance(v.get('name'),str)}
    if not asc:raise ValueError('Nenhuma definição de ascendência reconhecida. A base anterior foi preservada.')
    tr=Translator(translations);out=[];edges=[];known_hash={str(n.get('hash',k)):k for k,n in nodes.items()}
    diag={'nodes':len(nodes),'ascendancies':len(asc),'tree_container':path,'translated_nodes':0,
          'untranslated_stats':0,'stats':0,'unknown_ascendancies':[],'declared_edges':0,
          'translation_groups':len(tr.groups),'granted_skills':0,'decorative_nodes':0}
    def base(sid,name,kind):
        return {'id':stable_id(sid),'source':SOURCE,'source_id':str(sid),'name':name,'kind':kind,
            'color':'w','attribute':'ÁRVORE','color_source':'sem atributo de gem','weights':{},
            'tags':[],'availability':'not_verified','components':[],'rules':{},'rule_paths':{},'texts':[],
            'stats':[],'grants':[],'source_url':BASE+TREE_FILES[0],'links':[],'summary':'',
            'raw_dataset':'tree_nodes','selectable':True}
    for aid,a in asc.items():
        e=base('ascendancy:'+aid,a['name'],'ASCENDANCY');e['attribute']='ASCENDÊNCIA'
        e['ascendancy_id']=aid;e['ascendancy']=a['name'];e['raw_dataset']='ascendancies'
        e['raw_key']=aid;e['source_url']=BASE+'ascendancies.min.json';e['class_name']=''
        character=a.get('character')
        if isinstance(character,list) and len(character)>1 and isinstance(character[1],str):e['class_name']=character[1]
        elif isinstance(character,dict):e['class_name']=character.get('name','')
        # Flavour is not a mechanical effect; it is not fed to semantic extraction.
        e['summary']='Ascendência: '+a['name']+(' · '+e['class_name'] if e['class_name'] else '')
        e['metadata_only']=True
        out.append((e,json.dumps({'name':a['name'],'class_name':e['class_name']},ensure_ascii=False)))
    for key,node in nodes.items():
        aid=str(node.get('ascendancy') or node.get('ascendancyName') or '')
        if aid not in asc:
            byname=next((k for k,a in asc.items() if a['name']==aid),None)
            if byname:aid=byname
        aid_name=asc[aid]['name'] if aid in asc else aid
        notable=node.get('is_notable',node.get('isNotable',False));keystone=node.get('is_keystone',node.get('isKeystone',False))
        icon_only=node.get('is_icon_only',False)
        starting=node.get('is_ascendancy_starting_node',False) or bool(node.get('classStartIndex') is not None)
        kind='TREE_DECORATION' if icon_only else 'TREE_START' if starting else 'ASCENDANCY_NODE' if aid else 'KEYSTONE' if keystone else 'NOTABLE' if notable else 'JEWEL_SOCKET' if node.get('is_jewel_socket',node.get('isJewelSocket')) else 'PASSIVE'
        e=base('node:'+key,node['name'],kind)
        e.update(node_id=key,node_hash=node.get('hash',key),raw_key=key,tree_path=path+'.'+key,
                 ascendancy_id=aid,ascendancy=aid_name,is_notable=bool(notable),is_keystone=bool(keystone),
                 selectable=kind not in {'TREE_DECORATION','TREE_START'},node_meta={k:node[k] for k in node if k!='stats'})
        if aid:
            e['attribute']='ASCENDÊNCIA'
            e['links'].append({'relation':'BELONGS_TO','concept':'ASCENDANCY:'+aid,'label':aid_name,
                               'path':path+'.'+key+'.ascendancy','evidence':aid,'component':'node'})
        if aid and aid not in asc and aid not in diag['unknown_ascendancies']:diag['unknown_ascendancies'].append(aid)
        if icon_only:diag['decorative_nodes']+=1
        tags=node.get('tags');e['tags']=[str(t) for t in tags] if isinstance(tags,list) else []
        for i,t in enumerate(e['tags']):e['links'].append({'relation':'HAS_TAG','concept':concept(t),'label':t,'path':path+'.'+key+f'.tags[{i}]','evidence':t,'component':'node'})
        value=node.get('stats',{})
        stat_map=value if isinstance(value,dict) else {}
        e['stats']=[{'path':path+'.'+key+'.stats.'+str(sid),'id':str(sid),'value':v,'semantic_fixed':True} for sid,v in stat_map.items()]
        translated,missing=tr.render(stat_map)
        e['texts']=texts(node,path+'.'+key)
        for row in translated:
            e['texts'].append({**row,'text':plain(row['text']),'original':row['text'],
                              'path':path+'.'+key+'.stats.'+'+'.join(row['stat_ids']),
                              'translation_path':row['path'],'component':'node'})
        if isinstance(value,list):
            for i,s in enumerate(value):
                if isinstance(s,str):e['texts'].append({'text':plain(s),'original':s,'path':path+'.'+key+f'.stats[{i}]','component':'node'})
                elif isinstance(s,dict):e['stats'].append({'path':path+'.'+key+f'.stats[{i}]','id':str(s.get('id',i)),'value':s})
        diag['translated_nodes']+=bool(translated);diag['untranslated_stats']+=len(missing);diag['stats']+=len(e['stats'])
        e['untranslated_stats']=missing
        g=node.get('granted_skill')
        if isinstance(g,str) and g:
            diag['granted_skills']+=1;e['granted_gem_id']=g
            e['links'].append({'relation':'GRANTS_SKILL','concept':g,'label':g,'path':path+'.'+key+'.granted_skill','evidence':g,'component':'node'})
        e['summary']=' / '.join(x['text'] for x in e['texts']) or ' · '.join(f'{s["id"]} = {s["value"]}' for s in e['stats']) or 'Sem modificadores neste registro.'
        enrich(e)
        if not e['selectable']:e['links']=[l for l in e['links'] if l['relation'] in {'HAS_TAG','BELONGS_TO'}]
        e['neighbour_keys']=[]
        # Only explicit adjacency arrays are accepted. Orbit/group IDs do not prove adjacency.
        for field in ('out','in','connections','connected_nodes'):
            for to in node.get(field,[]) if isinstance(node.get(field),list) else []:
                target=known_hash.get(str(to),str(to) if str(to) in nodes else None)
                if target and target!=key:
                    e['neighbour_keys'].append(target);edges.append((e['id'],stable_id('node:'+target),field))
        out.append((e,json.dumps(node,ensure_ascii=False)))
    diag['imported']=len(out);diag['declared_edges']=len(set(edges))
    diag['semantic_links']=sum(sum(l['relation'] in {'PRODUCES','ENABLES','GENERATES','CREATES','CONSUMES','REQUIRES','AMPLIFIES','REDUCES','PREVENTS','MODIFIES'} for l in e['links']) for e,_ in out)
    return out,diag,edges,nodes

def locate(folder,name):
    folder=Path(folder).expanduser().resolve()
    alternatives=(name,name.replace('.min.json','.json'),name.rsplit('/',1)[-1],name.rsplit('/',1)[-1].replace('.min.json','.json'))
    for sub in ('','data/raw/repoe','poe2-synergy-finder/data/raw/repoe'):
        for n in alternatives:
            p=folder/sub/n
            if p.is_file():return p
    return None

def import_tree(folder,version=None,progress=None,_connection=None):
    folder=Path(folder).expanduser().resolve();paths={};hashes={};loaded={}
    for name in TREE_FILES:
        p=locate(folder,name)
        if p is None:
            if name in TREE_FILES[:2]:raise ValueError('Arquivo necessário ausente: '+name)
            continue
        if p.stat().st_size>150*1024*1024:raise ValueError('Arquivo grande demais: '+name)
        if progress:progress('Lendo árvore e traduções',name)
        b=p.read_bytes();paths[name]=str(p);hashes[name]=hashlib.sha256(b).hexdigest();loaded[name]=json.loads(b.decode('utf-8-sig'))
    if version is None and (folder/'manifest.json').is_file():
        try:version=json.loads((folder/'manifest.json').read_text()).get('repoe_version')
        except (OSError,ValueError):pass
    rows,diag,edges,nodes=parse(loaded[TREE_FILES[0]],loaded[TREE_FILES[1]],{k:v for k,v in loaded.items() if k in TREE_FILES[2:]})
    if progress:progress('Gravando árvore e ascendências',f'{len(rows)} entidades; operação atômica')
    with (nullcontext(_connection) if _connection is not None else storage.connect()) as c:
        if _connection is None:c.execute('BEGIN IMMEDIATE')
        write_tree(c,rows,diag,edges,nodes,loaded)
        meta={'source':SOURCE,'repoe_version':version,'imported_at':storage.now(),'folder':str(folder),
              'hashes':hashes,'paths':paths,'diagnostics':diag,'source_url':BASE,'schema_version':2,
              'files_missing':[n for n in TREE_FILES if n not in loaded]}
        storage.put_meta(c,'tree_import',meta)
    return meta

def write_tree(c,rows,diag,edges,nodes,loaded):
    c.execute('DELETE FROM tree_edges')
    c.execute('DELETE FROM entities WHERE source=?',(SOURCE,))
    c.execute("DELETE FROM raw_records WHERE dataset IN ('tree','tree_nodes','ascendancies','tree_translations')")
    c.execute('INSERT INTO raw_records VALUES(?,?,?)',('tree','all',json.dumps(loaded[TREE_FILES[0]],ensure_ascii=False)))
    for ds,payload in [('tree_nodes',nodes),('ascendancies',loaded[TREE_FILES[1]])]:
        c.executemany('INSERT INTO raw_records VALUES(?,?,?)',((ds,str(k),json.dumps(v,ensure_ascii=False)) for k,v in payload.items()))
    for name in TREE_FILES[2:]:
        if name in loaded:c.execute('INSERT INTO raw_records VALUES(?,?,?)',('tree_translations',name,json.dumps(loaded[name],ensure_ascii=False)))
    for e,blob in rows:
        c.execute('INSERT INTO entities VALUES(?,?,?,?,?,?,?,?)',(e['id'],SOURCE,e['source_id'],e['name'],e['kind'],e['color'],json.dumps(e,ensure_ascii=False),blob))
        c.executemany('INSERT INTO links VALUES(?,?,?,?,?,?,?)',((e['id'],l['component'],l['relation'],l['concept'],l['label'],l['path'],l['evidence']) for l in e['links']))
    c.executemany('INSERT OR IGNORE INTO tree_edges VALUES(?,?,?)',set(edges))
