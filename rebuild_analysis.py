# -*- coding: utf-8 -*-
"""从缓存重新生成分析文件"""
import json
import sys
import io
from pathlib import Path
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

OUTPUT_DIR = Path(r"C:\Users\enthalpy\WorkBuddy\Claw\notiforward\analysis")
CACHE_FILE = Path(r"C:\Users\enthalpy\WorkBuddy\Claw\notiforward\.analysis_cache.json")

results = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
print(f"缓存结果: {len(results)} 条\n")

todos = [r for r in results if r and r["needs_todo"]]
high = [r for r in results if r and r["importance"] == "high"]
work = [r for r in results if r and r["is_work"]]
others = [r for r in results if r and not r["is_work"] and not r["needs_todo"] and r["importance"] != "high"]

today = datetime.now().strftime("%Y-%m-%d")
lines = [f"# 微信消息分析 {today}", ""]

if todos:
    lines.append("## 📌 待办事项")
    for r in todos:
        lines.append(f"- [ ] **{r['todo_text']}**（来自 {r['source']}，{r['time']}）")
    lines.append("")

if high:
    lines.append("## 🔴 重要消息")
    for r in high:
        lines.append(f"- [{r['time']}] {r['source']}：{r['summary']}")
        lines.append(f"  - 原文：{r['text'][:100]}")
    lines.append("")

if work:
    lines.append("## 💼 工作消息")
    for r in work:
        lines.append(f"- [{r['time']}] {r['source']}：{r['summary']}")
    lines.append("")

if others:
    lines.append("## 其他消息")
    for r in others:
        lines.append(f"- [{r['time']}] {r['source']}：{r['summary']}")

content = "\n".join(lines)
out_file = OUTPUT_DIR / f"{today}.md"
out_file.write_text(content, encoding="utf-8")
print("已写入:", out_file)
print(f"文件大小: {out_file.stat().st_size} 字节")
print()
print("---- 内容预览 ----")
print(content)
