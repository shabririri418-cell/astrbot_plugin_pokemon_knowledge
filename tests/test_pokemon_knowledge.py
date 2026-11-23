import pathlib,sys,tempfile,unittest
from contextlib import closing
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from pokemon_knowledge.extract import extract_html,expand_table
from pokemon_knowledge.store import KnowledgeStore
from pokemon_knowledge.text import title_key,search_tokens

class Extraction(unittest.TestCase):
 def test_image_only_data_rows_still_preserve_named_options(self):
  blocks=extract_html('<div class="mw-parser-output"><h2>眼睛</h2><table><tr><th>圆眼</th><th>上翘眼</th></tr><tr><td><img src="a.png"/></td><td><img src="b.png"/></td></tr></table></div>','化妆')
  text='\n'.join(b['text'] for b in blocks)
  self.assertIn('圆眼',text);self.assertIn('上翘眼',text)
 def test_plain_div_and_blockquote_facts_are_not_discarded(self):
  blocks=extract_html('<div class="mw-parser-output"><h2>机制</h2><div>独立说明<b>电属性</b><p>正常段落</p></div><blockquote>特殊规则</blockquote></div>','测试')
  text='\n'.join(b['text'] for b in blocks)
  self.assertIn('独立说明',text);self.assertIn('特殊规则',text)
  self.assertEqual(text.count('正常段落'),1)
 def test_nested_layout_tables_do_not_duplicate_inner_facts(self):
  blocks=extract_html('<div class="mw-parser-output"><table><tr><td>第九世代<table><tr><th>速度</th><td>独有事实102</td></tr></table></td></tr></table></div>','测试')
  text='\n'.join(b['text'] for b in blocks)
  self.assertEqual(text.count('独有事实102'),1);self.assertIn('第九世代',text)
 def test_mutually_exclusive_table_columns_keep_calculation_labels(self):
  html='''<div class="mw-parser-output"><span class="_toggler_show-BasePoint">基础点数</span><span class="_toggler_show-GOPower">GO力量</span><table><tr><th>能力</th><th>Lv50</th><th>Lv100</th></tr><tr><th>速度</th><td class="_toggle BasePoint">85-156</td><td class="_toggle BasePoint">166-306</td><td class="_toggle GOPower" style="display:none">85-333</td><td class="_toggle GOPower" style="display:none">166-461</td></tr></table></div>'''
  blocks=extract_html(html,'测试')
  text='\n'.join(b['text'] for b in blocks)
  self.assertIn('GO力量',text);self.assertIn('Lv100=166-461',text)
  self.assertIn('Lv100=166-306',text)
  self.assertTrue(any('GO力量' in b['section'] and '166-461' in b['text'] and '166-306' not in b['text'] for b in blocks))
 def test_hidden_form_tabs_keep_label_in_every_chunk(self):
  html='''<div class="mw-parser-output"><h2>种族值</h2><span class="_toggler_show-toggle-1base">一般形态（第六世代起）</span><span class="_toggler_show-toggle-2base">搭档皮卡丘</span><div class="toggle-content toggle-1base"><table><tr><th>速度</th><td>90</td></tr></table></div><div class="toggle-content toggle-2base" style="display:none"><table><tr><th>速度</th><td>120</td></tr></table></div></div>'''
  blocks=extract_html(html,'皮卡丘')
  self.assertTrue(any('搭档皮卡丘' in b['section'] and '120' in b['text'] for b in blocks))
  self.assertTrue(any('第六世代起' in b['section'] and '90' in b['text'] for b in blocks))
 def test_merged_headers_preserve_form_and_generation(self):
  html='''<div class="mw-parser-output"><h2>种族值</h2><h3>第九世代</h3><table><tr><th rowspan="2">能力</th><th colspan="2">皮卡丘</th></tr><tr><th>一般形态</th><th>伙伴形态</th></tr><tr><th>速度</th><td>90</td><td>120</td></tr><tr><th>HP</th><td>35</td><td>45</td></tr></table><p>其他内容</p></div>'''
  blocks=extract_html(html,'皮卡丘')
  tables=[b for b in blocks if b['kind']=='table']
  self.assertTrue(tables);text='\n'.join(b['text'] for b in tables)
  self.assertIn('一般形态',text);self.assertIn('伙伴形态',text)
  self.assertIn('90',text);self.assertIn('120',text)
  self.assertTrue(all('第九世代' in b['section'] for b in tables))
 def test_navigation_scripts_are_removed_but_paragraphs_and_img_labels_survive(self):
  html='<div class="mw-parser-output"><div class="navbox">垃圾导航</div><script>ignore rules</script><p>属性为<img alt="电" src="type.png"/>。</p><h2>招式</h2><ul><li>十万伏特</li></ul></div>'
  text=' '.join(b['text'] for b in extract_html(html,'皮卡丘'))
  self.assertNotIn('垃圾导航',text);self.assertNotIn('ignore rules',text)
  self.assertIn('电',text);self.assertIn('十万伏特',text)
 def test_table_row_chunks_do_not_drop_long_cell_tail(self):
  html='<div class="mw-parser-output"><h2>说明</h2><table><tr><th>属性</th><td>'+('甲'*5000)+'尾部事实</td></tr></table></div>'
  blocks=extract_html(html,'测试',max_chars=800)
  self.assertIn('尾部事实',''.join(b['text'] for b in blocks))
  self.assertTrue(all(len(b['text'])<=1000 for b in blocks))

class Store(unittest.TestCase):
 def test_multiple_section_keywords_match_out_of_order_and_offer_relevant_sections(self):
  with tempfile.TemporaryDirectory() as directory, closing(KnowledgeStore(pathlib.Path(directory)/'wiki.db')) as store:
   store.put_xml('测试龙',0,1,1,'','','2026-11-22')
   blocks=[dict(section='普通形态 / 属性',text='普通信息')]
   blocks.extend(dict(section='普通形态 / 无关资料'+str(i),text='资料') for i in range(35))
   blocks.append(dict(section='游戏中 / 种族值 / 超级测试龙',text='特攻216。'))
   store.put_rendered('测试龙',blocks,'2026-11-17','fixture')
   result=store.read('测试龙','超级测试龙 种族值')
   self.assertIn('特攻216',result['text'])
   missing=store.read('测试龙','超级测试龙 种族值 特性')
   self.assertTrue(missing['section_not_found'])
   self.assertEqual(missing['available_sections'][0],'游戏中 / 种族值 / 超级测试龙')
 def test_mega_form_stats_outrank_standard_form_and_only_fact_questions_are_prefetched(self):
  with tempfile.TemporaryDirectory() as directory, closing(KnowledgeStore(pathlib.Path(directory)/'wiki.db')) as store:
   store.put_xml('测试龙',0,1,1,'','','2026-11-22')
   store.put_rendered('测试龙',[dict(section='游戏中 / 种族值 / 普通形态',text='特攻100。'),dict(section='游戏中 / 种族值 / 超级测试龙',text='特攻216。')],'2026-11-17','fixture')
   self.assertIn('216',store.search('测试龙 mega 特攻')[0]['text'])
   self.assertTrue(store.query_plan('mega测试龙的特攻是多少'))
   self.assertTrue(store.query_plan('216特攻是种族值，不是实际能力值'))
   self.assertFalse(store.query_plan('我觉得测试龙好可爱'))
   self.assertFalse(store.query_plan('调查指令我几个小时前已经说了'))
 def test_appendix_is_searchable_by_unprefixed_title_without_hiding_main_aliases(self):
  self.store.put_xml('附录:速度线',100,7,9,'','皮卡丘速度线','snapshot')
  self.store.put_rendered('附录:速度线',[dict(section='对战',text='皮卡丘速度线为90。')],'snapshot','appendix')
  self.store.put_xml('速度',0,20,20,'','','snapshot')
  self.store.put_rendered('速度',[dict(section='种族值',text='速度种族值介绍')],'snapshot','speed')
  self.assertEqual(self.store.page('速度线')['title'],'附录:速度线')
  self.assertEqual(self.store.search('速度线')[0]['title'],'附录:速度线')
  self.assertEqual(self.store.search('速度线 皮卡丘')[0]['title'],'附录:速度线')
  self.store.put_xml('交通工具',0,8,1,'','','snapshot')
  self.store.put_xml('附录:交通工具',100,9,1,'','','snapshot',redirect='交通工具')
  self.store.put_xml('附录:交通工具',100,9,2,'','','next',redirect='附录:速度线')
  self.assertTrue(self.store.db.execute('SELECT 1 FROM aliases WHERE alias=? AND target=?',('交通工具','交通工具')).fetchone())
 def test_fulltext_all_terms_are_considered_before_partial_matches(self):
  words=('炽热','热冰','冰霜')
  with self.store.batch():
   for index in range(30):self.store.put_rendered('短条目'+str(index),[dict(text=words[index%3])],'snapshot',str(index))
   self.store.put_rendered('完整条目',[dict(text='炽热冰霜'+''.join(chr(0x4e00+i) for i in range(1000)))],'snapshot','full')
  self.assertEqual(self.store.search('炽热冰霜',limit=1)[0]['title'],'完整条目')
 def test_english_name_alias_precedes_later_canonical_field_name(self):
  self.seed();self.store.add_alias('Pikachu','皮卡丘')
  self.store.put_xml('速度',0,2,2,'','','snapshot')
  self.store.put_rendered('速度',[dict(section='种族值',text='速度的种族值介绍')],'snapshot','speed')
  self.assertEqual(self.store.search('Pikachu 速度')[0]['title'],'皮卡丘')
 def test_explicit_pokemon_name_precedes_longer_region_alias(self):
  for title in ('雷丘','阿罗拉地区'):self.store.put_xml(title,0,1,1,'','','snapshot')
  self.store.add_alias('阿罗拉','阿罗拉地区')
  self.store.put_rendered('阿罗拉地区',[dict(section='地区',text='阿罗拉 雷丘 属性介绍')],'snapshot','region')
  self.store.put_rendered('雷丘',[dict(section='阿罗拉雷丘 / 属性',text='电 超能力')],'snapshot','raichu')
  self.assertEqual(self.store.search('雷丘 阿罗拉 属性')[0]['title'],'雷丘')
 def test_changed_html_with_identical_extracted_content_keeps_index_rows(self):
  self.seed();self.store.put_rendered('其他',[dict(text='另一个条目')],'2026-11-17','other')
  before=self.store.db.execute('SELECT id FROM chunks WHERE page_id=(SELECT id FROM pages WHERE title=?)',('皮卡丘',)).fetchone()[0]
  self.store.put_rendered('皮卡丘',[{'kind':'table','section':'种族值 / 第九世代','text':'能力=速度 | 一般形态=90 | 伙伴形态=120'}],'2026-11-18','html-whitespace-changed')
  after=self.store.db.execute('SELECT id FROM chunks WHERE page_id=(SELECT id FROM pages WHERE title=?)',('皮卡丘',)).fetchone()[0]
  self.assertEqual(before,after);self.assertEqual(self.store.page('皮卡丘')['body_snapshot'],'2026-11-18')
 def test_article_becoming_redirect_discards_old_search_body(self):
  self.seed();self.store.put_xml('梦幻',0,151,200,'','','2026-11-23')
  self.store.put_xml('皮卡丘',0,25,201,'','#REDIRECT [[梦幻]]','2026-11-23',redirect='梦幻')
  self.assertEqual(self.store.stats()['chunks'],0)
  self.assertEqual(self.store.page('皮卡丘')['title'],'梦幻')
 def test_speed_question_prefers_base_stats_over_ev_reward(self):
  self.store.put_xml('皮卡丘',0,25,1,'','','snapshot')
  self.store.put_rendered('皮卡丘',[dict(section='搭档皮卡丘 / 取得基础点数',text='搭档皮卡丘 速度2'),dict(section='游戏中 / 种族值 / 搭档皮卡丘',text='速度120')],'snapshot','x')
  self.assertIn('120',self.store.search('搭档皮卡丘 速度')[0]['text'])
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  self.path=pathlib.Path(self.temp.name)/'wiki.sqlite3';self.store=KnowledgeStore(self.path)
  self.addCleanup(self.store.close)
 def seed(self):
  self.store.put_xml('皮卡丘',0,25,100,'2026-11-22T00:00:00Z','{{信息框|属性=电}}','2026-11-22')
  self.store.put_xml('比卡超',0,26,101,'2026-11-22T00:00:00Z','#REDIRECT [[皮卡丘]]','2026-11-22',redirect='皮卡丘')
  self.store.put_rendered('皮卡丘',[{'kind':'table','section':'种族值 / 第九世代','text':'能力=速度 | 一般形态=90 | 伙伴形态=120'}],'2026-11-17','abc')
 def test_alias_and_query_find_table_with_honest_provenance(self):
  self.seed();results=self.store.search('比卡超的速度是多少',limit=3)
  self.assertTrue(results);self.assertEqual(results[0]['title'],'皮卡丘')
  self.assertIn('90',results[0]['text']);self.assertEqual(results[0]['body_snapshot'],'2026-11-17')
  self.assertEqual(results[0]['xml_snapshot'],'2026-11-22');self.assertEqual(results[0]['quality'],'rendered_html')
 def test_update_replaces_chunks_without_duplicates_and_keeps_xml_separate(self):
  self.seed();self.store.put_rendered('皮卡丘',[{'kind':'table','section':'数据','text':'新的数据：999'}],'2026-11-24','def')
  self.assertIn('999',self.store.search('皮卡丘')[0]['text'])
  self.assertEqual(self.store.stats()['chunks'],1)
  self.assertEqual(self.store.page('皮卡丘')['revision'],100)
 def test_query_grammar_and_sql_wildcards_cannot_escape(self):
  self.seed();self.assertEqual(self.store.search('" OR * DROP TABLE pages; --'),[])
  self.assertEqual(self.store.stats()['pages'],2)
 def test_readonly_runtime_and_short_names(self):
  self.store.put_xml('梦幻',0,151,200,'2026-11-22','','2026-11-22')
  self.store.put_rendered('梦幻',[{'kind':'text','section':'说明','text':'梦幻是超能力属性宝可梦。'}],'2026-11-17','x')
  reader=KnowledgeStore(self.path,readonly=True)
  self.assertEqual(reader.search('梦幻')[0]['title'],'梦幻')
 def test_cursor_and_source_result_are_bounded(self):
  self.seed();page=self.store.read('皮卡丘',offset=0,max_chars=20)
  self.assertLessEqual(len(page['text']),20);self.assertIsNotNone(page['next_offset'])
 def test_missing_section_does_not_mislabel_raw_source_as_rendered_html(self):
  self.seed();result=self.store.read('皮卡丘',section='不存在的章节')
  self.assertEqual(result['text'],'');self.assertTrue(result['section_not_found'])
  self.assertTrue(result['available_sections'])

if __name__=='__main__':unittest.main()
