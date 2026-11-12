# codebuddy-token-stats

![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-blue?logo=python&logoColor=white)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
![Dependencies: none](https://img.shields.io/badge/dependencies-none-green)

**One number for every model, across every CodeBuddy client.**

A single-file, zero-dependency Python CLI that aggregates token usage from the
CodeBuddy CLI, the VS Code extension and WorkBuddy, then breaks it down by model.

[简体中文](README.zh-CN.md)

---

## Why

CodeBuddy's built-in `#/stats` page only reads `~/.codebuddy/projects/` — in other
words, **only the CLI**. If you also use the VS Code CodeBuddy extension or
WorkBuddy (which is built on top of CodeBuddy), a large share of your usage is
invisible there.

`codebuddy-token-stats` reads all four local data sources and merges them into a
single report, so you can finally answer *"how many tokens did each model actually
consume?"*.

## Features

- **4 data sources on macOS, 2 on Linux** (WorkBuddy is macOS-only),
  auto-discovered per OS (missing ones are skipped)
- **Per-model** input / output / total / cache-hit tokens and request counts
- Group by **source**, **day** or **month**; filter with `--since` / `--until`
- **Deduplicated** by request ID, so the same request is never counted twice
- **Readable Chinese units** (`7.94 亿`, `6.01 百万`, `84.64 万`)
- **JSON output** with raw integers for scripting and dashboards
- **Local & read-only** — no network calls, no data leaves your machine

## Installation

Requires Python 3.8+. No third-party packages.

```bash
git clone https://github.com/wenzhixin/codebuddy-token-stats.git
cd codebuddy-token-stats
chmod +x codebuddy-token-stats.py
./codebuddy-token-stats.py
```

Or simply copy `codebuddy-token-stats.py` anywhere and run it with
`python3 codebuddy-token-stats.py`. Optionally link it into your `PATH`:

```bash
ln -s "$PWD/codebuddy-token-stats.py" ~/bin/codebuddy-token-stats.py
```

## Data sources

| Source | macOS path | Linux path | Format |
| --- | --- | --- | --- |
| `codebuddy-cli` | `~/.codebuddy/projects/**/*.jsonl` | same as macOS | per-turn `providerData.usage` + `providerData.model` |
| `workbuddy` | `~/.workbuddy/projects/**/*.jsonl` | — (not available) | same schema, plus a legacy `input_tokens` variant |
| `vscode-codebuddy` | `~/Library/Application Support/CodeBuddyExtension/Data` | `~/.config/CodeBuddyExtension/Data` | session `index.json` → `requests[].usage` |
| `vscode-workbuddy` | `~/Library/Application Support/WorkBuddyExtension/Data` | — (not available) | same as above |

Paths are selected automatically by OS (`sys.platform`). WorkBuddy is macOS-only
and is not registered as a source on Linux. Windows paths
(`%APPDATA%/CodeBuddy/...`) follow the same layout and can be added in the
`SOURCES` list at the top of the script.

Run `--list-sources` to see which ones were found on your machine:

```
$ ./codebuddy-token-stats.py --list-sources
codebuddy-cli        存在   原始记录    1.35 万  /Users/you/.codebuddy/projects
workbuddy            存在   原始记录    5,071  /Users/you/.workbuddy/projects
vscode-codebuddy     存在   原始记录      549  /Users/you/Library/.../CodeBuddyExtension/Data
vscode-workbuddy     存在   原始记录       19  /Users/you/Library/.../WorkBuddyExtension/Data

去重后记录数: 1.91 万
```

## Usage

```bash
./codebuddy-token-stats.py                                # totals by model, all sources
./codebuddy-token-stats.py --by-source                    # source × model
./codebuddy-token-stats.py --by-day --since 2026-11-01    # daily, newest day first
./codebuddy-token-stats.py --by-month                     # monthly
./codebuddy-token-stats.py --by-day --sort-by-usage       # back to global usage order
./codebuddy-token-stats.py --sources codebuddy-cli,workbuddy --json
./codebuddy-token-stats.py --list-sources
```

## Options

| Option | Description |
| --- | --- |
| `--sources <list>` | Comma-separated sources to include (default: all) |
| `--list-sources` | Show discovered sources and raw record counts |
| `--by-source` | Group by client source |
| `--by-day` | Group by date (default sort: newest day first) |
| `--by-month` | Group by month |
| `--since YYYY-MM-DD` | Include records on/after this date |
| `--until YYYY-MM-DD` | Include records on/before this date |
| `--sort-by-usage` | Sort globally by token usage instead of by date |
| `--json` | Emit raw integers as JSON (unscaled, English keys) |
| `--no-dedup` | Disable request-ID deduplication |

When `--by-day` / `--by-month` is used, rows are sorted by **date descending**,
and within each date by **usage descending**. `--sort-by-usage` restores the
original global usage-descending order. The table and `--json` share the same order.

## Sample output

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

> Console labels are in Chinese; `--json` keys are in English.
> Numbers are auto-scaled to Chinese units (亿 / 千万 / 百万 / 万) with a space
> between the number and the unit. `--json` always returns raw integers.

## How it works

- CLI / WorkBuddy logs store **per-turn** usage in `providerData.usage`, next to
  `providerData.model` and `requestModelName`.
- The VS Code extension stores **per-request** usage in each conversation's
  `index.json` (`requests[].usage`). The request itself has no model field, so the
  model is inferred from the first few message files (`extra.modelId`).
  The `statsSnapshot` inside message files is a **cumulative snapshot** and is
  deliberately **not** summed — adding those up would multiply-count everything.
- Records are deduplicated by `conversationRequestId` + `messageId`.
- The `traces/` directories also contain token counts, but they duplicate
  `projects/`, so they are excluded.
- VS Code's rotating `Logs/VSCode/*.log` files carry usage without a model name
  and expire daily, so they are not used either.

## Comparison with existing tools

| Tool | Coverage | Notes |
| --- | --- | --- |
| `codebuddy-stats` (npm) | CLI + VS Code IDE | Cannot merge WorkBuddy; IDE source must be switched manually; USD pricing only covers GPT/Claude/Gemini |
| `ccusage` | many agent CLIs | Parses Claude's `message.usage`; **reads 0 for CodeBuddy**, which uses `providerData.usage` |
| SuperBased | 50+ tools | Real-time hook capture, but requires a background daemon |
| `codebuddy-usage-analyzer` | exported JSON | Desktop GUI, needs a manual export |

## Notes & limitations

- **Input tokens look huge** because every turn resends the conversation history.
  That is the API billing semantics, not double counting; the cache-hit column
  shows how much of it came from prompt cache.
- The VS Code IDE source has **incomplete cache breakdown**, so its cache-hit
  numbers are lower than the CLI's.
- No USD cost is computed — pricing for these (mostly Chinese) models is not
  publicly stable.
- macOS and Linux paths are built in; Windows support is a small change in `SOURCES`.

## Privacy

Everything runs locally and read-only. The script never makes a network request
and never writes to the CodeBuddy data directories. Session contents are never
printed — only aggregated token counts.

## License

[MIT](LICENSE) © 2026 Zhixin Wen
