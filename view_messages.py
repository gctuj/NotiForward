# -*- coding: utf-8 -*-
"""查看最新消息"""
import json
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

path = r"C:/Users/enthalpy/WorkBuddy/Claw/notiforward/messages/2026-08-02.jsonl"
lines = open(path, encoding="utf-8").read().strip().split("\n")
print(f"共 {len(lines)} 条消息\n")
print("=== 最后 5 条 ===")
for line in lines[-5:]:
    try:
        d = json.loads(line)
        t = d.get("time", "")
        app = d.get("app", "")
        title = d.get("title", "")
        text = (d.get("full_text") or d.get("text") or "").replace("\n", " ")
        print(f"[{t}] {app} | {title} | {text[:100]}")
    except Exception as e:
        print("RAW:", line[:80])
