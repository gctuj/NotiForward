# -*- coding: utf-8 -*-
"""彻底重置分类状态：清缓存、清进度、清分析文件"""
import sys
import io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

BASE = Path(r"C:\Users\enthalpy\WorkBuddy\Claw\notiforward")

for p in [
    BASE / ".analysis_cache.json",
    BASE / ".classified_count",
    BASE / "analysis" / "2026-08-02.md",
]:
    if p.exists():
        p.unlink()
        print(f"已删除: {p.name}")
    else:
        print(f"不存在(跳过): {p.name}")

print("\n重置完成，等待重新分类")
