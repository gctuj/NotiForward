# -*- coding: utf-8 -*-
"""
清理消息文件：按 (时间+来源+内容) 去重，剔除无 app 字段的测试消息
用法: python dedup_messages.py [--dry-run]
"""
import json
import sys
import io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

MESSAGES_DIR = Path(r"C:\Users\enthalpy\WorkBuddy\Claw\notiforward\messages")
DRY_RUN = "--dry-run" in sys.argv

total_before = 0
total_after = 0
removed_dups = 0
removed_test = 0

for f in sorted(MESSAGES_DIR.glob("*.jsonl")):
    lines = f.read_text(encoding="utf-8").strip().split("\n")
    lines = [l for l in lines if l.strip()]
    total_before += len(lines)

    seen = set()
    kept = []
    for line in lines:
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        # 剔除无 app 字段的测试消息
        if not d.get("app"):
            removed_test += 1
            continue
        # 去重 key: 时间 + 标题 + 内容
        key = (d.get("time", ""), d.get("title", ""), d.get("full_text", "") or d.get("text", ""))
        if key in seen:
            removed_dups += 1
            continue
        seen.add(key)
        kept.append(line)

    total_after += len(kept)
    if not DRY_RUN:
        f.write_text("\n".join(kept) + "\n", encoding="utf-8")
    print(f"{f.name}: {len(lines)} -> {len(kept)} (去重 {len(lines)-len(kept)})")

print(f"\n总计: {total_before} -> {total_after}")
print(f"删除测试消息: {removed_test}, 删除重复: {removed_dups}")
print("DRY RUN，未实际修改" if DRY_RUN else "已写入")
