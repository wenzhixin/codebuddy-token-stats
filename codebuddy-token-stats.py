#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""统一统计 CodeBuddy 全系列 token 用量，按模型累计。

数据源（按操作系统自动发现，缺失的自动跳过）：
  codebuddy-cli     ~/.codebuddy/projects/**/*.jsonl
  vscode-codebuddy  mac: ~/Library/Application Support/CodeBuddyExtension/Data
                    linux: ~/.config/CodeBuddyExtension/Data
  workbuddy         ~/.workbuddy/projects/**/*.jsonl          (仅 mac)
  vscode-workbuddy  ~/Library/Application Support/WorkBuddyExtension/Data  (仅 mac)

用法：
  codebuddy-token-stats.py                          # 按模型汇总全部来源
  codebuddy-token-stats.py --by-source              # 按来源分组
  codebuddy-token-stats.py --by-day --since 2026-11-01
  codebuddy-token-stats.py --by-day --sort-by-usage  # 改回按用量倒序
  codebuddy-token-stats.py --sources codebuddy-cli,workbuddy --json
  codebuddy-token-stats.py --list-sources
"""
import argparse
import collections
import datetime as dt
import glob
import json
import os
import sys
import unicodedata

HOME = os.path.expanduser("~")
IS_MAC = sys.platform == "darwin"

SOURCES = [
    ("codebuddy-cli",
     os.path.join(HOME, ".codebuddy", "projects"), "jsonl"),
    ("vscode-codebuddy",
     os.path.join(HOME, ".config", "CodeBuddyExtension", "Data")
     if sys.platform.startswith("linux")
     else os.path.join(HOME, "Library", "Application Support", "CodeBuddyExtension", "Data"),
     "ide"),
]

if IS_MAC:
    SOURCES += [
        ("workbuddy",
         os.path.join(HOME, ".workbuddy", "projects"), "jsonl"),
        ("vscode-workbuddy",
         os.path.join(HOME, "Library", "Application Support", "WorkBuddyExtension", "Data"), "ide"),
    ]


ALIASES = {"hy4free": "hy4-free"}


def norm_model(m):
    """归一化模型名：去自定义前缀，合并不同客户端的命名差异。"""
    if not m:
        return "unknown"
    m = str(m)
    if m.startswith("custom-local:"):
        m = m.split(":", 1)[1]
    return ALIASES.get(m, m)


def to_date(v):
    """兼容毫秒 epoch、秒 epoch 与 ISO 字符串。"""
    if isinstance(v, (int, float)):
        return dt.datetime.fromtimestamp(v / 1000 if v > 1e11 else v).date().isoformat()
    if isinstance(v, str):
        try:
            return dt.datetime.fromisoformat(v.replace("Z", "+00:00")).date().isoformat()
        except ValueError:
            return None
    return None


def num(v):
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def make_rec(source, model, date, inp, out, total, cache, credit=0):
    return {"source": source, "model": norm_model(model), "date": date,
            "requests": 1, "input": inp, "output": out, "total": total,
            "cache": cache, "credit": credit}


def iter_jsonl(root, source):
    """CLI / WorkBuddy 会话日志：providerData.usage 为逐轮用量。"""
    for path in glob.iglob(os.path.join(root, "**", "*.jsonl"), recursive=True):
        with open(path, encoding="utf-8", errors="ignore") as f:
            for lineno, line in enumerate(f, 1):
                if '"usage"' not in line:
                    continue
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                pd = d.get("providerData") or {}
                u = pd.get("usage")
                if not isinstance(u, dict):
                    continue
                inp = num(u.get("inputTokens", u.get("input_tokens")))
                out = num(u.get("outputTokens", u.get("output_tokens")))
                total = num(u.get("totalTokens", u.get("total_tokens"))) or (inp + out)
                cache = sum(num(x.get("cached_tokens"))
                            for x in (u.get("inputTokensDetails") or [])
                            if isinstance(x, dict))
                raw = pd.get("rawUsage") or {}
                credit = num(raw.get("credit"))
                key = (pd.get("conversationRequestId"), pd.get("messageId")) or (path, lineno)
                yield (source, key), make_rec(
                    source, pd.get("model") or pd.get("requestModelId"),
                    to_date(d.get("timestamp")), inp, out, total, cache, credit)


def ide_model(conv_dir, req, cache):
    """IDE 请求不带模型名，从该轮前几条 message 的 extra.modelId 推断。"""
    for mid in (req.get("messages") or [])[:3]:
        if mid in cache:
            if cache[mid]:
                return cache[mid]
            continue
        p = os.path.join(conv_dir, "messages", str(mid) + ".json")
        model = None
        try:
            with open(p, encoding="utf-8", errors="ignore") as f:
                extra = json.load(f).get("extra")
            if isinstance(extra, str):
                extra = json.loads(extra)
            if isinstance(extra, dict):
                model = extra.get("modelId")
        except (OSError, ValueError):
            pass
        cache[mid] = model
        if model:
            return model
    return None


def iter_ide(root, source):
    """VSCode 插件：会话 index.json 的 requests[].usage 为逐轮用量。"""
    model_cache = collections.defaultdict(dict)
    for path in glob.iglob(os.path.join(root, "**", "history", "**", "index.json"),
                           recursive=True):
        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                d = json.load(f)
        except (OSError, ValueError):
            continue
        reqs = d.get("requests") if isinstance(d, dict) else None
        if not isinstance(reqs, list):
            continue
        conv_dir = os.path.dirname(path)
        cache = model_cache[conv_dir]
        for req in reqs:
            if not isinstance(req, dict):
                continue
            u = req.get("usage")
            if not isinstance(u, dict):
                continue
            inp = num(u.get("inputTokens"))
            out = num(u.get("outputTokens"))
            total = num(u.get("totalTokens")) or (inp + out)
            date = to_date(req.get("startedAt")) or to_date(d.get("lastMessageAt")) \
                or to_date(d.get("createdAt"))
            key = req.get("id") or (path, id(req))
            yield (source, key), make_rec(
                source, ide_model(conv_dir, req, cache), date,
                inp, out, total, num(u.get("cacheTokens")), num(u.get("credit")))


def collect(selected, dedup=True):
    records, file_counts, seen = [], {}, set()
    for name, root, kind in SOURCES:
        if name not in selected or not os.path.isdir(root):
            continue
        gen = iter_jsonl(root, name) if kind == "jsonl" else iter_ide(root, name)
        n = 0
        for key, rec in gen:
            n += 1
            if dedup and key in seen:
                continue
            seen.add(key)
            records.append(rec)
        file_counts[name] = n
    return records, file_counts


def aggregate(records, keys, since=None, until=None):
    out = collections.defaultdict(lambda: collections.defaultdict(int))
    for r in records:
        date = r["date"] or "unknown"
        if since or until:
            if date == "unknown" or (since and date < since) or (until and date > until):
                continue
        k = tuple(r[x] for x in keys)
        for f in ("requests", "input", "output", "total", "cache", "credit"):
            out[k][f] += r[f]
    return out


UNITS = (
    (100_000_000, "亿"),
    (10_000_000, "千万"),
    (1_000_000, "百万"),
    (10_000, "万"),
)

NUM_W = 6                      # 数值段：纯 ASCII，右对齐
UNIT_W = 4                     # 单位段：统一按两个汉字宽补齐
CELL_W = NUM_W + 1 + UNIT_W    # 单元格固定宽度


def disp_width(s):
    """终端显示宽度：中文/全角字符占两列。"""
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in s)


def rjust(s, width):
    return " " * max(0, width - disp_width(s)) + s


def ljust(s, width):
    return s + " " * max(0, width - disp_width(s))


def clip(s, width):
    """名字超长时截断加省略号，避免撑破列宽导致数字列错位。"""
    if disp_width(s) <= width:
        return s
    out, w = "", 0
    for c in s:
        cw = 2 if unicodedata.east_asian_width(c) in ("W", "F") else 1
        if w + cw > width - 1:
            break
        out += c
        w += cw
    return out + "…"


def split_num(n):
    num, unit = format(n, ","), ""
    for base, name in UNITS:
        if abs(n) >= base:
            num, unit = f"{n / base:.2f}", name
            break
    return num, unit


def fmt(n):
    """紧凑显示：数字与单位之间留一个空格；不足一万保留千分位原数。"""
    num, unit = split_num(n)
    return f"{num} {unit}".rstrip()


def cell(n):
    """表格单元格：数值段右对齐 + 空格 + 单位段左对齐，整格固定 CELL_W 列。

    数值段是纯 ASCII 且单独对齐，所以数字的位置不随终端中文宽度变化；
    含中文的单位段排在其右侧，不会再反过来挤动数字列。
    """
    num, unit = split_num(n)
    return rjust(num, NUM_W) + " " + ljust(unit, UNIT_W)


def sort_rows(agg, date_first):
    """按用量倒序；date_first 时改为日期倒序，同日内仍保持用量倒序。"""
    items = sorted(agg.items(), key=lambda kv: -kv[1]["total"])
    if date_first:
        # 稳定排序：先按用量、再按日期倒序；unknown 日期挪到最后
        items.sort(key=lambda kv: "" if kv[0][0] == "unknown" else kv[0][0],
                   reverse=True)
    return items


def print_table(agg, keys, label, date_first=False):
    fields = ("requests", "input", "output", "total", "cache")
    headers = ("请求", "输入", "输出", "合计", "缓存命中")

    rows = []
    for k, v in sort_rows(agg, date_first):
        name = " / ".join(str(x) for x in k) if isinstance(k, tuple) else str(k)
        rows.append((name, tuple(cell(v[f]) for f in fields)))
    tot = {f: sum(v[f] for v in agg.values()) for f in fields}
    rows.append(("合计", tuple(cell(tot[f]) for f in fields)))

    head_name = " / ".join(keys)
    name_w = min(max(28, max(disp_width(n) for n in
                             [head_name] + [r[0] for r in rows]) + 1), 40)
    line = name_w + 1 + CELL_W * len(headers) + (len(headers) - 1)

    def row(cells, name, header=False):
        parts = [rjust(h, CELL_W) for h in cells] if header else cells
        return ljust(clip(name, name_w), name_w) + " " + " ".join(parts)

    print("\n" + label)
    print(row(headers, head_name, header=True))
    print("-" * line)
    for name, cells in rows[:-1]:
        print(row(cells, name))
    print("-" * line)
    print(row(rows[-1][1], rows[-1][0]))


def main():
    ap = argparse.ArgumentParser(description="统一统计 CodeBuddy 全系列 token 用量")
    ap.add_argument("--sources", default=",".join(s[0] for s in SOURCES),
                    help="逗号分隔的数据源，默认全部")
    ap.add_argument("--list-sources", action="store_true", help="列出数据源与原始记录数")
    ap.add_argument("--by-source", action="store_true", help="按来源分组")
    ap.add_argument("--by-day", action="store_true", help="按日期分组")
    ap.add_argument("--by-month", action="store_true", help="按月份分组")
    ap.add_argument("--since", help="起始日期 YYYY-MM-DD")
    ap.add_argument("--until", help="结束日期 YYYY-MM-DD")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    ap.add_argument("--sort-by-usage", action="store_true",
                    help="按全局使用量倒序排（默认：按日期倒序，同日内按用量倒序）")
    ap.add_argument("--no-dedup", action="store_true", help="不去重（默认按请求 ID 去重）")
    args = ap.parse_args()

    selected = set(args.sources.split(","))
    records, counts = collect(selected, dedup=not args.no_dedup)

    if args.list_sources:
        for name, root, _ in SOURCES:
            print(f"{name:20s} {'存在' if os.path.isdir(root) else '缺失':4s} "
                  f"原始记录 {fmt(counts.get(name, 0)):>8}  {root}")
        print(f"\n去重后记录数: {fmt(len(records))}")
        return

    date_first = (args.by_day or args.by_month) and not args.sort_by_usage

    if args.by_day or args.by_month:
        for r in records:
            d = r["date"] or "unknown"
            r["day"] = d[:7] if args.by_month else d
    keys = (["day"] if (args.by_day or args.by_month) else []) \
        + (["source"] if args.by_source else []) + ["model"]
    agg = aggregate(records, keys, args.since, args.until)

    if args.json:
        print(json.dumps({
            "sources": counts,
            "records": len(records),
            "groupBy": keys,
            "totals": [
                dict(zip(keys, k if isinstance(k, tuple) else (k,)), **{f: v[f] for f in
                     ("requests", "input", "output", "total", "cache", "credit")})
                for k, v in sort_rows(agg, date_first)
            ],
        }, ensure_ascii=False, indent=2))
        return

    print(f"CodeBuddy 全系列 Token 统计  (数据源: {', '.join(sorted(counts))})")
    if args.since and args.until:
        period = f"，{args.since} ~ {args.until}"
    elif args.since:
        period = f"，自 {args.since}"
    elif args.until:
        period = f"，截至 {args.until}"
    else:
        period = ""
    print(f"去重后 {fmt(len(records))} 条请求{period}")
    order = "日期倒序，同日内按用量倒序" if date_first else "按用量倒序"
    print_table(agg, keys, "按 " + " / ".join(keys) + " 汇总（" + order + "）", date_first)

    if not (args.by_source or args.by_day or args.by_month):
        by_source = aggregate(records, ["source"], args.since, args.until)
        print("\n各来源合计：")
        for k, v in sorted(by_source.items(), key=lambda kv: -kv[1]["total"]):
            print(f"  {k[0]:<20s} {fmt(v['total']):>16} tokens  ({fmt(v['requests'])} 请求)")


if __name__ == "__main__":
    main()
