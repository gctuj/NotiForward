# -*- coding: utf-8 -*-
"""对比消息和缓存，找出缺失的消息"""
import json
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

msgs = []
for line in open(r"C:\Users\enthalpy\WorkBuddy\Claw\notiforward\messages\2026-08-02.jsonl", encoding="utf-8"):
    line = line.strip()
    if not line:
        continue
    msgs.append(json.loads(line))

cache = json.load(open(r"C:\Users\enthalpy\WorkBuddy\Claw\notiforward\.analysis_cache.json", encoding="utf-8"))
cache_times = {r["time"] for r in cache}

print(f"消息 {len(msgs)} 条, 缓存 {len(cache)} 条\n")
print("=== 缺失的消息（未分类成功）===")
for m in msgs:
    t = m.get("time", "")
    if t not in cache_times:
        print(f"  [{t}] {m.get('title')} | {(m.get('full_text') or m.get('text',''))[:80]}")

print("\n=== 缓存中所有消息 ===")
for r in cache:
    print(f"  [{r['time']}] {r['source']} | {r['summary'][:50]} | 工作:{r['is_work']} 重要:{r['importance']}")
