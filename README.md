# 大肥鱼宝可梦知识库

**Pokémon Offline Knowledge** — 从 52Poké 发布的 XML／ZIM 离线归档构建可检索的宝可梦百科，提供 AstrBot 工具和独立 Python 查询接口。

它为回答提供相关知识片段，不把整本百科塞进模型上下文，也不训练或微调模型。聊天时自然回答，默认不主动附来源、不播报检索过程；内部保留条目链接、来源、许可、快照日期，明确询问出处时可以提供。

## 能做什么

- 名称、简繁、日英重定向别名和中文全文检索；按章节、游标继续阅读。
- 保留形态、地区、世代、计算方式，以及表格的合并表头和行列关系。
- 同时索引主条目与“附录”，区分正式资料、攻略、社区术语和非官方译名。
- 流式 XML 导入、ZIM 断点恢复、快照差量更新；内容相同时复用索引。
- 只读 SQLite 查询，不依赖向量数据库、嵌入模型或在线百科服务。
- 未完成或覆盖报告过期的库不会就绪；未渲染的源代码有明确质量标记。

**仓库只包含代码、文档和生成式测试。** 百科正文、归档、数据库、聊天记录及运行账号配置均不随仓库分发。软件代码为 MIT；52Poké 内容适用其独立的 CC BY-NC-SA 3.0 等许可，见 [数据来源与许可](THIRD_PARTY_NOTICES.md)。本项目与站方及宝可梦版权方无官方关联。

## 快速开始：独立查询

需要 Python 3.11+，推荐 3.12，SQLite 必须支持 FTS5。先克隆仓库并建立构建环境：

```bash
git clone https://github.com/shabririri418-cell/astrbot_plugin_pokemon_knowledge.git
cd astrbot_plugin_pokemon_knowledge
python -m venv .venv
```

激活环境：Windows PowerShell 使用 `.venv\Scripts\Activate.ps1`；Linux／macOS 使用 `source .venv/bin/activate`。然后执行：

```bash
python -m pip install -e ".[build]"
```

从 [52Poké 官方归档发布页](https://github.com/52poke/mwarchiver/releases)下载 XML 和不含图片的 ZIM 包，按 [构建指南](docs/BUILD.md) 校验、解压并生成 `data/pokemon.sqlite3`。仓库没有预置数据库，安装代码后不能直接查出完整百科。

构建、审计及封库完成后：

```bash
python -m pokemon_knowledge --db data/pokemon.sqlite3 status
python -m pokemon_knowledge --db data/pokemon.sqlite3 search "皮卡丘 速度 种族值"
python -m pokemon_knowledge --db data/pokemon.sqlite3 search "雷丘 阿罗拉 属性"
python -m pokemon_knowledge --db data/pokemon.sqlite3 search "速度线"
python -m pokemon_knowledge --db data/pokemon.sqlite3 read "皮卡丘" --section "种族值"
```

CLI 返回 JSON，其中的来源字段供应用内部使用。聊天适配器默认不会在回答后追加引用。

## 接入 AstrBot

1. 在 AstrBot 插件管理中通过仓库 URL 安装本项目；这里不需要安装构建用的 lxml、libzim 等包。
2. 在电脑或其他独立环境构建并封库，将单文件数据库复制到 AstrBot 的持久化目录。
3. 在插件设置中将 `database_path` 设为数据库的绝对路径。Docker 中必须填容器内能访问的路径，而不是宿主机路径；留空时使用本插件数据目录的 `pokemon.sqlite3`。
4. 可用 `allowed_origins` 限制允许的会话，空列表表示允许所有正常触发的会话。在工具管理中启用下面两个工具。

| 工具 | 用途 |
|---|---|
| `search_pokemon_knowledge(query)` | 查名称、事实及相关片段 |
| `read_pokemon_knowledge(title, section, offset)` | 搜索不足时按章节继续回读 |

健康接口为 `/api/v1/plugins/extensions/pokemon_knowledge/health`，需管理员登录。没有数据库或导入未完成时 `ready=false`。配置项及故障排查见 [运行与更新](docs/OPERATIONS.md)。

公开适配器不依赖大肥鱼私有的情绪、记忆或群管理插件。它不负责唤起消息、定时发言或调整人格；只在原本已触发的模型请求中补充工具。其他机器人的会话权限、情绪门控等应由其宿主实现。已在真实 AstrBot 环境隔离验证初始化、工具注入、只读查询、白名单和自主消息拒绝，未发送聊天消息。

## 查询示例

| 问题 | 已核对的结果要点 |
|---|---|
| 皮卡丘和搭档皮卡丘的速度种族值分别是多少？ | 90／120，区分形态 |
| 阿罗拉雷丘是什么属性？ | 电／超能力 |
| 十万伏特的威力一直都是90吗？ | 第六世代从95变为90 |
| 速度线和速度种族值是一回事吗？ | 区分玩家配速参考和种族基础值 |

这些是检索后的事实要点；具体用词由模型和原有角色设定决定。

## 覆盖与性能

基于 2026-11-22 XML 和 2026-11-17 ZIM 的一次完整构建，实际索引 **48,186 篇知识正文**：主条目 48,074 篇、附录 112 篇，约 150 万片段。全部 297,762 页 XML 原文及元数据已与源文件核对；3 篇仅有未渲染源代码，未作为已渲染正文冒充。

部署样本中 13 个名称／形态／附录查询最长 0.055 秒，全文片段查询约 0.15 秒；5 个模型查证回答约 1.2～2.4 秒。库约 3.25 GB。这是特定快照与环境的样本结果，不是任意复杂问题或 QQ 全链路耗时保证。完整构建需要额外的归档、索引和临时空间，建议预留至少 15 GB。

这是离线文字知识库：不识别原图片／音频内容，不保证覆盖快照之后的修改，不保证复杂表格或任意召回问题完全无误。正文与 XML 的日期分别返回，不能把 XML 修订号当作 ZIM 正文的更新证明。

## 开发与验证

```bash
python -m pip install -e ".[build]"
python -m unittest discover -s tests -v
```

测试会临时生成小型 XML／真实 ZIM 容器，不联网、不下载完整百科。包含表格与形态语义、断点恢复、跨快照删除、增量范围、别名、全文检索、只读边界，以及“解压→构建→独立审计→封库→查询”流程。GitHub Actions 在 Linux 和 Windows 上运行。

## English

An offline Pokémon knowledge retrieval engine with an AstrBot adapter. Build locally from publisher-provided XML/ZIM snapshots; query aliases, CJK full text and article sections through read-only SQLite. Tables retain form/generation context. The runtime needs no vector model or network access. Answers are natural by default, with provenance retained internally.

This repository distributes **software only**, under MIT. Download encyclopedia archives from the publisher and comply with their separate content license; do not treat encyclopedia content as MIT. See [build instructions](docs/BUILD.md), [operations](docs/OPERATIONS.md) and [content notices](THIRD_PARTY_NOTICES.md).
