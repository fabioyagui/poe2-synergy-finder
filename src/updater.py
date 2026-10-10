"""RePoE downloads/local imports: isolated job, byte progress, atomic database import."""
from __future__ import annotations
import json
import re
import socket
import threading
import time
import uuid
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError
from . import storage, VERSION
from .importer import import_files
from .tree_importer import import_tree, TREE_FILES, locate

BASE = 'https://repoe-fork.github.io/poe2/'
GEM_FILES = ('skill_gems.min.json', 'skills.min.json', 'active_skill_types.min.json')
FILES = GEM_FILES + TREE_FILES

class Cancelled(Exception): pass

class Jobs:
    def __init__(self, on_commit=None):
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.on_commit = on_commit or (lambda: None)
        self.thread = None
        self.state = {'running':False,'stage':'Nenhuma atualização em curso','detail':'','error':None,'result':None,'id':None}
        self.started = None

    def snapshot(self):
        with self.lock:
            state = dict(self.state)
            state['elapsed_seconds'] = round(time.monotonic()-self.started,1) if self.started else 0
            return state

    def progress(self, stage, detail='', **more):
        with self.lock:
            self.state.update(stage=stage,detail=detail,updated_at=storage.now(),**more)
        if 'downloaded' not in more:
            print(f'[dados] {stage}: {detail}', flush=True)

    def check_cancelled(self):
        if self.stop_event.is_set(): raise Cancelled('Operação cancelada antes da gravação do catálogo.')

    def start(self, kind, folder=''):
        if kind not in {'online','local','online_tree','local_tree'}: raise ValueError('Operação de dados inválida.')
        with self.lock:
            if self.state['running']: raise RuntimeError('Uma atualização já está em andamento.')
            self.stop_event.clear()
            self.started=time.monotonic()
            self.state={'id':uuid.uuid4().hex,'running':True,'stage':'Preparando atualização',
                        'detail':'A base anterior será preservada até a nova importação concluir.','error':None,'result':None,
                        'downloaded':None,'total':None,'file_index':None,'file_count':len(TREE_FILES) if kind=='online_tree' else len(FILES)}
            job_id=self.state['id']
        self.thread=threading.Thread(target=self._work,args=(kind,folder),daemon=True)
        self.thread.start()
        return {'id':job_id,'running':True}

    def cancel(self):
        self.stop_event.set()
        return {'requested':True,'message':'Cancelamento solicitado. Uma requisição em espera pode levar até 25 segundos; uma gravação já iniciada terminará atomicamente.'}

    def _work(self, kind, folder):
        try:
            self.check_cancelled()
            version=None
            if kind in {'online','online_tree'}:
                folder,version=self._download(TREE_FILES if kind=='online_tree' else FILES)
            else:
                if not isinstance(folder,str) or not folder.strip(): raise ValueError('Informe a pasta da versão anterior ou data/raw/repoe.')
                folder=Path(folder)
            self.check_cancelled()
            def progress(stage,detail):
                self.check_cancelled()
                self.progress(stage,detail,downloaded=None,total=None)
            # One transaction for a complete snapshot. Tree-only updates keep gems.
            with storage.connect() as conn:
                conn.execute('BEGIN IMMEDIATE')
                if kind in {'online_tree','local_tree'}:
                    result=import_tree(folder,version=version,progress=progress,_connection=conn)
                else:
                    result=import_files(folder,version=version,progress=progress,_connection=conn)
                    tree_path=locate(folder,TREE_FILES[0]);asc_path=locate(folder,TREE_FILES[1])
                    if tree_path or asc_path:
                        tree=import_tree(folder,version=version,progress=progress,_connection=conn)
                        result={**result,'tree':tree}
            
            self.on_commit()
            self.progress('Catálogo atualizado',f"{result['diagnostics']['imported']} registros importados" + (f" + {result['tree']['diagnostics']['imported']} da árvore." if 'tree' in result else '.'),downloaded=None,total=None)
            with self.lock: self.state.update(running=False,result=result,finished_at=storage.now())
        except Exception as exc:
            cancelled=isinstance(exc,Cancelled)
            self.progress('Cancelado' if cancelled else 'Não foi possível atualizar',str(exc),downloaded=None,total=None)
            with self.lock: self.state.update(running=False,error=str(exc),finished_at=storage.now())

    def _read(self,url,destination=None,max_bytes=150*1024*1024,index=None):
        request=Request(url,headers={'User-Agent':f'PoE2-Synergy-Finder/{VERSION} (local research tool)'})
        started=time.monotonic(); accumulated=bytearray(); n=0
        try:
            with urlopen(request,timeout=25) as response:
                length=response.headers.get('Content-Length','')
                total=int(length) if length.isdigit() else None
                if total and total>max_bytes: raise ValueError('Download excede o limite de tamanho.')
                handle=destination.open('wb') if destination else None
                try:
                    while True:
                        self.check_cancelled()
                        if time.monotonic()-started>180: raise TimeoutError('Tempo máximo de download do arquivo excedido.')
                        block=response.read(128*1024)
                        if not block: break
                        n+=len(block)
                        if n>max_bytes: raise ValueError('Arquivo maior que o limite permitido.')
                        if handle: handle.write(block)
                        else: accumulated.extend(block)
                        if index:
                            self.progress('Baixando arquivo',url.rsplit('/',1)[-1],downloaded=n,total=total,file_index=index)
                finally:
                    if handle: handle.close()
        except (URLError,TimeoutError,socket.timeout) as exc:
            raise RuntimeError(f'Falha de conexão com RePoE: {exc}. A base anterior continua disponível; também é possível importar os arquivos já baixados.') from exc
        return bytes(accumulated)

    def _download(self,files=FILES):
        directory=storage.DATA/'raw'/'snapshots'/self.state['id']
        directory.mkdir(parents=True,exist_ok=False)
        for i,name in enumerate(files,1):
            self.progress('Conectando ao RePoE',name,file_index=i,downloaded=0,total=None)
            temp=directory/(name+'.part')
            temp.parent.mkdir(parents=True,exist_ok=True)
            self._read(BASE+name,temp,index=i)
            self.check_cancelled()
            # Validate before exposing the snapshot as a JSON file.
            with temp.open(encoding='utf-8-sig') as f: value=json.load(f)
            if not isinstance(value,(dict,list)) or not value: raise ValueError(f'{name} tem estrutura inesperada.')
            temp.replace(directory/name)
        self.progress('Lendo versão da fonte','A versão ficará desconhecida se o índice não a informar.',downloaded=None,total=None)
        version=None
        try:
            text=self._read(BASE,max_bytes=4*1024*1024).decode('utf-8','replace')
            match=re.search(r'PoE2 version\s+([0-9A-Za-z.\-_]+)',text,re.I)
            if match: version=match.group(1)
        except Cancelled: raise
        except Exception: pass
        (directory/'manifest.json').write_text(json.dumps({'repoe_version':version,'downloaded_at':storage.now(),'source':BASE},ensure_ascii=False,indent=2),encoding='utf-8')
        return directory,version
