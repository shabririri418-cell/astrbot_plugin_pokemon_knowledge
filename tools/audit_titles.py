"""Independently compare source title sets with index coverage; never modifies the DB."""
import argparse,hashlib,json,pathlib,sqlite3
from libzim.reader import Archive
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--verify-index',action='store_true');parser.add_argument('--db',type=pathlib.Path,required=True);parser.add_argument('--zim',type=pathlib.Path,required=True);parser.add_argument('--output',type=pathlib.Path,required=True);args=parser.parse_args()
db=sqlite3.connect(args.db.resolve().as_uri()+'?mode=ro',uri=True)
main={row[0] for row in db.execute("SELECT title FROM pages WHERE namespace=0 AND redirect=''")}
appendix={row[0] for row in db.execute("SELECT title FROM pages WHERE namespace=100 AND redirect=''")}
titles=main|appendix
zim_path=args.zim;archive=Archive(zim_path)
eligible=set();old_redirects={};other_mimes={}
for entry in archive.iter_efficient():
 title=entry.title
 if title not in titles:continue
 if entry.is_redirect:old_redirects[title]=entry.get_redirect_entry().title;continue
 mime=entry.get_item().mimetype
 if mime.startswith('text/html'):eligible.add(title)
 else:other_mimes[title]=mime
fallback=titles-eligible
def checksum(values):return hashlib.sha256('\n'.join(sorted(values)).encode()).hexdigest()
report=dict(xml_main_articles=len(main),xml_appendix_articles=len(appendix),knowledge_articles=len(titles),expected_rendered=len(eligible),expected_fallback=len(fallback),rendered_title_sha256=checksum(eligible),fallback_title_sha256=checksum(fallback),older_zim_redirects=old_redirects,non_html_mimes=other_mimes,fallback_titles=sorted(fallback))
with zim_path.open('rb') as stream:report['zim_sha256']=hashlib.file_digest(stream,'sha256').hexdigest()
if args.verify_index:
 rendered={r[0] for r in db.execute("SELECT title FROM pages WHERE namespace IN (0,100) AND redirect='' AND quality='rendered_html'")}
 actual_fallback={r[0] for r in db.execute("SELECT title FROM pages WHERE namespace IN (0,100) AND redirect='' AND quality='wikitext_fallback'")}
 assert rendered==eligible,dict(missing=sorted(eligible-rendered)[:30],unexpected=sorted(rendered-eligible)[:30])
 assert actual_fallback==fallback,dict(missing=sorted(fallback-actual_fallback)[:30],unexpected=sorted(actual_fallback-fallback)[:30])
 assert db.execute('SELECT count(*) FROM pages WHERE raw_source IS NULL').fetchone()[0]==0
 report['verified_index']=True
args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({k:v for k,v in report.items() if k not in ('fallback_titles','older_zim_redirects')},ensure_ascii=True));print('OLDER_REDIRECTS',json.dumps(old_redirects,ensure_ascii=True))
