"""Independent, streaming, read-only validation of every archived XML source byte."""
import argparse,gzip,hashlib,json,pathlib,sqlite3,time,zlib
from lxml import etree
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--db',type=pathlib.Path,required=True);parser.add_argument('--xml',type=pathlib.Path,required=True);parser.add_argument('--output',type=pathlib.Path,required=True);args=parser.parse_args()
source=args.xml;db=sqlite3.connect(args.db.resolve().as_uri()+'?mode=ro',uri=True)
count=0;namespaces={};started=time.monotonic()
with gzip.open(source,'rb') as stream:
 for _,page in etree.iterparse(stream,events=('end',),tag='{*}page',huge_tree=True,resolve_entities=False,no_network=True):
  title=page.findtext('{*}title');namespace=int(page.findtext('{*}ns'));ident=int(page.findtext('{*}id'))
  revision=page.find('{*}revision');revision_id=int(revision.findtext('{*}id'));timestamp=revision.findtext('{*}timestamp') or ''
  text=revision.findtext('{*}text')
  if text is None:text=revision.findtext('./{*}slots/{*}slot/{*}text') or ''
  digest=hashlib.sha256(text.encode('utf8')).hexdigest()
  redirect=page.find('{*}redirect');redirect_title=redirect.get('title','') if redirect is not None else ''
  row=db.execute('SELECT namespace,xml_id,revision,xml_timestamp,xml_hash,raw_source,redirect FROM pages WHERE title=?',(title,)).fetchone()
  assert row is not None,('MISSING_PAGE',title)
  assert row[:5]==(namespace,ident,revision_id,timestamp,digest),('METADATA_MISMATCH',title)
  assert zlib.decompress(row[5]).decode('utf8')==text,('RAW_SOURCE_MISMATCH',title)
  assert row[6]==redirect_title,('REDIRECT_MISMATCH',title)
  count+=1;namespaces[namespace]=namespaces.get(namespace,0)+1
  page.clear()
  while page.getprevious() is not None:del page.getparent()[0]
assert count==db.execute('SELECT count(*) FROM pages').fetchone()[0]
with source.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
report=dict(verified_pages=count,namespaces=namespaces,xml_gzip_sha256=digest,raw_sources_exact=True,metadata_exact=True,seconds=round(time.monotonic()-started,2))
args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
print('ALL_XML_SOURCE_BYTES_VERIFIED',json.dumps(report,ensure_ascii=True),flush=True)
