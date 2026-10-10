from __future__ import annotations
import argparse
import html as html_lib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import traceback
import urllib.request
import urllib.error
from urllib.parse import urlparse,parse_qs
import webbrowser
from src import VERSION,storage
from src.catalog import Catalog,compatibility as catalog_compatibility
from src.updater import Jobs
from src.discovery import candidates
from src.interactions import build as build_interactions
from src import pob_bridge,ggg_api,tree_simulator,workbench,trade,assets,economy

class Application:
    def __init__(self):
        storage.init();self.catalog=Catalog();self.lock=threading.Lock()
        self.jobs=Jobs(self.refresh)
    def refresh(self):
        new=Catalog()
        with self.lock:self.catalog=new

WEB=Path(__file__).resolve().parent/'web'

def _support_semantics(cat,names,skill_name=""):
    skills=cat.exact_name(skill_name,{"SKILL","META"}) if skill_name else []
    skill=skills[0] if skills else None
    out=[]
    semantic={"PRODUCES","ENABLES","AMPLIFIES","REDUCES","MODIFIES","REQUIRES",
              "PREVENTS","CONSUMES","GENERATES","CREATES","PREVENTS_CONSUMPTION"}
    for name in names:
        rows=cat.exact_name(name,{"SUPPORT"})
        if not rows:
            out.append({"name":name,"found":False})
            continue
        e=rows[0]
        comp=catalog_compatibility(skill,e) if skill else {
            "status":"unknown","label":"Não cruzado","reason":"Skill não localizada pelo mesmo nome na base RePoE."
        }
        out.append({
            "name":name,"found":True,"attribute":e.get("attribute"),"color":e.get("color"),
            "tags":e.get("tags",[]),"summary":e.get("summary",""),"compatibility":comp,
            "links":[{"relation":l.get("relation"),"label":l.get("label"),"concept":l.get("concept"),
                      "component":l.get("component"),"path":l.get("path"),"evidence":l.get("evidence")}
                     for l in e.get("links",[]) if l.get("relation") in semantic]
        })
    return out


def make_handler(application):
    class Handler(BaseHTTPRequestHandler):
        server_version='PoE2Synergy/'+VERSION
        def log_message(self,fmt,*args):
            if '/api/progress' not in str(args):print('[web] '+fmt%args,flush=True)
        def valid_host(self):
            host=self.headers.get('Host','')
            return host in {f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}
        def json(self,data,status=200):
            raw=json.dumps(data,ensure_ascii=False).encode()
            self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8')
            self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(raw)
        def html(self,text,status=200):
            raw=text.encode('utf-8')
            self.send_response(status);self.send_header('Content-Type','text/html; charset=utf-8')
            self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(raw)
        def do_GET(self):
            if not self.valid_host():return self.json({'error':'Host local inválido.'},403)
            p=urlparse(self.path);q=parse_qs(p.query)
            get=lambda k,d='':q.get(k,[d])[0]
            cat=application.catalog
            try:
                if p.path=='/api/status':return self.json(cat.status())
                if p.path=='/api/pob/current':return self.json(pob_bridge.load_current() or {'imported':False})
                if p.path=='/api/build/tree-analysis':return self.json(pob_bridge.current_tree_analysis(cat))
                if p.path=='/api/ggg/status':
                    st=ggg_api.status()
                    st['redirect_uri']=f'http://127.0.0.1:{self.server.server_port}/oauth/callback'
                    return self.json(st)
                if p.path=='/api/ggg/characters':return self.json(ggg_api.list_characters())
                if p.path=='/oauth/callback':
                    error=get('error')
                    if error:
                        msg="OAuth GGG cancelado/recusado: "+html_lib.escape(str(error))
                        return self.html(f"<!doctype html><meta charset='utf-8'><title>GGG OAuth</title><body style='font-family:system-ui;background:#111;color:#eee;padding:32px'><h2>{msg}</h2><p>Você pode fechar esta janela.</p></body>",400)
                    try:
                        ggg_api.finish_oauth(get('code'),get('state'))
                        return self.html("<!doctype html><meta charset='utf-8'><title>GGG OAuth</title><body style='font-family:system-ui;background:#111;color:#eee;padding:32px'><h2>Conta GGG autorizada ✓</h2><p>Volte ao Synergy Finder. Esta janela pode ser fechada.</p><script>setTimeout(()=>window.close(),1800)</script></body>")
                    except Exception as e:
                        return self.html(f"<!doctype html><meta charset='utf-8'><title>GGG OAuth</title><body style='font-family:system-ui;background:#111;color:#eee;padding:32px'><h2>Falha na autorização</h2><pre>{html_lib.escape(str(e))}</pre><p>Volte ao Synergy Finder.</p></body>",400)
                if p.path=='/api/builds':return self.json(pob_bridge.library_list(get('q'),get('class_name'),get('ascendancy'),get('main_skill'),int(get('min_level','0') or 0),get('sync','1')!='0'))
                if p.path=='/api/pob/engine/status':return self.json(pob_bridge.stdio_engine_status())
                if p.path=='/api/pob/engine/setup':return self.json(pob_bridge.stdio_setup_status())
                if p.path=='/api/pob/engine/virtual':return self.json(pob_bridge.stdio_virtual_context())
                if p.path=='/api/progress':return self.json(application.jobs.snapshot())
                if p.path=='/api/candidates':return self.json({'results':candidates()})
                if p.path=='/api/skills':return self.json(cat.skills(get('q'),100))
                if p.path=='/api/topics':return self.json({'results':cat.topics()})
                if p.path=='/api/entity':
                    value=cat.get(get('id'),with_raw=get('raw')=='1')
                    return self.json(value if value else {'error':'Registro não encontrado. Recarregue a lista.'},200 if value else 404)
                if p.path=='/api/interactions':
                    return self.json(build_interactions(cat,q=get('q'),skill_id=get('skill_id'),component=get('component'),
                        include_incompatible=get('include_incompatible')=='1',ascendancy=get('ascendancy'),limit=int(get('limit','12'))))
                if p.path.startswith('/api/economy/'):
                    eco=economy.current_map();many=lambda k:[x.strip() for x in get(k).split(',') if x.strip()]
                    if p.path=='/api/economy/status':return self.json(eco.status())
                    if p.path=='/api/economy/anchors':
                        return self.json(eco.anchors(resource=get('resource'),kinds=many('kinds'),ascendancy=get('ascendancy'),
                            include_plain_reads=get('include_plain_reads')=='1',include_universal=get('include_universal')=='1',limit=int(get('limit','40'))))
                    if p.path=='/api/economy/resource':
                        return self.json(eco.resource(get('resource'),verbs=many('verbs'),kinds=many('kinds'),ascendancy=get('ascendancy'),limit_per_verb=int(get('limit_per_verb','25'))))
                    if p.path=='/api/economy/lookup':return self.json(eco.lookup(get('query'),kinds=many('kinds'),limit=int(get('limit','30'))))
                if p.path=='/api/explore':
                    kw={k:get(k) for k in ('q','skill_id','component','color','tag','relation','ascendancy','kind')}
                    for key,choices,default in [('scope',{'supports','all','passives','ascendancies'},'supports'),('mode',{'match','all','unknown','incompatible'},'match')]:
                        value=get(key,default)
                        if value not in choices:raise ValueError('Filtro inválido.')
                        kw[key]=value
                    kw['include_decorative']=get('include_decorative')=='1'
                    kw['offset']=max(0,int(get('offset','0')));kw['limit']=max(1,min(100,int(get('limit','36'))))
                    return self.json(cat.explore(**kw))
                routes={'/':('index.html','text/html; charset=utf-8'),'/app.js':('app.js','application/javascript; charset=utf-8'),
                        '/style.css':('style.css','text/css; charset=utf-8'),
                        '/tree-sim.js':('tree-sim.js','application/javascript; charset=utf-8'),
                        '/tree-sim.css':('tree-sim.css','text/css; charset=utf-8'),
                        '/workbench.js':('workbench.js','application/javascript; charset=utf-8'),
                        '/workbench.css':('workbench.css','text/css; charset=utf-8')}
                if p.path in routes:
                    name,ctype=routes[p.path];b=(WEB/name).read_bytes()
                    self.send_response(200);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(b)))
                    self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
                    self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data: https://image.ggpk.exposed https://web.poecdn.com https://*.poecdn.com; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
                    self.end_headers();self.wfile.write(b);return
                return self.json({'error':'Não encontrado.'},404)
            except ValueError as e:return self.json({'error':str(e)},400)
            except (BrokenPipeError,ConnectionResetError):pass
            except Exception:
                traceback.print_exc();return self.json({'error':'Falha no servidor. Veja a janela do programa para os detalhes.'},500)
        def do_POST(self):
            if not self.valid_host():return self.json({'error':'Host inválido.'},403)
            origin=self.headers.get('Origin')
            allowed={f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}'}
            if origin not in allowed or self.headers.get('X-Local-App')!='poe2-explorer':
                return self.json({'error':'Operação permitida apenas pela interface local.'},403)
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 0<=size<=2_000_000:raise ValueError('Pedido grande demais.')
                body=json.loads(self.rfile.read(size) or b'{}')
                if not isinstance(body,dict):raise ValueError('Pedido inválido.')
                path=urlparse(self.path).path
                if path=='/api/import':return self.json(application.jobs.start(body.get('kind'),body.get('folder','')),202)
                if path=='/api/workbench/visual':return self.json(workbench.visual_context())
                if path=='/api/workbench/calcs':return self.json(workbench.calcs(body))
                if path=='/api/workbench/suggestions':return self.json(workbench.suggestions(body))
                if path=='/api/tree-sim/context':return self.json(tree_simulator.context())
                if path=='/api/tree-sim/preview':return self.json(tree_simulator.preview(body))
                if path=='/api/tree-sim/compare':return self.json(tree_simulator.compare(body))
                if path=='/api/pob/import':
                    return self.json(pob_bridge.import_build(str(body.get('source',''))))
                if path=='/api/ggg/config':return self.json(ggg_api.save_config(body))
                if path=='/api/ggg/oauth/start':return self.json(ggg_api.start_oauth(self.server.server_port))
                if path=='/api/ggg/logout':return self.json(ggg_api.logout())
                if path=='/api/ggg/import-character':return self.json(pob_bridge.ggg_import_character(str(body.get('name',''))))
                if path=='/api/ggg/import-snapshot':return self.json(pob_bridge.ggg_import_snapshot(body.get('snapshot')))
                if path=='/api/builds/use':return self.json(pob_bridge.library_use(str(body.get('id',''))))
                if path=='/api/builds/delete':return self.json(pob_bridge.library_delete(str(body.get('id',''))))
                if path=='/api/assets/resolve':
                    names=body.get('names') or []
                    if not isinstance(names,list):raise ValueError('Lista de assets inválida.')
                    return self.json(assets.resolve_names(names))
                if path=='/api/trade/prepare':
                    current=pob_bridge.load_current()
                    if not current:raise ValueError('Nenhuma build ativa.')
                    return self.json(trade.prepare_item(current,str(body.get('slot',''))))
                if path=='/api/trade/search':
                    current=pob_bridge.load_current()
                    if not current:raise ValueError('Nenhuma build ativa.')
                    filters=body.get('filters') or []
                    if not isinstance(filters,list):raise ValueError('Filtros de trade inválidos.')
                    return self.json(trade.search_item(current,str(body.get('slot','')),league=str(body.get('league','')),filters=filters,base_only=bool(body.get('base_only')),online=body.get('online',True) is not False))
                if path=='/api/pob/engine/detect':
                    return self.json(pob_bridge.stdio_auto_detect())
                if path=='/api/pob/engine/config':
                    return self.json(pob_bridge.stdio_save_config(body))
                if path=='/api/pob/engine/install-pob':
                    return self.json(pob_bridge.stdio_install_pob_checkout())
                if path=='/api/pob/engine/install-bridge':
                    return self.json(pob_bridge.stdio_install_bridge())
                if path=='/api/pob/engine/start':
                    return self.json(pob_bridge.stdio_start())
                if path=='/api/pob/engine/stop':
                    return self.json(pob_bridge.stdio_stop())
                if path=='/api/pob/engine/load':
                    return self.json(pob_bridge.stdio_load_current())
                if path=='/api/pob/engine/snapshot':
                    return self.json(pob_bridge.stdio_snapshot())
                if path=='/api/pob/engine/compatible-supports':
                    return self.json(pob_bridge.stdio_compatible_supports(body))
                if path=='/api/pob/engine/compare-supports':
                    result=pob_bridge.stdio_compare_supports(body)
                    result['semantics']=_support_semantics(application.catalog,result.get('selected_supports',[]),result.get('main_skill',''))
                    return self.json(result)
                if path=='/api/cancel':return self.json(application.jobs.cancel())
                return self.json({'error':'Não encontrado.'},404)
            except RuntimeError as e:return self.json({'error':str(e)},409)
            except ValueError as e:return self.json({'error':str(e)},400)
            except Exception:
                traceback.print_exc();return self.json({'error':'Falha ao iniciar a operação.'},500)
    return Handler


def _running_finders(start_port: int, count: int=10) -> list[dict]:
    found=[]
    for port in range(start_port,start_port+count):
        try:
            req=urllib.request.Request(f"http://127.0.0.1:{port}/api/status",headers={"Accept":"application/json"})
            with urllib.request.urlopen(req,timeout=0.25) as response:
                payload=json.loads(response.read().decode("utf-8"))
            if isinstance(payload,dict) and payload.get("app_version"):
                found.append({"port":port,"version":str(payload.get("app_version"))})
        except Exception:
            pass
    return found


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=8777)
    parser.add_argument('--no-browser',action='store_true')
    args=parser.parse_args()
    running=_running_finders(args.port,10)
    if running:
        detail=", ".join(f"v{x['version']} em http://127.0.0.1:{x['port']}" for x in running)
        raise SystemExit("Já existe outra instância do PoE2 Synergy Finder aberta: "+detail+". Feche a janela/terminal antigo antes de iniciar esta versão. Isso evita carregar ou analisar uma build antiga.")
    app=Application()
    try:
        server=ThreadingHTTPServer(('127.0.0.1',args.port),make_handler(app))
    except OSError as exc:
        raise SystemExit(f"A porta {args.port} já está em uso. Feche o programa que está usando essa porta e tente novamente.") from exc
    server.daemon_threads=True
    url=f'http://127.0.0.1:{server.server_port}'
    print(f'\nPoE2 Synergy Finder {VERSION} | Dados + árvore + interações\n{url}\nBase: {storage.DB}\nMantenha esta janela aberta. Ctrl+C encerra.\n',flush=True)
    if not args.no_browser:threading.Timer(.5,lambda:webbrowser.open(url)).start()
    try:server.serve_forever()
    except KeyboardInterrupt:print('\nEncerrando...')
    finally:
        from src.pob_engine import ENGINE
        ENGINE.stop(force=True)
        server.server_close()

if __name__=='__main__':main()
