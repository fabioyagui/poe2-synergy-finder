"""Conservative RePoE stat text renderer.
Unknown handlers, incomplete groups or formats stay raw, rather than inventing text.
Reference: https://repoe-fork.github.io/data-formats/stat_translations.html
"""
from __future__ import annotations
import re

class Translator:
    def __init__(self, datasets=None):
        self.groups=[]; self.index={}; self.issues=[]
        for file,data in (datasets or {}).items():
            if isinstance(data,dict): data=data.get('translations',data.get('stats',[]))
            if not isinstance(data,list):
                self.issues.append(f'{file}: lista de traduções não reconhecida');continue
            for i,g in enumerate(data):
                if not isinstance(g,dict) or not isinstance(g.get('ids'),list) or not isinstance(g.get('English'),list):continue
                row=(g,f'{file}[{i}]');self.groups.append(row)
                for sid in g['ids']:self.index.setdefault(sid,[]).append(row)

    @staticmethod
    def handle(value,handler):
        if handler in {'negate','multiply_by_minus_one'}:return -value
        known={'divide_by_one_hundred':100,'divide_by_one_thousand':1000,'milliseconds_to_seconds':1000,
               'per_minute_to_per_second':60,'divide_by_ten':10,'divide_by_two':2,
               'divide_by_five':5,'divide_by_sixty':60}
        if handler in known:return value/known[handler]
        raise ValueError('Handler não implementado: '+str(handler))

    def render(self,values):
        if not isinstance(values,dict):return [],[]
        output=[];covered=set(); tried=set()
        for sid in values:
            for group,path in self.index.get(sid,[]):
                ids=group['ids'];sig=(path,tuple(ids))
                if sig in tried:continue
                tried.add(sig)
                # Missing values are not assumed zero: this is not the full stat engine.
                if any(k not in values or isinstance(values[k],bool) or not isinstance(values[k],(int,float)) for k in ids):continue
                vs=[values[k] for k in ids]
                if not any(v!=0 for v in vs):continue
                for variant in group['English']:
                    try:
                        cs=variant.get('condition');formats=variant.get('format');hs=variant.get('index_handlers')
                        if not isinstance(cs,list) or len(cs)!=len(vs) or not isinstance(formats,list) or len(formats)!=len(vs):continue
                        if not isinstance(hs,list) or len(hs)!=len(vs):continue
                        valid=True
                        for v,condition in zip(vs,cs):
                            ok=condition.get('min',float('-inf'))<=v<=condition.get('max',float('inf'))
                            if condition.get('negated'):ok=not ok
                            valid=valid and ok
                        if not valid:continue
                        formatted=[]
                        for v,fmt,handlers in zip(vs,formats,hs):
                            if not isinstance(handlers,list):raise ValueError('Handler malformado')
                            for h in handlers:v=self.handle(v,h)
                            if fmt=='ignore':formatted.append('')
                            elif fmt=='#':formatted.append(f'{v:g}')
                            elif fmt=='+#':formatted.append(f'{v:+g}')
                            else:raise ValueError('Formato desconhecido')
                        text=variant['string']
                        if not isinstance(text,str):continue
                        def sub(m):
                            idx=int(m.group(1))
                            if idx>=len(formatted):raise ValueError('Índice de tradução')
                            return formatted[idx]
                        text=re.sub(r'\{(\d+)\}',sub,text)
                        # Do not claim a rendered string with unresolved format tokens.
                        if re.search(r'\{[^}]*\}',text):continue
                        output.append({'text':text,'original':variant['string'],'path':path,
                                       'stat_ids':ids,'values':{k:values[k] for k in ids},'rendered':True})
                        covered.update(ids);break
                    except (ValueError,TypeError,KeyError,IndexError,ArithmeticError):continue
                if all(k in covered for k in ids):break
        return output,[k for k in values if k not in covered]
