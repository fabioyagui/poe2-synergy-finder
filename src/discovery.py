"""Locate previous project's RePoE files in nearby project folders, not the user's disk."""
from pathlib import Path
import json
from . import storage
from .importer import resolve_folder

def candidates():
    bases={storage.ROOT,storage.ROOT.parent,storage.ROOT.parent.parent}
    for parent in list(bases):
        try:
            nearby=[p for p in parent.iterdir() if p.is_dir() and 'poe' in p.name.lower()][:60]
            bases.update(nearby)
            for p in nearby:
                bases.add(p/'poe2-synergy-finder')
        except OSError:continue
    found={}
    for b in sorted(bases,key=str):
        paths=[b,b/'data/raw/repoe',b/'poe2-synergy-finder/data/raw/repoe']
        for snap in (b/'data/raw/snapshots',):
            if snap.is_dir():
                try:paths.extend(sorted([p for p in snap.iterdir() if p.is_dir()],key=lambda p:p.stat().st_mtime,reverse=True)[:5])
                except OSError:pass
        for p in paths:
            try:
                d=resolve_folder(p)
                if str(d) in found:continue
                files=[p for p in d.iterdir() if p.name in {'skill_gems.min.json','skills.min.json','active_skill_types.min.json',
                    'skill_gems.json','skills.json','active_skill_types.json'}]
                found[str(d)]={'folder':str(d),'bytes':sum(p.stat().st_size for p in files),
                               'modified':max(p.stat().st_mtime for p in files)}
            except (ValueError,OSError):pass
    return sorted(found.values(),key=lambda x:x['modified'],reverse=True)
