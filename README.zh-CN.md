# codebuddy-token-stats

![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-blue?logo=python&logoColor=white)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
![零依赖](https://img.shields.io/badge/dependencies-none-green)

**一个脚本，把 CodeBuddy 全系列各客户端的 token 用量按模型统一算出来。**

单文件、零依赖的 Python 命令行工具，自动汇总 CodeBuddy CLI、VS Code 插件和
WorkBuddy 的本地用量数据，按模型累计输入 / 输出 / 合计 / 缓存命中 token 与请求数。

[English](README.md)

---

## 为什么需要它

CodeBuddy 自带的 `#/stats` 统计页只读 `~/.codebuddy/projects/`，也就是说
**只统计 CLI**。如果你同时还在用 VS Code 的 CodeBuddy 插件，或者 WorkBuddy
（底层同样是 CodeBuddy），这些用量在 `#/stats` 里完全看不到。

这个工具把四个本地数据源一起读出来合并，回答一个很实际的问题：
**「到底哪个模型用了多少 token？」**

## 特性

- **4 个数据源**自动发现，缺失的自动跳过
- **按模型**汇总输入 / 输出 / 合计 / 缓存命中 token 及请求数
- 支持按**来源**、**日期**、**月份**分组，配合 `--since` / `--until` 过滤
- 按请求 ID **去重**，同一请求不会被重复计入
- **中文可读单位**（`7.94 亿`、`6.01 百万`、`84.64 万`），数字与单位之间留空格
- `--json` 输出原始整数，方便接脚本或面板
- **纯本地只读**：不发网络请求，数据不出本机

## 安装

需要 Python 3.8+，无第三方依赖。

```bash
git clone https://github.com/wenzhixin/codebuddy-token-stats.git
cd codebuddy-token-stats
chmod +x codebuddy-token-stats.py
./codebuddy-token-stats.py
```

也可以只把 `codebuddy-token-stats.py` 拷到任意目录用 `python3` 跑。想继续用
`~/bin` 里的命令，可以建个软链：

```bash
ln -s "$PWD/codebuddy-token-stats.py" ~/bin/codebuddy-token-stats.py
```

## 数据源

| 来源 | 默认路径（macOS） | 数据格式 |
| --- | --- | --- |
| `codebuddy-cli` | `~/.codebuddy/projects/**/*.jsonl` | 逐轮 `providerData.usage` + `providerData.model` |
| `workbuddy` | `~/.workbuddy/projects/**/*.jsonl` | 同上，另兼容少量旧版 `input_tokens` 字段 |
| `vscode-codebuddy` | `~/Library/Application Support/CodeBuddyExtension/Data` | 会话 `index.json` 里的 `requests[].usage` |
| `vscode-workbuddy` | `~/Library/Application Support/WorkBuddyExtension/Data` | 同上 |

目前只配置了 macOS 路径。Windows（`%APPDATA%/CodeBuddy/...`）和 Linux
（`$XDG_CONFIG_HOME/codebuddy/...`）目录结构一致，改脚本顶部的 `SOURCES`
即可支持。

用 `--list-sources` 查看本机发现了哪些数据源：

```
$ ./codebuddy-token-stats.py --list-sources
codebuddy-cli        存在   原始记录    1.35 万  /Users/you/.codebuddy/projects
workbuddy            存在   原始记录    5,071  /Users/you/.workbuddy/projects
vscode-codebuddy     存在   原始记录      549  /Users/you/Library/.../CodeBuddyExtension/Data
vscode-workbuddy     存在   原始记录       19  /Users/you/Library/.../WorkBuddyExtension/Data

去重后记录数: 1.91 万
```

## 用法

```bash
./codebuddy-token-stats.py                                # 按模型汇总全部来源
./codebuddy-token-stats.py --by-source                    # 按来源 × 模型
./codebuddy-token-stats.py --by-day --since 2026-11-01    # 按天，最新日期在最前
./codebuddy-token-stats.py --by-month                     # 按月
./codebuddy-token-stats.py --by-day --sort-by-usage       # 切回全局按用量倒序
./codebuddy-token-stats.py --sources codebuddy-cli,workbuddy --json
./codebuddy-token-stats.py --list-sources
```

## 参数

| 参数 | 说明 |
| --- | --- |
| `--sources <list>` | 逗号分隔指定数据源，默认全部 |
| `--list-sources` | 列出发现的数据源与原始记录数 |
| `--by-source` | 按客户端来源分组 |
| `--by-day` | 按日期分组（默认日期倒序） |
| `--by-month` | 按月份分组 |
| `--since YYYY-MM-DD` | 只统计该日期及之后 |
| `--until YYYY-MM-DD` | 只统计该日期及之前 |
| `--sort-by-usage` | 改为全局按用量倒序，不按日期排 |
| `--json` | 输出原始整数 JSON（不缩放、英文键） |
| `--no-dedup` | 关闭按请求 ID 去重 |

使用 `--by-day` / `--by-month` 时，**默认按日期倒序**，同一天内再按用量倒序；
`--sort-by-usage` 可切回原来的全局用量倒序。表格和 `--json` 共用同一排序。

## 输出示例

```
CodeBuddy 全系列 Token 统计  (数据源: codebuddy-cli, vscode-codebuddy, vscode-workbuddy, workbuddy)
去重后 1.91 万 条请求

按 model 汇总（按用量倒序）
model                               请求        输入        输出        合计    缓存命中
----------------------------------------------------------------------------------------
glm-5.3                       9,841        7.94 亿     6.01 百万   8.00 亿     7.15 亿
hy4-free                      3,114        3.99 亿     4.89 百万   4.04 亿     3.77 亿
deepseek-v4.1-flash           1,809        2.10 亿     1.59 百万   2.11 亿     2.05 亿
...
----------------------------------------------------------------------------------------
合计                           1.91 万    20.11 亿     1.72 千万  20.29 亿    18.65 亿

各来源合计：
  codebuddy-cli                 11.51 亿 tokens  (1.35 万 请求)
  vscode-codebuddy               4.41 亿 tokens  (549 请求)
  workbuddy                      4.30 亿 tokens  (5,056 请求)
  vscode-workbuddy              7.15 百万 tokens  (19 请求)
```

> 数字按数量级自动换算成「亿 / 千万 / 百万 / 万」，数字与单位之间留一个空格；
> `--json` 始终返回原始整数。

## 实现要点

- CLI / WorkBuddy 的会话日志里，`providerData.usage` 是**逐轮**用量，旁边带
  `providerData.model` 和 `requestModelName`。
- VS Code 插件把**逐请求**用量记在会话 `index.json` 的 `requests[].usage` 里。
  请求本身不带模型名，因此从该轮前几条 message 文件的 `extra.modelId` 推断。
  message 文件里的 `statsSnapshot` 是**会话累计快照**，脚本刻意不累加它——
  否则会成倍重复计数。
- 用 `conversationRequestId` + `messageId` 去重。
- `traces/` 目录里也有 token 数据，但与 `projects/` 重复，故不纳入。
- VS Code 的 `Logs/VSCode/*.log` 按天轮转、且不带模型名，历史补不回来，也不用。

## 和现成工具的对比

| 工具 | 覆盖范围 | 说明 |
| --- | --- | --- |
| `codebuddy-stats`（npm） | CLI + VS Code IDE | 不覆盖 WorkBuddy；IDE 源需手动切换；成本定价只含 GPT/Claude/Gemini |
| `ccusage` | 多种 agent CLI | 解析 Claude 的 `message.usage`，**读 CodeBuddy 全是 0**（CodeBuddy 用 `providerData.usage`） |
| SuperBased | 50+ 工具 | 通过 hook 实时捕获，但要常驻后台进程 |
| `codebuddy-usage-analyzer` | 导出的 JSON | 桌面 GUI，需手动导出 |

## 口径与限制

- **输入 token 看起来特别大**，是因为每轮都会把历史上下文重新喂给模型，
  这是 API 计费口径，并非重复统计；「缓存命中」列可以看出其中多少走了 prompt cache。
- VS Code IDE 源的缓存明细不完整，缓存命中数会比 CLI 源低。
- 不计算美元成本——这些（多为国产）模型没有稳定公开的价格表。
- 目前只配置了 macOS 路径，Linux / Windows 只需改 `SOURCES`。

## 隐私

全程本地只读，不发任何网络请求，也不会写入 CodeBuddy 的数据目录。
只输出聚合后的 token 数字，不会打印会话内容。

## License

[MIT](LICENSE) © 2026 Zhixin Wen
