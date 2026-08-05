# -*- coding: utf-8 -*-
"""查看完整分析文件和一致性"""
import json
import sys
import io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

BASE = Path(r"C:\Users\enthalpy\WorkBuddy\Claw\notiforward")

# 分析文件
analysis = BASE / "analysis" / "2026-08-02.md"
print("===== 分析文件 =====")
print(analysis.read_text(encoding="utf-8"))

# 一致性
msg_count = len((BASE / "messages" / "2026-08-02.jsonl").read_text(encoding="utf-8").strip().split("\n"))
cf = BASE / ".classified_count"
cf_val = cf.read_text(encoding="utf-8").strip() if cf.exists() else "N/A"
cache = json.loads((BASE / ".analysis_cache.json").read_text(encoding="utf-8"))
print(f"\n===== 一致性 =====\n消息: {msg_count} 条 | 进度: {cf_val} | 缓存: {len(cache)} 条")
