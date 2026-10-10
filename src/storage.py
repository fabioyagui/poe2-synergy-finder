from __future__ import annotations
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get('POE2_SYNERGY_DATA_DIR', str(ROOT/'data'))).resolve()
DB = DATA/'database'/'explorer_v08.sqlite3'

def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

@contextmanager
def connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    c.execute('PRAGMA busy_timeout=30000')
    try:
        with c: yield c
    finally: c.close()

def init():
    with connect() as c:
        c.execute('PRAGMA journal_mode=WAL')
        c.executescript('''
        CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS entities(
            id TEXT PRIMARY KEY, source TEXT NOT NULL, source_id TEXT NOT NULL,
            name TEXT NOT NULL, kind TEXT NOT NULL, color TEXT NOT NULL,
            payload TEXT NOT NULL, search_text TEXT NOT NULL,
            UNIQUE(source, source_id)
        );
        CREATE TABLE IF NOT EXISTS links(
            entity_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
            component TEXT NOT NULL, relation TEXT NOT NULL, concept TEXT NOT NULL,
            label TEXT NOT NULL, evidence_path TEXT NOT NULL, evidence TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS links_concept ON links(concept,relation);
        CREATE INDEX IF NOT EXISTS links_entity ON links(entity_id);
        CREATE TABLE IF NOT EXISTS tree_edges(
            from_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
            to_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
            source_field TEXT NOT NULL, PRIMARY KEY(from_id,to_id,source_field));
        CREATE TABLE IF NOT EXISTS raw_records(
            dataset TEXT NOT NULL, source_id TEXT NOT NULL, payload TEXT NOT NULL,
            PRIMARY KEY(dataset,source_id)
        );
        ''')

def meta():
    with connect() as c:
        return {r['key']:json.loads(r['value']) for r in c.execute('SELECT * FROM meta')}

def put_meta(c,k,v):
    c.execute('INSERT INTO meta VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
              (k,json.dumps(v,ensure_ascii=False)))
