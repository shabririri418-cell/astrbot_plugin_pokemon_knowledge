# 运行、更新与接口

## 运行边界

核心查询不联网、不读聊天记忆，也不把百科整体注入模型。命名查询先解析条目再读该页片段；无匹配名称时用中文二元词 FTS，先完整词组合，再宽泛回退。搜索结果最多约 6,500 字符，章节回读最多 5,000 字符，并返回后续游标。

每条 SQLite 查询连接约 2 MiB 页缓存，两个工具查询并发槽，SQL 执行约 1.2 秒截止、进入槽位后的工具等待约 3 秒。它们是局部资源边界，不等于模型调用和队列等待的总时限。返回 unavailable 时不能据此声称百科没有该事实。

AstrBot 的设置只控制此插件：`enabled` 开关、`database_path` 管理员指定路径、`allowed_origins` 会话列表。数据库路径不作为模型工具参数。插件本身不新增定时任务，不发送主动消息，不清除旧聊天历史，不代替宿主的权限与情绪策略。

`search_pokemon_knowledge` 与 `read_pokemon_knowledge` 的工具结果包含来源和许可证，但回答提示默认不主动附出处。用户明确索要时可使用结果中的原文链接。部署时仍应在产品说明中保留适当内容署名，见 [许可边界](../THIRD_PARTY_NOTICES.md)。

## Python API

```python
import asyncio
import json
from pokemon_knowledge.service import KnowledgeService

async def main():
    knowledge = KnowledgeService("data/pokemon.sqlite3")
    result = json.loads(await knowledge.query("search", query="雷丘 阿罗拉 属性", limit=5, max_chars=6500))
    if result["available"]:
        for item in result["results"]:
            print(item["title"], item["section"], item["text"])

asyncio.run(main())
```

`read` 参数为 `title`、`section`、`offset`、`max_chars`；用搜索返回的规范标题，并按 `next_offset` 分页。`quality` 区分已渲染正文和维基源代码降级，`article_kind=appendix` 标识附录。`body_snapshot` 与 `xml_snapshot` 可能不同，`revision_applies_to=xml_source_only` 提醒修订号只对应 XML 源代码。

## 更新与回退

1. 下载并验证新归档，在独立的数据库副本上运行构建，不修改线上只读库。
2. 执行原文、标题集合审计与封库；核对实际缺口及降级情况。
3. 备份当前数据库、manifest、插件版本和设置。先把新文件传入临时目录，核对 SHA256。
4. 在同一文件系统内用原子重命名替换库，或修改设置指向新文件；如有旧连接，待查询结束后仅重载本插件。不要同时升级数据库和未验证的其他插件。
5. 确认管理员健康接口 `ready=true`，实际查几个形态、世代和别名问题。验证失败时恢复匹配的旧数据与旧插件版本；没有旧库时禁用本插件，原有聊天继续使用既有功能。

首次使用的新插件应通过正常安装接口加载；只在它已注册后调用精确插件重载，避免框架对未知名称退化成全插件重载。完整库校验有持续磁盘读取，可在低峰、低 IO 优先级运行。不要为了更新知识库重启整个 QQ 客户端。

## 故障排查

| 现象 | 检查 |
|---|---|
| `ready=false` | 路径、容器挂载、读权限，XML/ZIM complete 与 coverage 是否匹配，范围是否含 0 和 100 |
| 无法导入 libzim／lxml | 构建端安装 `.[build]`；运行端纯查询不需要这些包 |
| `no such module: fts5` | 使用带 FTS5 的 Python／SQLite 构建 |
| 解密很慢 | 安装 libarchive 的 bsdtar；Python ZIP 解密是较慢的兼容路径 |
| 世代或形态混淆 | 查询中同时写条目、形态、游戏与字段，必要时回读章节 |
| 某篇只有维基模板 | 查看 `wikitext_fallback` 和两份快照日期，可能是新 XML 尚无对应 ZIM |
| 查不到刚发生的消息 | 离线库只到快照日期，使用既有联网工具查新消息 |

## 验证 AstrBot 适配器

普通 CI 不安装完整 AstrBot。也可以在已经装好 AstrBot 的隔离 Python 进程中，从仓库执行：

```bash
python tools/verify_astrbot.py
```

该脚本使用临时合成库和虚拟事件，验证真实框架导入、初始化、工具注入、白名单和自主消息拒绝，不调用管理安装接口，不发聊天消息。不要把隔离进程注册工具的日志当作主进程插件已经上线的证据。
