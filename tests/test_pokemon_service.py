import asyncio,json,pathlib,sys,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from pokemon_knowledge.store import KnowledgeStore
from pokemon_knowledge.service import KnowledgeService,source_urls,retain_source,damage_clarification

class References(unittest.TestCase):
 def test_damage_parameters_do_not_gate_ordinary_type_questions(self):
  self.assertIn('游戏版本',damage_clarification('什么宝可梦能扛一发归无之光'))
  self.assertIsNone(damage_clarification('快龙不是二倍弱龙吗'))
  self.assertIsNone(damage_clarification('主系列100级，双方个体值31努力值252内敛，特防300，能扛一发吗'))
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
 async def test_reviewer_receives_only_current_evidence_and_fails_closed(self):
  from unittest.mock import AsyncMock
  from types import SimpleNamespace
  service=KnowledgeService('unused.sqlite3')
  provider=SimpleNamespace(text_chat=AsyncMock(return_value=SimpleNamespace(completion_text='快龙是龙／飞行，二倍弱龙。')))
  evidence={'results':[{'title':'快龙','text':'属性：龙 飞行'}]}
  text=await service.review('快龙不是二倍弱龙吗','归无之光是无极汰那的招式。',evidence,provider)
  self.assertEqual(text,'快龙是龙／飞行，二倍弱龙。')
  call=provider.text_chat.call_args.kwargs
  self.assertEqual(call['contexts'],[]);self.assertIsNone(call['func_tool'])
  self.assertIn('最大',call['system_prompt']);self.assertIn('属性：龙 飞行',call['prompt'])
  provider.text_chat.side_effect=RuntimeError('offline')
  self.assertNotIn('无极汰那',await service.review('快龙','无极汰那',evidence,provider))
 async def test_current_fact_prefetch_is_real_bounded_and_unrelated_chat_is_skipped(self):
  with tempfile.TemporaryDirectory() as directory:
   path=pathlib.Path(directory)/'wiki.db';writer=KnowledgeStore(path)
   writer.put_xml('测试龙',0,1,1,'','','2026-11-22')
   writer.put_rendered('测试龙',[dict(section='种族值 / 超级测试龙',text='特攻216。')],'2026-11-17','fixture')
   xml={'complete':True};zim={'complete':True,'knowledge_namespaces':[0,100]}
   writer.set_metadata('xml_import',xml);writer.set_metadata('zim_import',zim)
   writer.set_metadata('coverage',dict(xml=xml,zim=zim,main_articles=1,missing_bodies=0));writer.close()
   service=KnowledgeService(path)
   self.assertIsNone(await service.prepare('今天想吃什么'))
   result=await service.prepare('mega测试龙的特攻是多少？')
   self.assertTrue(result['available']);self.assertIn('216',result['results'][0]['text'])
   self.assertLessEqual(sum(len(row['text']) for row in result['results']),4800)
   self.assertIn('参数',result['notice'])
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
