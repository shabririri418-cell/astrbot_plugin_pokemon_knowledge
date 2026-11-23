# 从官方归档构建

在 README 的 Python 构建环境中、仓库根目录执行以下命令。所有示例参数均为公开快照。不要用本流程绕过站方机器读取限制；本项目没有在线逐页爬虫。

## 1. 下载与解压

到 [官方 releases](https://github.com/52poke/mwarchiver/releases) 手工下载两个 ZIP，保存到 `assets/`（自行新建目录）：

| 类型 | 发布资产 | ZIP SHA256 |
|---|---|---|
| XML | [mwarchiver-2026.11.22.zip](https://github.com/52poke/mwarchiver/releases/download/2026.11.22/mwarchiver-2026.11.22.zip) | `bedf5096bd5ea587ca1006296551bcd0a4c2c0ba7956a2887998a416a8ca8624` |
| ZIM | [mwoffliner-2026.11.17-zim.zip](https://github.com/52poke/mwarchiver/releases/download/2026.11.17-zim/mwoffliner-2026.11.17-zim.zip) | `913410ca25e30f45b7f130f12f7216b584b8b6976f93e08109c3f1bfda0c23c3` |

SHA256 是本项目验证上述资产时记录的摘要，**不是额外宣称站方签名认证**。更换快照时应先核实发布页与新资产，不可把旧摘要套在新下载上。

站方在 [离线归档说明](https://wiki.52poke.com/wiki/神奇宝贝百科:离线归档) 公开的解压密码是 `52P0KEW1K1`。工具先校验 ZIP，再只把指定成员流式写入给定输出文件，不会按压缩包内路径展开整个目录。

```bash
python tools/extract_archive.py assets/mwarchiver-2026.11.22.zip --sha256 bedf5096bd5ea587ca1006296551bcd0a4c2c0ba7956a2887998a416a8ca8624 --suffix .xml.gz --output assets/52poke-2026.11.22.xml.gz
python tools/extract_archive.py assets/mwoffliner-2026.11.17-zim.zip --sha256 913410ca25e30f45b7f130f12f7216b584b8b6976f93e08109c3f1bfda0c23c3 --suffix .zim --output assets/wiki-52poke-privileged_zh_all_nopic_2026-11.zim
```

工具不覆盖已有输出文件。Windows 自带的 libarchive tar、其他系统的 `bsdtar` 可以快速解密；没有时退回 Python ZIP，处理大 ZIM 会较慢。意外中断留下 `.extracting` 时，确认没有解压进程后，手动删除该临时文件再重试。

本次解出文件的摘要：

- XML.gz：`45e6a3b96b289bcfbc2e0f79d5e0d6f1c71e8fe558ccd6115d19b4105f77fab6`
- ZIM：`19b947d7dbad3cd4be8c8daddc6ca22dffbf3e4b81af9874c74e5d1fe57c4b2a`

## 2. 离线构建

```bash
python -m pokemon_knowledge.builder --db data/pokemon.sqlite3 --xml assets/52poke-2026.11.22.xml.gz --xml-date 2026-11-22 --zim assets/wiki-52poke-privileged_zh_all_nopic_2026-11.zim --zim-date 2026-11-17 --fallback
```

命令结束后生成 `data/pokemon.coverage.json`。`--zim-date` 必须与 ZIM 的 Date 元数据一致。XML 与 ZIM 不同日期很正常，必须分别记录。完整构建会消耗 CPU、磁盘与临时空间；建议在独立电脑或低峰运行，不要直接在忙碌的机器人进程里构建。

同一命令再次运行会使用断点。快照或抽取版本变化会重新遍历，正文内容不变时保留片段索引。XML 完整导入后才删除退出新快照的页面；ZIM 完整遍历后清理旧正文，再为新 XML 独有页面做源代码降级。更新时使用真实的新快照日期，不要给不同资产复用旧日期。

默认查询范围是命名空间 `0`（主条目）和 `100`（附录），重定向用于别名解析。其他辅助命名空间只保存 XML 原文。`wikitext_fallback` 表示未渲染的维基源代码，不能把它当作完整展开的模板表格。

## 3. 独立审计与封库

以下审计脚本不改变数据库：

```bash
python tools/audit_xml.py --db data/pokemon.sqlite3 --xml assets/52poke-2026.11.22.xml.gz --output data/xml-audit.json
python tools/audit_titles.py --db data/pokemon.sqlite3 --zim assets/wiki-52poke-privileged_zh_all_nopic_2026-11.zim --verify-index --output data/title-audit.json
```

第一项逐页核对原文实际解压字节、元数据和重定向；第二项独立枚举 ZIM 标题，验证渲染与源代码降级的集合。查看覆盖报告中的 `missing_bodies`、`empty_articles`、`errors`，处理异常，不要手工删错误记录来通过验收。

确认构建进程结束后封库：

```bash
python -m pokemon_knowledge --db data/pokemon.sqlite3 seal
python -m pokemon_knowledge --db data/pokemon.sqlite3 status
```

封库会执行 SQLite 与 FTS 外部内容一致性检查、合并 WAL、切换 DELETE 日志模式，并生成 `data/pokemon.manifest.json`（数据库大小、SHA256、覆盖报告）。它需要写权限，只能对离线数据库运行。不要在构建器仍写入或数据库正被热替换时封库。

初次验证快照预期：297,762 个 XML 页面；48,186 篇知识正文；48,183 篇渲染正文和 3 篇源代码降级；缺失／空白／解析错误均为 0。源代码降级条目为“一口堅果（道具）”“每日新發現”“語言標籤（Pokémon GO）”。未来快照数量可以变化，不应为符合旧数字而丢弃新条目。

## 4. 安装后查询

只运行查询不需要构建依赖；可以把封库后的单文件和 manifest 复制到运行机器。不要复制未合并 WAL 的单独 `.sqlite3` 文件。传输后比对文件 SHA256 和大小，再配置 AstrBot；更新和回退见 [运行说明](OPERATIONS.md)。
