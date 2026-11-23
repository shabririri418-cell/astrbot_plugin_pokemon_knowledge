"""Test adapter methods without installing AstrBot in the builder environment."""
import ast
import asyncio
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

from pokemon_knowledge.policy import permitted


def methods():
    tree = ast.parse((Path(__file__).resolve().parents[1] / 'main.py').read_text(encoding='utf8'))
    namespace = dict(asyncio=asyncio, AstrMessageEvent=object, permitted=permitted)
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef))
    for node in cls.body:
        if isinstance(node, ast.AsyncFunctionDef):
            node.decorator_list = []
            exec(compile(ast.Module(body=[node], type_ignores=[]), 'adapter', 'exec'), namespace)
    return namespace


class Adapter(unittest.IsolatedAsyncioTestCase):
    async def test_disabled_scope_does_not_query_database(self):
        calls = AsyncMock()
        adapter = types.SimpleNamespace(permitted=AsyncMock(return_value=False), knowledge=types.SimpleNamespace(query=calls))
        ns = methods()
        await ns['search_pokemon_knowledge'](adapter, object(), '示例')
        await ns['read_pokemon_knowledge'](adapter, object(), '示例')
        calls.assert_not_called()

    async def test_existing_tools_and_personality_are_preserved(self):
        class ToolSet:
            def __init__(self): self.tools = ['existing']
            def add_tool(self, tool): self.tools.append(tool)
        module = types.ModuleType('astrbot.core.provider.func_tool_manager')
        module.ToolSet = ToolSet
        manager = types.SimpleNamespace(get_func=lambda name: types.SimpleNamespace(name=name, active=True))
        adapter = types.SimpleNamespace(permitted=AsyncMock(return_value=True), knowledge=types.SimpleNamespace(ready=lambda: True),
                                        context=types.SimpleNamespace(get_llm_tool_manager=lambda: manager))
        request = types.SimpleNamespace(func_tool=ToolSet(), system_prompt='已有角色设定')
        with patch.dict(sys.modules, {module.__name__: module}):
            await methods()['expose_knowledge'](adapter, object(), request)
        self.assertEqual(request.func_tool.tools[0], 'existing')
        self.assertEqual(len(request.func_tool.tools), 3)
        self.assertTrue(request.system_prompt.startswith('已有角色设定'))
        self.assertIn('默认不提百科', request.system_prompt)

    async def test_no_tools_are_injected_before_the_index_is_ready(self):
        adapter = types.SimpleNamespace(permitted=AsyncMock(return_value=True), knowledge=types.SimpleNamespace(ready=lambda: False))
        request = types.SimpleNamespace(func_tool=None, system_prompt='original')
        await methods()['expose_knowledge'](adapter, object(), request)
        self.assertIsNone(request.func_tool)
        self.assertEqual(request.system_prompt, 'original')
