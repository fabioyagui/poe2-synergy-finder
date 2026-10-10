"""CLI kept for diagnostics; the browser is the primary interface."""
import argparse,json
from src import storage
from src.catalog import Catalog
from src.importer import import_files
from src.tree_importer import import_tree
from src.interactions import build

def main():
    p=argparse.ArgumentParser(description='PoE2 Synergy Finder — dados completos')
    s=p.add_subparsers(dest='command',required=True)
    s.add_parser('status')
    i=s.add_parser('import');i.add_argument('folder')
    q=s.add_parser('search');q.add_argument('query')
    t=s.add_parser('import-tree');t.add_argument('folder')
    it=s.add_parser('interactions');it.add_argument('query')
    a=p.parse_args();storage.init()
    if a.command=='import':out=import_files(a.folder,progress=lambda a,b:print(a,b))
    elif a.command=='import-tree':out=import_tree(a.folder,progress=lambda a,b:print(a,b))
    elif a.command=='interactions':out=build(Catalog(),a.query)
    elif a.command=='status':out=Catalog().status()
    else:out=Catalog().explore(q=a.query,scope='all',mode='all')
    print(json.dumps(out,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
