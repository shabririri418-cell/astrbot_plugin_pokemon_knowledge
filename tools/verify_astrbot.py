"""Run manually INSIDE an AstrBot Python environment; never sends any chat messages."""
import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pokemon_knowledge.store import KnowledgeStore
from astrbot.core.provider.func_tool_manager import ToolSet
from astrbot.core.provider.register import llm_tools


async def main():
    package = 'offline_pokemon_plugin_smoke'
    spec = importlib.util.spec_from_file_location(package, ROOT / '__init__.py', submodule_search_locations=[str(ROOT)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[package] = module
    spec.loader.exec_module(module)
    module = __import__(package + '.main', fromlist=['PokemonKnowledge'])
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory)
        writer = KnowledgeStore(path / 'pokemon.sqlite3')
        writer.put_xml('测试条目', 0, 1, 1, '', '', '2026-11-22')
        writer.put_rendered('测试条目', [dict(section='测试', text='合成的验证事实。')], '2026-11-17', 'fixture')
        xml = dict(complete=True)
        zim = dict(complete=True, knowledge_namespaces=[0, 100])
        writer.set_metadata('xml_import', xml)
        writer.set_metadata('zim_import', zim)
        writer.set_metadata('coverage', dict(xml=xml, zim=zim, main_articles=1, missing_bodies=0))
        writer.close()
        apis = []
        context = types.SimpleNamespace(register_web_api=lambda *args: apis.append(args),
                                        get_llm_tool_manager=lambda: llm_tools)
        config = dict(database_path=str(path / 'pokemon.sqlite3'), allowed_origins=['synthetic:allowed'])
        plugin = module.PokemonKnowledge(context, config)
        await plugin.initialize()
        event = types.SimpleNamespace(unified_msg_origin='synthetic:allowed', get_extra=lambda key: False)
        value = json.loads(await plugin.search_pokemon_knowledge(event, '测试条目'))
        assert value['available'] and '合成' in value['results'][0]['text']
        request = types.SimpleNamespace(func_tool=ToolSet(), system_prompt='原有人格')
        await plugin.expose_knowledge(event, request)
        assert set(request.func_tool.names()) == {'search_pokemon_knowledge', 'read_pokemon_knowledge'}
        assert request.system_prompt.startswith('原有人格')
        assert apis[0][0] == '/pokemon_knowledge/health'
        event.unified_msg_origin = 'synthetic:denied'
        assert '不能' in await plugin.search_pokemon_knowledge(event, '测试条目')
        event.unified_msg_origin = 'synthetic:allowed'
        event.get_extra = lambda key: True
        assert '不能' in await plugin.read_pokemon_knowledge(event, '测试条目')
        print('ASTRBOT_PUBLIC_ADAPTER_INITIALIZE_TOOLS_READONLY_SCOPE_PROACTIVE_PASS')


if __name__ == '__main__':
    asyncio.run(main())
