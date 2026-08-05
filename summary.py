"""
NotiForward 精简摘要生成器 v5（微信版）
从分类缓存生成 QQ 友好的精简格式
只显示重要消息：待办优先，其余重要/工作消息一行一条
用法: python summary.py
"""
import json
from datetime import datetime
from pathlib import Path

CACHE_FILE = Path(r"C:\Users\enthalpy\WorkBuddy\Claw\notiforward\.analysis_cache.json")
TITLE = "【今日微信重要消息】"


def load_cache():
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def short_time(t):
    try:
        return t.split(" ")[1][:5]
    except Exception:
        return t


def build_summary():
    cache = load_cache()
    if not cache:
        return f"{TITLE}暂无记录"

    todos = [r for r in cache if r.get("needs_todo") and r.get("todo_text")]
    highs = [r for r in cache if r.get("importance") == "high"]
    mediums = [r for r in cache if r.get("importance") == "medium"]

    lines = [TITLE]
    shown = set()

    # 1. 待办（同一来源 5 分钟内的重要消息自动并入待办详情）
    todos_sorted = sorted(todos, key=lambda x: x.get("time", ""))
    todo_lines = []
    for r in todos_sorted:
        key = ("todo", r.get("todo_text", ""))
        if key in shown:
            continue
        shown.add(key)
        src = r.get("source", "")
        tm = short_time(r.get("time", ""))
        # 找同一来源、时间相近的补充消息（high/medium）
        extras = []
        for o in sorted(highs + mediums, key=lambda x: x.get("time", "")):
            if o.get("source") == src and o.get("todo_text") in ("", None) and o.get("summary"):
                # 时间差在 10 分钟内视为补充
                try:
                    t1 = datetime.strptime(r.get("time", ""), "%Y-%m-%d %H:%M:%S")
                    t2 = datetime.strptime(o.get("time", ""), "%Y-%m-%d %H:%M:%S")
                    if abs((t2 - t1).total_seconds()) <= 600 and ("todo", o.get("time", ""), o.get("summary", "")) not in shown:
                        shown.add(("msg", o.get("time", ""), o.get("summary", "")))
                        extras.append(o.get("summary", ""))
                except Exception:
                    pass
        todo_lines.append(f"①  {r['todo_text']}")
        for e in extras:
            todo_lines.append(f"    · {e}")
        if src:
            todo_lines.append(f"    {src} {tm}")
    if todo_lines:
        lines.append("📌 待办")
        lines.extend(todo_lines)

    # 2. 其他重要消息（排除与待办同时间的）
    todo_times = {t.get("time", "") for t in todos}
    other_lines = []
    for r in sorted(highs + mediums, key=lambda x: x.get("time", "")):
        if r.get("time", "") in todo_times:
            continue
        key = ("msg", r.get("time", ""), r.get("summary", ""))
        if key in shown:
            continue
        shown.add(key)
        tm = short_time(r.get("time", ""))
        other_lines.append(f"· [{tm}] {r['summary']}")
    if other_lines:
        lines.append("📌 重要")
        lines.extend(other_lines)

    if not todo_lines and not other_lines:
        return f"{TITLE}\n暂无重要消息，都是闲聊 😊"

    omitted = max(len(cache) - len(shown), 0)
    if omitted > 0:
        lines.append(f"\n（其余 {omitted} 条闲聊已省略）")

    return "\n".join(lines)


if __name__ == "__main__":
    print(build_summary())
