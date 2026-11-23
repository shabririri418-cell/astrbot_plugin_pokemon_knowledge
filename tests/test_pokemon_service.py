import asyncio,json,pathlib,sys,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from pokemon_knowledge.store import KnowledgeStore
from pokemon_knowledge.service import KnowledgeService,source_urls,retain_source

class References(unittest.TestCase):
 def test_sources_stay_internal_without_appending_them_to_answers(self):
  payload=json.dumps(dict(available=True,results=[dict(text='事实',url='https://wiki.52poke.com/wiki/test')]))
  urls=source_urls(payload);self.assertEqual(urls,['https://wiki.52poke.com/wiki/test'])
  self.assertEqual(retain_source('自然回答',urls),'自然回答')
  self.assertEqual(retain_source('日常闲聊',[]),'日常闲聊')
  self.assertEqual(source_urls(json.dumps(dict(available=False,results=[]))),[])
 def test_existing_reference_is_not_duplicated_and_external_urls_are_rejected(self):
  text='参考：https://wiki.52poke.com/wiki/test'
  self.assertEqual(retain_source(text,['https://wiki.52poke.com/wiki/test']),text)
  self.assertEqual(retain_source('正文',['https://wiki.52poke.com.evil/wiki/fake']),'正文')

class Service(unittest.IsolatedAsyncioTestCase):
 async def test_unbuilt_database_never_claims_available(self):
  with tempfile.TemporaryDirectory() as directory:
   service=KnowledgeService(pathlib.Path(directory)/'missing.sqlite3')
   result=json.loads(await service.query('search',query='皮卡丘'))
   self.assertFalse(result['available']);self.assertFalse(service.store.path.exists())
 async def test_ready_readonly_service_and_bounded_response(self):
  with tempfile.TemporaryDirectory() as directory:
   path=pathlib.Path(directory)/'wiki.db';writer=KnowledgeStore(path)
   writer.put_xml('皮卡丘',0,25,5,'2026-11-22','','2026-11-22')
   writer.put_rendered('皮卡丘',[dict(text='电属性。速度90。',section='一般形态 / 第六世代起')],'2026-11-17','a')
   writer.set_metadata('coverage',dict(xml={'complete':True},zim={'complete':True,'knowledge_namespaces':[0,100]},main_articles=1,missing_bodies=0))
   writer.set_metadata('xml_import',{'complete':True});writer.set_metadata('zim_import',{'complete':True,'knowledge_namespaces':[0,100]})
   writer.close();service=KnowledgeService(path)
   result=json.loads(await service.query('search',query='皮卡丘的速度'))
   self.assertTrue(result['available']);self.assertIn('90',result['results'][0]['text'])
   self.assertEqual(result['results'][0]['body_snapshot'],'2026-11-17')
   self.assertIn('不播报',result['notice']);self.assertIsNone(service.store.db)
 async def test_stale_complete_manifest_cannot_expose_partially_updated_database(self):
  with tempfile.TemporaryDirectory() as directory:
   path=pathlib.Path(directory)/'wiki.db';writer=KnowledgeStore(path)
   writer.set_metadata('coverage',dict(xml={'complete':True},zim={'complete':True},main_articles=1,missing_bodies=0))
   writer.set_metadata('xml_import',{'complete':True});writer.set_metadata('zim_import',{'complete':False,'position':2})
   writer.close();service=KnowledgeService(path)
   result=json.loads(await service.query('search',query='皮卡丘'))
   self.assertFalse(result['available'])

if __name__=='__main__':unittest.main()
