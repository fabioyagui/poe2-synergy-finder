"""Update the Finder program only; never replace data/, engine/ or credentials."""
from __future__ import annotations
import argparse
import ast
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

SOURCE=Path(__file__).resolve().parent
PACKAGE_VERSION='0.19.3'
SUPPORTED={'0.15.0','0.16.0','0.16.1','0.17.0','0.18.0','0.18.1','0.18.2','0.18.3','0.18.4','0.18.5','0.18.6','0.18.7','0.19.0','0.19.1','0.19.2'}
MANAGED_DIRS={'src','web','tests','docs'}
MANAGED_FILES={'ABRIR_LOG_MCP.bat','AGENTS.md','ATUALIZAR_INSTALACAO.bat','CODEX_MCP.md','INSTALAR_CODEX_MCP.bat','LEIA_PRIMEIRO.txt','LIMPAR_LOG_MCP.bat','README.md','REMOVER_CODEX_MCP.bat','REPARAR_CODEX_MCP.bat','START_POE2_SYNERGY_FINDER.bat','TESTAR_9_MCP_REAIS.bat','TESTAR_9_MCP_REAIS.py','TESTAR_CODEX_MCP.bat','TESTAR_HANDSHAKE_MCP.bat','TESTAR_HANDSHAKE_MCP.py','TESTAR_SCHEMAS_CODEX.bat','TESTAR_SCHEMAS_CODEX.py','app.py','atualizar_instalacao.py','main.py','mcp_server.py'}

def version(root: Path) -> str:
    tree=ast.parse((root/'src/__init__.py').read_text(encoding='utf-8-sig'))
    for node in tree.body:
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='VERSION' for t in node.targets):
            return str(ast.literal_eval(node.value))
    raise ValueError('Não encontrei a versão desta instalação.')

def files(source: Path) -> list[Path]:
    result=[]
    for p in source.rglob('*'):
        rel=p.relative_to(source)
        if not p.is_file() or '__pycache__' in rel.parts or p.suffix=='.pyc':continue
        if rel.parts[0] in MANAGED_DIRS or rel.as_posix() in MANAGED_FILES:
            result.append(rel)
    return sorted(result)

def atomic_copy(src: Path,dst: Path):
    dst.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix='.sf-update-',dir=dst.parent)
    try:
        with os.fdopen(fd,'wb') as out, src.open('rb') as inp:shutil.copyfileobj(inp,out)
        os.replace(tmp,dst)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def update(source: Path,target: Path) -> Path:
    source=source.resolve();target=target.resolve()
    if source==target:raise ValueError('Escolha a pasta da instalação anterior, não a pasta nova do ZIP.')
    if not (target/'app.py').is_file() or version(target) not in SUPPORTED:
        raise ValueError('Este atualizador aceita v0.15, v0.16, v0.17, v0.18, v0.19.0, v0.19.1 ou v0.19.2. A pasta deve conter app.py.')
    if version(source)!=PACKAGE_VERSION:raise ValueError('Pacote de atualização inválido.')
    relative=files(source)
    for rel in relative:
        dst=(target/rel).resolve()
        if not dst.is_relative_to(target):raise ValueError('Um caminho da instalação aponta para fora da pasta; atualização cancelada.')
    backup=target/'backups'/('antes-v'+PACKAGE_VERSION+'-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    backup.mkdir(parents=True)
    existed={}
    # Complete the backup before changing any program file.
    for rel in relative:
        old=target/rel;existed[rel.as_posix()]=old.is_file()
        if old.is_file():atomic_copy(old,backup/rel)
    (backup/'manifest.json').write_text(json.dumps(existed,indent=2),encoding='utf-8')
    changed=[]
    try:
        for rel in relative:
            atomic_copy(source/rel,target/rel);changed.append(rel)
    except Exception:
        # Restore only files touched by this updater. Never touch data/ or engine/.
        for rel in reversed(changed):
            if existed[rel.as_posix()]:atomic_copy(backup/rel,target/rel)
            else:(target/rel).unlink(missing_ok=True)
        raise
    return backup

def choose_target() -> Path:
    family=SOURCE.parent.parent
    candidates=[]
    for folder in family.glob('poe2-synergy-finder-v*'):
        candidate=folder/'poe2-synergy-finder'
        if candidate.resolve()==SOURCE.resolve() or not (candidate/'app.py').is_file():continue
        try:
            if version(candidate) in SUPPORTED:candidates.append(candidate)
        except (OSError,ValueError,SyntaxError):pass
    if len(candidates)==1:
        print('\nInstalação encontrada:\n'+str(candidates[0]))
        answer=input('Usar esta pasta? [S/n]: ').strip().lower()
        if answer in {'','s','sim','y','yes'}:return candidates[0]
    try:
        import tkinter
        from tkinter import filedialog
        root=tkinter.Tk();root.withdraw()
        folder=filedialog.askdirectory(title='Selecione a pasta da instalação que você usa, contendo app.py',mustexist=True)
        root.destroy()
        if not folder:raise ValueError('Atualização cancelada.')
        return Path(folder)
    except ImportError:
        return Path(input('Cole a pasta da instalação que contém app.py: ').strip().strip('"'))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target',type=Path);parser.add_argument('--yes',action='store_true')
    args=parser.parse_args()
    print('PoE2 Synergy Finder → 0.19.3\nFecha o Finder e o Motor PoB antes de continuar.\nBuilds, configurações, dados e motor não serão substituídos.')
    try:
        target=args.target or choose_target()
        if not args.yes:
            answer=input('\nO Finder e o motor estão fechados? Confirmar atualização [s/N]: ').strip().lower()
            if answer not in {'s','sim','y','yes'}:raise ValueError('Atualização cancelada.')
        backup=update(SOURCE,target)
        print('\nAtualização concluída. Backup do código anterior:\n'+str(backup))
        print('\nAbra o START_POE2_SYNERGY_FINDER.bat da mesma pasta que você já usava.\nO nome da pasta pode continuar v0.15; a interface deve mostrar 0.19.3.')
        return 0
    except Exception as exc:
        print('\nAtualização não concluída: '+str(exc));return 1

if __name__=='__main__':raise SystemExit(main())
