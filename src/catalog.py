from __future__ import annotations
import json
import re
import unicodedata
from . import storage, VERSION
from .compatibility import evaluate, token
from .importer import concept, plain
from .semantics import SEMANTIC


def normalize(s):
    s=unicodedata.normalize('NFKD',str(s))
    s=''.join(c for c in s if not unicodedata.combining(c))
    s=re.sub(r'([a-z])([A-Z])',r'\1 \2',s)
    return re.sub(r'[^a-z0-9]+',' ',s.lower()).strip()

def compact(s):return normalize(s).replace(' ','')

def match(text,q):
    if not q.strip():return True
    hay=normalize(text);short=hay.replace(' ','')
    return all(w in hay or w in short for w in normalize(q).split())

def explain_expression(expr):
    if not isinstance(expr,list):return 'Regra ausente'
    if not expr:return '(lista vazia na fonte)'
    stack=[]
    try:
        for x in expr:
            t=token(x)
            if t=='NOT':stack[-1]='NÃO '+stack[-1]
            elif t in {'AND','OR'}:
                b,a=stack.pop(),stack.pop();stack.append(f'({a} {"E" if t=="AND" else "OU"} {b})')
            else:stack.append(x)
        return ' OU '.join(stack)
    except (ValueError,IndexError,TypeError):return 'Expressão inválida: '+str(expr)


def compatibility(skill,support,component=None):
    cs=skill.get('components',[])
    c=next((x for x in cs if x['id']==component),None) if component else (cs[0] if cs else None)
    if not c or not c.get('resolved') or not c.get('types'):
        return {'status':'unknown','label':'Não verificado','reason':'Tipos do efeito selecionado ausentes ou não resolvidos.'}
    if c.get('cannot_be_supported') is True:
        return {'status':'incompatible','label':'Incompatível por tipo','reason':'O efeito está marcado como cannot_be_supported.'}
    rules=support['rules']
    try:
        types={token(x) for x in c['types']}
        minions={token(x) for x in (c.get('minion_types') or [])} if rules.get('ignore_minion_types') is not True else set()
    except ValueError:
        return {'status':'unknown','label':'Não verificado','reason':'Tipos não interpretados.'}
    allow=evaluate(rules.get('allowed_types'),types|minions,empty=True)
    exclude=evaluate(rules.get('excluded_types'),types,empty=False)
    if allow is None or exclude is None:
        return {'status':'unknown','label':'Não verificado','reason':'Regra de tipos ausente ou inválida. Não foi presumida compatibilidade.'}
    status='type_match' if allow and not exclude else 'incompatible'
    return {'status':status,'label':'Compatível por tipos' if status=='type_match' else 'Incompatível por tipos',
            'reason':'Passou nas expressões de tipos importadas.' if status=='type_match' else
                     ('Não cumpre a exigência: '+explain_expression(rules.get('allowed_types')) if not allow else
                      'Ativa a exclusão: '+explain_expression(rules.get('excluded_types'))),
            'component':c['id'],'allowed':explain_expression(rules.get('allowed_types')),
            'excluded':explain_expression(rules.get('excluded_types'))}

class Catalog:
    def __init__(self):
        self.all_meta=storage.meta()
        self.meta=self.all_meta.get('import',{})
        self.tree_meta=self.all_meta.get('tree_import',{})
        self.entries={};self.search_index={};self.exact_index={};self.link_count=0
        with storage.connect() as c:
            for r in c.execute('SELECT id,payload,search_text FROM entities'):
                e=json.loads(r['payload']);self.entries[e['id']]=e
                blob=r['search_text']+' '+json.dumps(e,ensure_ascii=False)
                self.search_index[e['id']]=normalize(plain(blob))
                self.exact_index[e['id']]=blob.casefold()
                self.link_count+=len(e['links'])
        self.ordered=sorted(self.entries.values(),key=lambda e:(e['name'].casefold(),e['source_id']))

    def status(self):
        counts={};colors={};relations={}
        for e in self.ordered:
            counts[e['kind']]=counts.get(e['kind'],0)+1
            colors[e['attribute']]=colors.get(e['attribute'],0)+1
            for l in e['links']:relations[l['relation']]=relations.get(l['relation'],0)+1
        return {'app_version':VERSION,'entities':len(self.entries),'counts':counts,'colors':colors,
                'relations':relations,'links':self.link_count,'import':self.meta,'database':str(storage.DB),
                'tree_import':self.tree_meta,'semantic_links':sum(v for k,v in relations.items() if k in SEMANTIC),
                'ascendancies':[{'id':e['ascendancy_id'],'name':e['name']} for e in self.ordered if e['kind']=='ASCENDANCY'],
                'source_warnings':self.source_warnings(),
                'future_sources':[{'name':'Uniques','status':'ainda não importados'}]}

    def exact_name(self,name,kinds=None):
        target=normalize(name);allowed=set(kinds or [])
        return [e for e in self.ordered
                if normalize(e.get("name",""))==target
                and (not allowed or e.get("kind") in allowed)]

    def version_for(self,e):
        return (self.tree_meta if e.get('raw_dataset') in {'tree_nodes','ascendancies'} else self.meta).get('repoe_version')

    def source_warnings(self):
        a=self.meta.get('repoe_version');b=self.tree_meta.get('repoe_version')
        if self.meta and self.tree_meta and (not a or not b):return ['Versão de uma fonte não identificada. Não foi presumida igualdade de patch.']
        if a and b and a!=b:return [f'Fontes de versões diferentes: gems {a}; árvore {b}. Atualize a base completa.']
        return []

    def brief(self,e):
        out={k:e.get(k) for k in ['id','name','kind','color','attribute','tags','availability','summary','source_id']}
        out.update(ascendancy=e.get('ascendancy',''),ascendancy_id=e.get('ascendancy_id',''),is_notable=e.get('is_notable',False),is_keystone=e.get('is_keystone',False),selectable=e.get('selectable',True))
        return out

    def skills(self,q='',limit=60):
        rows=[e for e in self.ordered if e['kind'] in {'SKILL','META'} and match(e['name']+' '+' '.join(e['tags']),q)]
        rows.sort(key=lambda e:(normalize(e['name'])!=normalize(q),not normalize(e['name']).startswith(normalize(q)),e['name'].casefold()))
        return {'total':len(rows),'results':[self.brief(e) for e in rows[:limit]]}

    def get(self,eid,with_raw=False):
        e=self.entries.get(eid)
        if not e:return None
        out=dict(e)
        meta=self.tree_meta if e.get('raw_dataset') in {'tree_nodes','ascendancies'} else self.meta
        out['source_version']=meta.get('repoe_version')
        out['imported_at']=meta.get('imported_at')
        if e.get('raw_dataset')=='tree_nodes':
            from .tree_importer import stable_id
            out['neighbours']=[self.brief(self.entries[stable_id('node:'+k)]) for k in e.get('neighbour_keys',[]) if stable_id('node:'+k) in self.entries]
        if e.get('granted_gem_id'):
            out['granted_gem']=next((self.brief(v) for v in self.ordered if v['source_id']==e['granted_gem_id'] and v['kind'] in {'SKILL','META'}),None)
        if with_raw and e.get('raw_dataset') in {'tree_nodes','ascendancies'}:
            with storage.connect() as c:
                row=c.execute('SELECT payload FROM raw_records WHERE dataset=? AND source_id=?',(e['raw_dataset'],e['raw_key'])).fetchone()
                out['raw']={e['raw_dataset']:json.loads(row[0]) if row else None}
            return out
        if with_raw:
            with storage.connect() as c:
                row=c.execute("SELECT payload FROM raw_records WHERE dataset='gems' AND source_id=?",(e['source_id'],)).fetchone()
                children={}
                for cm in e['components']:
                    if cm['raw_key']:
                        rr=c.execute("SELECT payload FROM raw_records WHERE dataset='skills' AND source_id=?",(cm['raw_key'],)).fetchone()
                        if rr:children[cm['raw_key']]=json.loads(rr[0])
                out['raw']={'gem':json.loads(row[0]) if row else None,'skills':children}
        return out

    def explore(self,q='',skill_id='',component='',scope='supports',color='',tag='',relation='',mode='match',offset=0,limit=36,ascendancy='',kind='',include_decorative=False):
        skill=self.entries.get(skill_id)
        if skill_id and (not skill or skill['kind'] not in {'SKILL','META'}):raise ValueError('Escolha uma skill válida, não um support.')
        results=[];counts={'type_match':0,'incompatible':0,'unknown':0,'not_applicable':0}
        for e in self.ordered:
            if scope=='supports' and e['kind']!='SUPPORT':continue
            if scope=='passives' and e['kind'] not in {'PASSIVE','NOTABLE','KEYSTONE','JEWEL_SOCKET','TREE_START','TREE_DECORATION'}:continue
            if scope=='ascendancies' and e['kind'] not in {'ASCENDANCY','ASCENDANCY_NODE'}:continue
            if kind and e['kind']!=kind:continue
            if ascendancy and e.get('ascendancy_id')!=ascendancy:continue
            if not include_decorative and not e.get('selectable',True):continue
            if color and e['color']!=color:continue
            if tag and concept(tag) not in {concept(t) for t in e['tags']}:continue
            if q:
                matched=q.casefold() in self.exact_index[e['id']] if '_' in q else match(self.search_index[e['id']],q)
                if not matched:continue
            exact_links=[l for l in e['links'] if not q or concept(q)==l['concept'] or match(l['label'],q)]
            if relation:
                permitted={'consumes':{'CONSUMES'},'generates':{'GENERATES','CREATES'},
                           'tags':{'HAS_TAG'},'mentions':{'MENTIONS'},'prevents':{'PREVENTS_CONSUMPTION','PREVENTS'},'modifies':{'AMPLIFIES','REDUCES','MODIFIES'},'requires':{'REQUIRES'},'produces':{'PRODUCES','ENABLES','GENERATES','CREATES'}}.get(relation,{relation})
                if not any(l['relation'] in permitted for l in exact_links):continue
            comp=compatibility(skill,e,component) if skill and e['kind']=='SUPPORT' else {
                'status':'not_applicable','label':'Sem filtro de skill','reason':'Consulta da base, não aprovação de combinação.'}
            counts[comp['status']]+=1
            if skill and e['kind']=='SUPPORT':
                if mode=='match' and comp['status']!='type_match':continue
                if mode=='unknown' and comp['status']!='unknown':continue
                if mode=='incompatible' and comp['status']!='incompatible':continue
            evidence=[]
            for tr in e['texts']:
                if q and match(tr['text'],q):evidence.append({'source':'Texto da fonte','path':tr['path'],'text':tr['text']})
            if not evidence and q:
                for st in e['stats']:
                    if match(st['id']+' '+json.dumps(st['value'],ensure_ascii=False),q):
                        evidence.append({'source':'Stat bruto — significado não inferido','path':st['path'],
                                         'text':st['id']+' = '+json.dumps(st['value'],ensure_ascii=False)})
                        if len(evidence)>=3:break
            if not evidence and e['summary']:evidence=[{'source':'Texto da fonte' if e['texts'] else 'Metadados / stats originais','path':e['texts'][0]['path'] if e['texts'] else e.get('tree_path',e['source_id']),'text':e['summary']}]
            declared=[l for l in e['links'] if l['relation'] in SEMANTIC]
            # Collapse display duplicates only. The inspector retains every evidence path.
            unique={}
            for l in declared:unique.setdefault((l['relation'],l['concept'],l['component']),l)
            r=self.brief(e)
            r.update(compatibility=comp,evidence=evidence[:3],declared=list(unique.values())[:8],
                     matching_links=exact_links[:25],text_count=len(e['texts']),stat_count=len(e['stats']))
            results.append(r)
        return {'total':len(results),'counts':counts,'offset':offset,'limit':limit,
                'results':results[offset:offset+limit],'skill':self.brief(skill) if skill else None,
                'notice':'Ordem alfabética. Ligações e compatibilidade de tipos não são nota de poder nem ganho de DPS.'}

    def topics(self):
        index={}
        for e in self.ordered:
            for l in e['links']:
                if l['relation'] not in SEMANTIC|{'MENTIONS'}:continue
                d=index.setdefault(l['concept'],{'key':l['concept'],'name':l['label'],'ids':set()})
                d['ids'].add(e['id'])
        return [{'key':v['key'],'name':v['name'],'count':len(v['ids'])} for v in sorted(index.values(),key=lambda v:(-len(v['ids']),v['name']))]
