"""Offline sealing only. Never run against an actively written database."""
import hashlib
import json
from pathlib import Path
import sqlite3

from .service import KnowledgeService


def seal_database(path):
    path = Path(path).resolve()
    if not KnowledgeService(path).ready():
        raise ValueError('Database is missing, partial, or has a stale coverage report')
    with sqlite3.connect(path.as_uri() + '?mode=rw', uri=True) as db:
        db.execute('PRAGMA cache_size=-2048')
        report = json.loads(db.execute("SELECT value FROM meta WHERE key='coverage'").fetchone()[0])
        if report.get('empty_articles', 1) or report.get('errors') or report['zim'].get('extractor_version') != '6':
            raise ValueError('Unresolved extraction errors, empty articles, or outdated extractor')
        if db.execute('SELECT count(*) FROM errors').fetchone()[0]:
            raise ValueError('Unresolved extraction errors')
        if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
            raise ValueError('SQLite integrity check failed')
        db.execute("INSERT INTO chunks_fts(chunks_fts,rank) VALUES('integrity-check',1)")
        db.commit()
        checkpoint = db.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()
        if checkpoint[0]:
            raise ValueError('Database is busy; stop writers before sealing')
        if db.execute('PRAGMA journal_mode=DELETE').fetchone()[0] != 'delete':
            raise ValueError('Could not switch to a single-file snapshot')
    db.close()
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    result = dict(database_sha256=digest, database_bytes=path.stat().st_size, coverage=report,
                  integrity_checks=dict(sqlite_quick_check='ok', fts_external_content='ok', journal_mode='delete'))
    manifest = path.with_suffix('.manifest.json')
    temporary = manifest.with_name(manifest.name + '.part')
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf8')
    temporary.replace(manifest)
    return result
