"""Offline-only streaming builders. Never called by the running bot."""
import gzip,hashlib,json,re,time,zlib
from pathlib import Path
from lxml import etree

def fingerprint(path):
 with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def import_xml(path,store,snapshot,batch_size=500,stop_after=None):
 path=Path(path);digest=fingerprint(path);prior=store.metadata('xml_import',{})
 if prior.get('sha256')==digest and prior.get('complete'):return prior
 resume=prior.get('position',0) if prior.get('sha256')==digest else 0
 count=0;started=time.monotonic();buffer=[]
 def commit(position,complete=False):
  with store.batch():
   for record,redirect in buffer:store.put_xml(*record,snapshot=snapshot,redirect=redirect)
   state=dict(sha256=digest,snapshot=snapshot,position=position,complete=complete)
   store.set_metadata('xml_import',state)
  buffer.clear()
  if position%5000==0:print('XML',position,'seconds',round(time.monotonic()-started,1),flush=True)
  return state
 opener=gzip.open if path.suffix=='.gz' else open
 with opener(path,'rb') as stream:
  for _,page in etree.iterparse(stream,events=('end',),tag='{*}page',huge_tree=True,resolve_entities=False,no_network=True):
   count+=1
   if count>resume:
    def value(parent,name,default=''):
     node=parent.find('{*}'+name);return node.text if node is not None and node.text else default
    revision=page.find('{*}revision');redirect=page.find('{*}redirect')
    if revision is None:raise ValueError('Missing revision: '+value(page,'title'))
    text=value(revision,'text')
    if not text:
     slot=revision.find('.//{*}slot');text=value(slot,'text') if slot is not None else ''
    record=(value(page,'title'),int(value(page,'ns','0')),int(value(page,'id','0')),int(value(revision,'id','0')),value(revision,'timestamp'),text)
    buffer.append((record,redirect.get('title','') if redirect is not None else ''))
    if len(buffer)>=batch_size:commit(count)
   page.clear()
   while page.getprevious() is not None:del page.getparent()[0]
   if stop_after and count>=stop_after:commit(count);return store.metadata('xml_import')
 state=commit(count,False)
 with store.batch():
  deleted=store.db.execute('SELECT count(*) FROM pages WHERE seen_xml IS NULL OR seen_xml!=?',(snapshot,)).fetchone()[0]
  store.db.execute('DELETE FROM chunks WHERE page_id IN (SELECT id FROM pages WHERE seen_xml IS NULL OR seen_xml!=?)',(snapshot,))
  store.db.execute('DELETE FROM aliases WHERE alias IN (SELECT title FROM pages WHERE seen_xml IS NULL OR seen_xml!=?) OR target IN (SELECT title FROM pages WHERE seen_xml IS NULL OR seen_xml!=?)',(snapshot,snapshot))
  store.db.execute('DELETE FROM pages WHERE seen_xml IS NULL OR seen_xml!=?',(snapshot,))
  state['deleted_pages']=deleted;state['complete']=True;store.set_metadata('xml_import',state)
 store.set_metadata('namespaces',dict(store.db.execute('SELECT namespace,count(*) FROM pages WHERE seen_xml=? GROUP BY namespace',(snapshot,)).fetchall()))
 return state

def fallback_missing(store,snapshot,batch_size=200):
 """Keep template parameters verbatim; do not pretend unrendered source is prose."""
 count=0;last=0
 while True:
  rows=store.db.execute("SELECT id,title,raw_source,xml_hash FROM pages WHERE id>? AND namespace IN (0,100) AND redirect='' AND raw_source IS NOT NULL AND (quality IS NULL OR quality='wikitext_fallback') ORDER BY id LIMIT ?",(last,batch_size)).fetchall()
  if not rows:break
  with store.batch():
   for row in rows:
    last=row['id'];raw=zlib.decompress(row['raw_source']).decode('utf8')
    blocks=[dict(kind='wikitext',section='原始维基源代码（模板未渲染）',text=raw[start:start+1800]) for start in range(0,len(raw),1800)]
    store.put_rendered(row['title'],blocks,snapshot,row['xml_hash'],quality='wikitext_fallback');count+=1
 return count

def _extract_job(job):
 from .extract import extract_html
 from .text import index_text
 position,title,raw,digest=job
 try:
  blocks=extract_html(raw.decode('utf8'),title)
  if not blocks:raise ValueError('Empty extracted HTML')
  for block in blocks:block['tokens']=index_text(title+' '+block.get('section','')+' '+block['text'])
  return position,title,digest,blocks,None
 except Exception as exc:return position,title,digest,None,type(exc).__name__+': '+str(exc)[:500]

def import_zim(path,store,snapshot,batch_size=40,stop_after=None,workers=3,namespaces=(0,100)):
 from concurrent.futures import ProcessPoolExecutor
 from libzim.reader import Archive,set_cluster_cache_max_size
 from .extract import EXTRACTOR_VERSION
 path=Path(path);digest=fingerprint(path);prior=store.metadata('zim_import',{})
 same=prior.get('sha256')==digest and prior.get('extractor_version')==EXTRACTOR_VERSION and prior.get('knowledge_namespaces')==list(namespaces)
 if same and prior.get('complete'):return prior
 resume=prior.get('position',0) if same else 0
 with store.batch():
  for row in store.db.execute('SELECT title,redirect FROM pages WHERE namespace=100'):
   target=(row['redirect'] or row['title']).split('#',1)[0]
   store.add_alias(row['title'],target);store.add_alias(row['title'].split(':',1)[-1],target,owner=row['title'])
 set_cluster_cache_max_size(32*1024*1024);archive=Archive(path)
 date=archive.get_metadata('Date').decode('utf8')
 if date!=snapshot:raise ValueError('ZIM metadata date differs from requested snapshot')
 count=0;imported=prior.get('imported',0) if resume else 0;started=time.monotonic();jobs=[]
 def save(pool):
  nonlocal imported
  if not jobs:return
  results=map(_extract_job,jobs) if pool is None else pool.map(_extract_job,jobs,chunksize=1)
  with store.batch():
   for position,title,body_hash,blocks,error in results:
    if error:store.db.execute('INSERT OR REPLACE INTO errors VALUES(?,?,?)',('zim',title,error))
    else:
     store.put_rendered(title,blocks,snapshot,body_hash);imported+=1
     store.db.execute("DELETE FROM errors WHERE stage='zim' AND item=?",(title,))
   state=dict(sha256=digest,snapshot=snapshot,position=jobs[-1][0],imported=imported,complete=False,extractor_version=EXTRACTOR_VERSION,knowledge_namespaces=list(namespaces))
   store.set_metadata('zim_import',state)
  jobs.clear()
  print('ZIM',state['position'],'rendered',imported,'seconds',round(time.monotonic()-started,1),flush=True)
 # Stable physical order for a given checksum, reducing repeated cluster decompression.
 with ProcessPoolExecutor(max_workers=workers) if workers>1 else __import__('contextlib').nullcontext(None) as pool:
  for count,entry in enumerate(archive.iter_efficient(),1):
   if count<=resume:continue
   title=entry.title
   row=store.db.execute('SELECT namespace,redirect FROM pages WHERE title=?',(title,)).fetchone()
   if row is None or row['namespace'] not in namespaces or row['redirect']:continue
   try:
    if entry.is_redirect:
     store.add_alias(title,entry.get_redirect_entry().title);continue
    item=entry.get_item()
    if not item.mimetype.startswith('text/html'):continue
    raw=bytes(item.content);body_hash=hashlib.sha256(raw+b'\x00extractor:'+EXTRACTOR_VERSION.encode()).hexdigest()
    old=store.db.execute('SELECT body_hash,quality,seen_zim,body_snapshot FROM pages WHERE title=?',(title,)).fetchone()
    if old and old['body_hash']==body_hash and old['quality']=='rendered_html':
     if old['seen_zim']!=snapshot or old['body_snapshot']!=snapshot:store.db.execute('UPDATE pages SET seen_zim=?,body_snapshot=? WHERE title=?',(snapshot,snapshot,title))
    else:
     jobs.append((count,title,raw,body_hash))
    store.commit()
   except Exception as exc:
    store.db.execute('INSERT OR REPLACE INTO errors VALUES(?,?,?)',('zim',title,type(exc).__name__+': '+str(exc)[:500]));store.commit()
   if len(jobs)>=batch_size:save(pool)
   if stop_after and imported+len(jobs)>=stop_after:break
  save(pool)
  complete=not stop_after or imported<stop_after
  if complete:
   with store.batch():
    store.db.execute("DELETE FROM chunks WHERE page_id IN (SELECT id FROM pages WHERE quality='rendered_html' AND (seen_zim IS NULL OR seen_zim!=?))",(snapshot,))
    store.db.execute("UPDATE pages SET quality=NULL,body_snapshot=NULL,body_hash=NULL WHERE quality='rendered_html' AND (seen_zim IS NULL OR seen_zim!=?)",(snapshot,))
  state=dict(sha256=digest,snapshot=snapshot,position=count,imported=imported,complete=complete,entries=archive.entry_count,articles=archive.article_count,extractor_version=EXTRACTOR_VERSION,knowledge_namespaces=list(namespaces))
  store.set_metadata('zim_import',state)
 return state

def coverage(store):
 db=store.db
 report=store.stats()
 report.update(main_articles=db.execute("SELECT count(*) FROM pages WHERE namespace=0 AND redirect='' ").fetchone()[0],
  appendix_articles=db.execute("SELECT count(*) FROM pages WHERE namespace=100 AND redirect='' ").fetchone()[0],
  knowledge_articles=db.execute("SELECT count(*) FROM pages WHERE namespace IN (0,100) AND redirect='' ").fetchone()[0],
  redirects=db.execute("SELECT count(*) FROM pages WHERE namespace=0 AND redirect!=''").fetchone()[0],
  fallback_pages=db.execute("SELECT count(*) FROM pages WHERE quality='wikitext_fallback'").fetchone()[0],
  missing_bodies=db.execute("SELECT count(*) FROM pages WHERE namespace IN (0,100) AND redirect='' AND quality IS NULL").fetchone()[0],
  empty_articles=db.execute("SELECT count(*) FROM pages p WHERE namespace IN (0,100) AND redirect='' AND NOT EXISTS(SELECT 1 FROM chunks c WHERE c.page_id=p.id)").fetchone()[0],
  quality_counts=dict(db.execute("SELECT coalesce(quality,'unindexed'),count(*) FROM pages WHERE namespace IN (0,100) AND redirect='' GROUP BY quality").fetchall()),
  errors=[dict(row) for row in db.execute('SELECT * FROM errors LIMIT 100')],
  xml=store.metadata('xml_import'),zim=store.metadata('zim_import'),namespaces=store.metadata('namespaces'))
 return report

def main():
 import argparse
 from .store import KnowledgeStore
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--db',required=True);parser.add_argument('--xml');parser.add_argument('--xml-date');parser.add_argument('--zim');parser.add_argument('--zim-date');parser.add_argument('--fallback',action='store_true')
 args=parser.parse_args();store=KnowledgeStore(args.db)
 try:
  if args.xml:print(import_xml(args.xml,store,args.xml_date),flush=True)
  if args.zim:print(import_zim(args.zim,store,args.zim_date),flush=True)
  if args.fallback:print('FALLBACK',fallback_missing(store,args.xml_date or store.metadata('xml_import')['snapshot']),flush=True)
  report=coverage(store);store.set_metadata('coverage',report)
  Path(args.db).with_suffix('.coverage.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
  print(json.dumps(report,ensure_ascii=True),flush=True)
 finally:store.close()

if __name__=='__main__':main()
