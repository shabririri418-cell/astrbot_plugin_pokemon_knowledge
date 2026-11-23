import gzip,pathlib,sys,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from pokemon_knowledge.store import KnowledgeStore
from pokemon_knowledge.builder import import_xml,import_zim,fallback_missing

class Builder(unittest.TestCase):
 def test_namespace_expansion_adds_appendix_without_reindexing_existing_article(self):
  from libzim.writer import Creator,Item,StringProvider
  class Article(Item):
   def __init__(self,title):self.title=title
   def get_path(self):return self.title
   def get_title(self):return self.title
   def get_mimetype(self):return 'text/html'
   def get_contentprovider(self):return StringProvider('<p>'+self.title+'的知识</p>')
   def get_hints(self):return {}
  with tempfile.TemporaryDirectory() as directory:
   root=pathlib.Path(directory);path=root/'test.zim'
   with Creator(path).config_indexing(False,'zho').config_nbworkers(1) as creator:
    creator.add_metadata('Date','2026-11-17')
    for title in ('皮卡丘','附录:速度线'):creator.add_item(Article(title))
   db=KnowledgeStore(root/'wiki.db')
   try:
    db.put_xml('皮卡丘',0,1,1,'','','2026-11-22');db.put_xml('附录:速度线',100,2,2,'','','2026-11-22')
    import_zim(path,db,'2026-11-17',workers=1,namespaces=(0,))
    before=db.db.execute('SELECT id FROM chunks').fetchone()[0]
    self.assertEqual(db.stats()['rendered_pages'],1)
    import_zim(path,db,'2026-11-17',workers=1)
    self.assertEqual(db.stats()['rendered_pages'],2)
    self.assertEqual(db.db.execute('SELECT id FROM chunks WHERE page_id=(SELECT id FROM pages WHERE title=?)',('皮卡丘',)).fetchone()[0],before)
    self.assertEqual(db.metadata('zim_import')['knowledge_namespaces'],[0,100])
    self.assertEqual(db.search('速度线')[0]['article_kind'],'appendix')
   finally:db.close()
 def test_new_zim_snapshot_skips_unchanged_body_and_retires_removed_body(self):
  from libzim.writer import Creator,Item,StringProvider
  class Article(Item):
   def __init__(self,title):self.title=title
   def get_path(self):return self.title
   def get_title(self):return self.title
   def get_mimetype(self):return 'text/html'
   def get_contentprovider(self):return StringProvider('<p>'+self.title+'的正文</p>')
   def get_hints(self):return {}
  with tempfile.TemporaryDirectory() as directory:
   root=pathlib.Path(directory);db=KnowledgeStore(root/'wiki.db')
   try:
    for title in ('皮卡丘','梦幻'):db.put_xml(title,0,1,1,'','{{数据|新参数=99}}','2026-11-22')
    for date,titles in [('2026-11-17',('皮卡丘','梦幻')),('2026-11-18',('皮卡丘',))]:
     path=root/(date+'.zim')
     with Creator(path).config_indexing(False,'zho').config_nbworkers(1) as creator:
      creator.add_metadata('Date',date)
      for title in titles:creator.add_item(Article(title))
     if date=='2026-11-18':old_id=db.db.execute('SELECT id FROM chunks WHERE page_id=(SELECT id FROM pages WHERE title=?)',('皮卡丘',)).fetchone()[0]
     import_zim(path,db,date,workers=1)
    self.assertEqual(db.db.execute('SELECT id FROM chunks WHERE page_id=(SELECT id FROM pages WHERE title=?)',('皮卡丘',)).fetchone()[0],old_id)
    self.assertEqual(db.page('皮卡丘')['body_snapshot'],'2026-11-18')
    self.assertIsNone(db.page('梦幻')['quality'])
    fallback_missing(db,'2026-11-22')
    self.assertEqual(db.page('梦幻')['quality'],'wikitext_fallback')
    self.assertIn('新参数=99',db.read('梦幻')['text'])
    self.assertEqual(db.stats()['chunks'],2)
   finally:db.close()
 def test_real_zim_container_import_and_resume(self):
  from libzim.writer import Creator,Item,StringProvider
  class Article(Item):
   def __init__(self,title,text):self.title=title;self.text=text
   def get_path(self):return self.title
   def get_title(self):return self.title
   def get_mimetype(self):return 'text/html'
   def get_contentprovider(self):return StringProvider(self.text)
   def get_hints(self):return {}
  with tempfile.TemporaryDirectory() as directory:
   root=pathlib.Path(directory);path=root/'test.zim'
   with Creator(path).config_indexing(False,'zho').config_nbworkers(1) as creator:
    creator.add_metadata('Date','2026-11-17')
    creator.add_item(Article('皮卡丘','<p>皮卡丘是电属性。</p>'))
    creator.add_item(Article('梦幻','<p>梦幻是超能力属性。</p>'))
   db=KnowledgeStore(root/'wiki.db')
   try:
    for title in ('皮卡丘','梦幻'):db.put_xml(title,0,1,1,'','','2026-11-22')
    import_zim(path,db,'2026-11-17',stop_after=1,workers=1)
    self.assertEqual(db.stats()['rendered_pages'],1)
    import_zim(path,db,'2026-11-17',workers=1)
    self.assertEqual(db.stats()['rendered_pages'],2)
    self.assertTrue(db.metadata('zim_import')['complete'])
    self.assertIn('电属性',db.search('皮卡丘')[0]['text'])
   finally:db.close()
 def test_new_snapshot_removes_deleted_pages_and_redirect_target(self):
  with tempfile.TemporaryDirectory() as directory:
   root=pathlib.Path(directory);source=root/'wiki.xml.gz';db=KnowledgeStore(root/'wiki.db')
   try:
    db.put_xml('过时条目',0,1,1,'','','old')
    db.put_rendered('过时条目',[dict(text='旧内容')],'old','x')
    db.put_xml('别名',0,2,2,'','','old',redirect='过时条目')
    data='<mediawiki><page><title>新条目</title><ns>0</ns><id>3</id><revision><id>3</id><text>新内容</text></revision></page><page><title>别名</title><ns>0</ns><id>2</id><redirect title="新条目"/><revision><id>4</id><text>redirect</text></revision></page></mediawiki>'
    with gzip.open(source,'wt',encoding='utf8') as stream:stream.write(data)
    import_xml(source,db,'new')
    self.assertFalse(db.page('过时条目'));self.assertEqual(db.page('别名')['title'],'新条目')
    self.assertEqual(db.stats()['chunks'],0)
    self.assertEqual(db.db.execute('SELECT target FROM aliases WHERE alias=?',('别名',)).fetchall()[0][0],'新条目')
    self.assertEqual(db.metadata('xml_import')['deleted_pages'],1)
   finally:db.close()
 def test_streaming_xml_revision_redirect_and_resume(self):
  with tempfile.TemporaryDirectory() as directory:
   root=pathlib.Path(directory);source=root/'wiki.xml.gz';db=KnowledgeStore(root/'wiki.db')
   try:
    data='''<mediawiki xmlns="http://www.mediawiki.org/xml/export-0.11/"><siteinfo><namespaces><namespace key="0"/><namespace key="10">模板</namespace></namespaces></siteinfo><page><title>皮卡丘</title><ns>0</ns><id>25</id><revision><id>900</id><timestamp>2026-11-22</timestamp><text>{{信息框|属性=电}}\n==种族值==\n速度90</text></revision></page><page><title>比卡超</title><ns>0</ns><id>26</id><redirect title="皮卡丘#种族值"/><revision><id>901</id><text>#REDIRECT [[皮卡丘#种族值]]</text></revision></page><page><title>模板:信息框</title><ns>10</ns><id>27</id><revision><id>902</id><text>模板内容</text></revision></page></mediawiki>'''
    with gzip.open(source,'wt',encoding='utf8') as stream:stream.write(data)
    import_xml(source,db,'2026-11-22',batch_size=1,stop_after=1)
    self.assertEqual(db.stats()['pages'],1)
    import_xml(source,db,'2026-11-22',batch_size=1)
    self.assertEqual(db.stats()['pages'],3)
    self.assertEqual(db.page('皮卡丘')['xml_id'],25)
    self.assertEqual(db.page('皮卡丘')['revision'],900)
    self.assertEqual(db.page('比卡超')['title'],'皮卡丘')
    fallback_missing(db,'2026-11-22')
    result=db.search('皮卡丘 速度')[0]
    self.assertEqual(result['quality'],'wikitext_fallback')
    self.assertIn('属性=电',db.read('皮卡丘')['text'])
    self.assertEqual(db.metadata('xml_import')['complete'],True)
   finally:db.close()

if __name__=='__main__':unittest.main()
