import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from pokemon_knowledge.store import KnowledgeStore


class CLI(unittest.TestCase):
    def invoke(self, path, *args):
        return subprocess.run([sys.executable, '-m', 'pokemon_knowledge', '--db', str(path), *args],
                              text=True, encoding='utf8', capture_output=True,
                              env={**os.environ, 'PYTHONUTF8': '1'})

    def test_missing_database_reports_unavailable_without_creating_it(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'missing.sqlite3'
            response = self.invoke(path, 'status')
            self.assertEqual(response.returncode, 0, response.stderr)
            self.assertFalse(json.loads(response.stdout)['ready'])
            self.assertFalse(path.exists())

    def test_query_and_seal_then_query_the_same_database(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'fixture.sqlite3'
            writer = KnowledgeStore(path)
            writer.put_xml('示例条目', 0, 1, 1, '', '', '2026-11-22')
            writer.put_rendered('示例条目', [dict(section='测试', text='这是一条合成的测试事实。')], '2026-11-17', 'fixture')
            xml = dict(complete=True, snapshot='2026-11-22')
            zim = dict(complete=True, snapshot='2026-11-17', knowledge_namespaces=[0, 100], extractor_version='6')
            from pokemon_knowledge.builder import coverage
            writer.set_metadata('xml_import', xml)
            writer.set_metadata('zim_import', zim)
            writer.set_metadata('coverage', coverage(writer))
            writer.close()
            sealed = self.invoke(path, 'seal')
            self.assertEqual(sealed.returncode, 0, sealed.stderr)
            manifest = json.loads(sealed.stdout)
            self.assertEqual(len(manifest['database_sha256']), 64)
            self.assertEqual(manifest['integrity_checks']['fts_external_content'], 'ok')
            answer = self.invoke(path, 'search', '示例条目')
            self.assertEqual(answer.returncode, 0, answer.stderr)
            data = json.loads(answer.stdout)
            self.assertTrue(data['available'])
            self.assertIn('合成的测试事实', data['results'][0]['text'])
            self.assertTrue(data['results'][0]['url'].startswith('https://wiki.52poke.com/'))

    def test_partial_database_cannot_be_sealed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'partial.sqlite3'
            KnowledgeStore(path).close()
            response = self.invoke(path, 'seal')
            self.assertNotEqual(response.returncode, 0)
            self.assertFalse(path.with_suffix('.manifest.json').exists())
