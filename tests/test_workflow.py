"""Build, audit, seal and query a generated tiny XML/ZIM snapshot, offline."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

from libzim.writer import Creator, Item, StringProvider

ROOT = Path(__file__).resolve().parents[1]


class Article(Item):
    def __init__(self, title): self.title = title
    def get_path(self): return self.title
    def get_title(self): return self.title
    def get_mimetype(self): return 'text/html'
    def get_contentprovider(self): return StringProvider('<p>这是一条合成的知识说明。</p>')
    def get_hints(self): return {}


class Workflow(unittest.TestCase):
    def run_command(self, *arguments):
        result = subprocess.run([sys.executable, *map(str, arguments)], cwd=ROOT,
                                env={**os.environ, 'PYTHONUTF8': '1'}, capture_output=True,
                                text=True, encoding='utf8')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def test_archive_build_audit_seal_and_read(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            xml = b'<mediawiki><page><title>Example</title><ns>0</ns><id>1</id><revision><id>10</id><timestamp>2026-11-22T00:00:00Z</timestamp><text>synthetic source</text></revision></page></mediawiki>'
            archive = root / 'test.zip'
            payload = gzip.compress(xml)
            with zipfile.ZipFile(archive, 'w') as zipped:
                # Extraction never trusts the member path; caller picks the destination.
                zipped.writestr('../source.xml.gz', payload)
            xml_path = root / 'snapshot.xml.gz'
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            self.run_command('tools/extract_archive.py', archive, '--sha256', digest,
                             '--suffix', '.xml.gz', '--output', xml_path)
            self.assertEqual(gzip.decompress(xml_path.read_bytes()), xml)
            self.assertFalse((root.parent / 'source.xml.gz').exists())
            zim = root / 'snapshot.zim'
            with Creator(zim).config_indexing(False, 'zho').config_nbworkers(1) as creator:
                creator.add_metadata('Date', '2026-11-17')
                creator.add_item(Article('Example'))
            db = root / 'pokemon.sqlite3'
            self.run_command('-m', 'pokemon_knowledge.builder', '--db', db, '--xml', xml_path,
                             '--xml-date', '2026-11-22', '--zim', zim, '--zim-date', '2026-11-17', '--fallback')
            xml_report = root / 'xml-audit.json'
            title_report = root / 'title-audit.json'
            self.run_command('tools/audit_xml.py', '--db', db, '--xml', xml_path, '--output', xml_report)
            self.run_command('tools/audit_titles.py', '--db', db, '--zim', zim, '--verify-index', '--output', title_report)
            self.assertTrue(json.loads(xml_report.read_text())['raw_sources_exact'])
            self.assertEqual(json.loads(title_report.read_text())['expected_rendered'], 1)
            self.run_command('-m', 'pokemon_knowledge', '--db', db, 'seal')
            result = json.loads(self.run_command('-m', 'pokemon_knowledge', '--db', db, 'read', 'Example'))
            self.assertTrue(result['available'])
            self.assertIn('合成的知识说明', result['results']['text'])
