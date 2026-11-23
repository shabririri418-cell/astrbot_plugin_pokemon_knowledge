"""Disk-backed exact aliases and CJK bigram FTS. Runtime uses stdlib only."""
import hashlib,json,re,sqlite3,time,zlib
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote
from .text import title_key,variants,index_text,search_tokens,candidate_keys

LICENSE='CC BY-NC-SA 3.0'
SOURCE='神奇宝贝百科（52Poké Wiki）'
KNOWLEDGE_NAMESPACES=(0,100)

class KnowledgeStore:
    query_revision='2'
    def __init__(self,path,readonly=False):
        self.path=Path(path).resolve();self.readonly=readonly;self._depth=0;self.db=None
        if readonly:return
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(self.path,timeout=30)
        self.db.row_factory=sqlite3.Row
        self.db.executescript('''PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL; PRAGMA cache_size=-16384;
CREATE TABLE IF NOT EXISTS pages(id INTEGER PRIMARY KEY,title TEXT UNIQUE NOT NULL,namespace INTEGER DEFAULT 0,xml_id INTEGER,revision INTEGER,xml_timestamp TEXT,xml_snapshot TEXT,xml_hash TEXT,raw_source BLOB,redirect TEXT DEFAULT '',body_snapshot TEXT,body_hash TEXT,quality TEXT,seen_xml TEXT,seen_zim TEXT);
CREATE INDEX IF NOT EXISTS pages_namespace ON pages(namespace);
CREATE TABLE IF NOT EXISTS aliases(key TEXT,alias TEXT,target TEXT,PRIMARY KEY(key,alias,target));
CREATE INDEX IF NOT EXISTS alias_target ON aliases(target);
CREATE TABLE IF NOT EXISTS chunks(id INTEGER PRIMARY KEY,page_id INTEGER,position INTEGER,section TEXT,kind TEXT,text TEXT,tokens TEXT);
CREATE INDEX IF NOT EXISTS chunks_page ON chunks(page_id,position);
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(tokens,content='chunks',content_rowid='id');
CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN INSERT INTO chunks_fts(rowid,tokens) VALUES(new.id,new.tokens); END;
CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN INSERT INTO chunks_fts(chunks_fts,rowid,tokens) VALUES('delete',old.id,old.tokens); END;
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT);
INSERT OR IGNORE INTO meta VALUES('schema_version','1');
CREATE TABLE IF NOT EXISTS errors(stage TEXT,item TEXT,error TEXT,PRIMARY KEY(stage,item));
''');self.db.commit()

    @contextmanager
    def batch(self):
        self._depth+=1
        try:
            yield self
            if self._depth==1:self.db.commit()
        except BaseException:
            if self._depth==1:self.db.rollback()
            raise
        finally:self._depth-=1

    def commit(self):
        if not self._depth:self.db.commit()

    @contextmanager
    def connection(self):
        if self.db is not None:yield self.db;return
        connection=sqlite3.connect(self.path.as_uri()+'?mode=ro',uri=True,timeout=2)
        connection.row_factory=sqlite3.Row;connection.execute('PRAGMA cache_size=-2048');connection.execute('PRAGMA query_only=ON')
        try:yield connection
        finally:connection.close()

    def metadata(self,key,default=None):
        with self.connection() as db:row=db.execute('SELECT value FROM meta WHERE key=?',(key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set_metadata(self,key,value):
        self.db.execute('INSERT OR REPLACE INTO meta VALUES(?,?)',(key,json.dumps(value,ensure_ascii=False)));self.commit()

    def add_alias(self,alias,target,owner=None):
        self.db.executemany('INSERT OR IGNORE INTO aliases VALUES(?,?,?)',[(title_key(value),owner or alias,target) for value in variants(alias) if value]);self.commit()

    def put_xml(self,title,namespace,xml_id,revision,timestamp,wikitext,snapshot,redirect=''):
        digest=hashlib.sha256(wikitext.encode('utf8')).hexdigest()
        prior=self.db.execute('SELECT xml_hash FROM pages WHERE title=?',(title,)).fetchone()
        self.db.execute('''INSERT INTO pages(title,namespace,xml_id,revision,xml_timestamp,xml_snapshot,xml_hash,raw_source,redirect,seen_xml) VALUES(?,?,?,?,?,?,?,?,?,?)
ON CONFLICT(title) DO UPDATE SET namespace=excluded.namespace,xml_id=excluded.xml_id,revision=excluded.revision,xml_timestamp=excluded.xml_timestamp,xml_snapshot=excluded.xml_snapshot,xml_hash=excluded.xml_hash,raw_source=CASE WHEN pages.xml_hash=excluded.xml_hash THEN pages.raw_source ELSE excluded.raw_source END,redirect=excluded.redirect,seen_xml=excluded.seen_xml''',(title,namespace,xml_id,revision,timestamp,snapshot,digest,zlib.compress(wikitext.encode('utf8')),redirect,snapshot))
        self.db.execute('DELETE FROM aliases WHERE alias=?',(title,))
        if namespace in KNOWLEDGE_NAMESPACES:
            target=(redirect or title).split('#',1)[0];self.add_alias(title,target)
            if namespace==100 and ':' in title:self.add_alias(title.split(':',1)[1],target,owner=title)
        if namespace not in KNOWLEDGE_NAMESPACES or redirect:
            self.db.execute('DELETE FROM chunks WHERE page_id=(SELECT id FROM pages WHERE title=?)',(title,))
            self.db.execute('UPDATE pages SET quality=NULL,body_hash=NULL,body_snapshot=NULL WHERE title=?',(title,))
        self.commit();return prior is None or prior[0]!=digest

    def put_rendered(self,title,blocks,snapshot,digest,quality='rendered_html'):
        prior=self.db.execute('SELECT id,body_hash,quality FROM pages WHERE title=?',(title,)).fetchone()
        self.db.execute('INSERT INTO pages(title,body_snapshot,body_hash,quality,seen_zim) VALUES(?,?,?,?,?) ON CONFLICT(title) DO UPDATE SET body_snapshot=excluded.body_snapshot,body_hash=excluded.body_hash,quality=excluded.quality,seen_zim=excluded.seen_zim',(title,snapshot,digest,quality,snapshot))
        ident=self.db.execute('SELECT id FROM pages WHERE title=?',(title,)).fetchone()[0]
        if prior is None or prior['body_hash']!=digest or prior['quality']!=quality:
            incoming=[(item.get('section',''),item.get('kind','text'),item['text'],item['tokens'] if 'tokens' in item else index_text(title+' '+item.get('section','')+' '+item['text'])) for item in blocks if item.get('text','').strip()]
            existing=[tuple(row) for row in self.db.execute('SELECT section,kind,text,tokens FROM chunks WHERE page_id=? ORDER BY position',(ident,))] if prior else None
            if existing!=incoming:
                self.db.execute('DELETE FROM chunks WHERE page_id=?',(ident,))
                self.db.executemany('INSERT INTO chunks(page_id,position,section,kind,text,tokens) VALUES(?,?,?,?,?,?)',[(ident,index,*item) for index,item in enumerate(incoming)])
        self.add_alias(title,title);self.commit()

    def _resolve(self,db,title):
        title=title.split('#',1)[0]
        seen=set()
        for _ in range(12):
            if title in seen:return None
            seen.add(title);row=db.execute('SELECT * FROM pages WHERE title=?',(title,)).fetchone()
            if row is None:return None
            if not row['redirect']:return row
            title=row['redirect'].split('#',1)[0]
        return None

    def _candidates(self,db,query):
        keys=candidate_keys(query)
        if not keys:return []
        rows=db.execute('SELECT key,target FROM aliases WHERE key IN ('+','.join('?' for _ in keys)+') ORDER BY length(key) DESC LIMIT 32',keys).fetchall()
        records=[];normalized=title_key(query)
        for row in rows:
            page=self._resolve(db,row['target'])
            if page is not None and page['namespace'] in KNOWLEDGE_NAMESPACES:
                canonical=title_key(page['title']);position=normalized.find(canonical)
                priority=(normalized.find(row['key']),-len(row['key']),0 if position>=0 else 1)
                records.append((priority,page))
        pages=[];seen=set()
        for _,page in sorted(records,key=lambda value:value[0]):
            if page['id'] not in seen:
                seen.add(page['id']);pages.append(page)
        return pages[:6]

    def search(self,query,limit=5,max_chars=6500):
        query=str(query).strip()[:160]
        if len(query)<2:return []
        limit=min(8,max(1,int(limit)));tokens=search_tokens(query)[:32]
        expression=' OR '.join('"'+token+'"' for token in tokens)
        with self.connection() as db:
            deadline=time.monotonic()+1.2;db.set_progress_handler(lambda:time.monotonic()>deadline,2000)
            try:
                pages=self._candidates(db,query);candidates={};ranks={p['id']:index for index,p in enumerate(pages)}
                if pages:
                    identifiers=[page['id'] for page in pages[:3]];slots=','.join('?' for _ in identifiers)
                    # Resolve the title first: do not rank the entire corpus for a known page.
                    for row in db.execute('SELECT id,page_id,position,section,kind,tokens FROM chunks WHERE page_id IN ('+slots+')',identifiers):candidates[row['id']]=row
                if not candidates and expression:
                    strict=' AND '.join('"'+token+'"' for token in tokens)
                    for match in dict.fromkeys([strict,expression]):
                        for row in db.execute('SELECT c.*,bm25(chunks_fts) AS rank FROM chunks_fts JOIN chunks c ON c.id=chunks_fts.rowid WHERE chunks_fts MATCH ? ORDER BY rank LIMIT 20',(match,)):candidates[row['id']]=row
                        if candidates:break
                def score(row):
                    overlap=len(set(tokens)&set(row['tokens'].split()))
                    field_bonus=0
                    if re.search(r'速度|攻击|防御|特攻|特防|种族值|\bhp\b',query,re.I) and not re.search(r'基础点数|努力值|击倒|获得|速度[线線]',query):
                        if '种族值' in row['section']:field_bonus+=24
                    if '属性' in query and row['section'].endswith('属性'):field_bonus+=12
                    return (100-ranks[row['page_id']]*15 if row['page_id'] in ranks else 0)+overlap*4+field_bonus-min(20,row['position']*0.015)
                ordered=sorted(candidates.values(),key=score,reverse=True);results=[];remaining=max_chars
                for row in ordered:
                    if len(results)>=limit or remaining<=0:break
                    page=db.execute('SELECT * FROM pages WHERE id=?',(row['page_id'],)).fetchone()
                    body=db.execute('SELECT text FROM chunks WHERE id=?',(row['id'],)).fetchone()[0]
                    excerpt=body[:min(2000,remaining)];remaining-=len(excerpt)
                    result=self._source(page);result.update(section=row['section'],kind=row['kind'],text=excerpt,truncated=len(excerpt)<len(body),position=row['position'])
                    results.append(result)
                return results
            finally:db.set_progress_handler(None,0)

    def _source(self,page):
        return dict(title=page['title'],namespace=page['namespace'],article_kind='appendix' if page['namespace']==100 else 'article',url='https://wiki.52poke.com/wiki/'+quote(page['title'].replace(' ','_'),safe=''),source=SOURCE,license=LICENSE,quality=page['quality'],body_snapshot=page['body_snapshot'],xml_snapshot=page['xml_snapshot'],revision=page['revision'],revision_applies_to='xml_source_only')

    def page(self,title):
        with self.connection() as db:
            row=self._resolve(db,title)
            if row is None:
                candidates=self._candidates(db,title);row=candidates[0] if candidates else None
            return dict(row) if row is not None else {}

    def read(self,title,section='',offset=0,max_chars=4000):
        with self.connection() as db:
            row=self._resolve(db,title)
            if row is None:
                pages=self._candidates(db,title);row=pages[0] if pages else None
            if row is None:return {}
            items=db.execute('SELECT section,text FROM chunks WHERE page_id=? AND section LIKE ? ORDER BY position',(row['id'],'%'+section.replace('%','').replace('_','')+'%'))
            body='\n\n'.join((item['section']+'\n' if item['section'] else '')+item['text'] for item in items)
            if not body and section:
                result=self._source(row)
                sections=[item[0] for item in db.execute('SELECT DISTINCT section FROM chunks WHERE page_id=? LIMIT 30',(row['id'],))]
                result.update(text='',offset=0,next_offset=None,total_chars=0,section_not_found=True,available_sections=sections)
                return result
            if not body and row['raw_source']:body='【原始维基源代码，模板未渲染】\n'+zlib.decompress(row['raw_source']).decode('utf8')
            offset=max(0,int(offset));end=min(len(body),offset+min(6000,max(1,int(max_chars))))
            result=self._source(row);result.update(text=body[offset:end],offset=offset,next_offset=end if end<len(body) else None,total_chars=len(body))
            return result

    def stats(self):
        with self.connection() as db:
            return dict(pages=db.execute('SELECT count(*) FROM pages').fetchone()[0],main_pages=db.execute('SELECT count(*) FROM pages WHERE namespace=0').fetchone()[0],rendered_pages=db.execute("SELECT count(*) FROM pages WHERE quality='rendered_html'").fetchone()[0],chunks=db.execute('SELECT count(*) FROM chunks').fetchone()[0],aliases=db.execute('SELECT count(*) FROM aliases').fetchone()[0])

    def close(self):
        if self.db is not None:self.db.commit();self.db.close();self.db=None
