# -*- coding: utf-8 -*-
"""补分类失败的消息（通用版）

数据源（按优先级）：
1. failed_classify.jsonl — classify_messages.py 分类失败时自动记录的队列
2. 兜底：扫描 messages/*.jsonl 中 time 不在缓存里的消息（如旧版遗留）

处理：规则层优先（与主分类器一致），未命中走 AI；
成功后写入缓存（原子替换）并从失败队列移除；
最后自动重建 analysis/*.md。

用法: python fix_missing.py [--dry-run]
"""
import json
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = Path(__file__).resolve().parent
FAILED_FILE = BASE / "failed_classify.jsonl"

# 无论从哪个目录运行，都能 import 到同目录的主分类器模块
sys.path.insert(0, str(BASE))
import classify_messages as cm  # noqa: E402  复用主分类器的规则层/缓存/写入逻辑


def load_failed():
    """读取失败队列（按 time+title+text 去重）"""
    msgs = []
    seen = set()
    try:
        for line in FAILED_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                m = json.loads(line)
            except json.JSONDecodeError:
                continue
            key = (m.get("time", ""), m.get("title", ""), m.get("full_text") or m.get("text", ""))
            if key in seen:
                continue
            seen.add(key)
            msgs.append(m)
    except FileNotFoundError:
        pass
    return msgs


def find_missing_from_messages():
    """兜底：扫描 messages/ 中 time 不在缓存里的消息（旧版遗留场景）"""
    cache = cm.load_cache()
    cache_times = {str(r.get("time", "")) for r in cache}
    missing = []
    for f in sorted(cm.MESSAGES_DIR.glob("*.jsonl")):
        try:
            lines = f.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                m = json.loads(line)
            except json.JSONDecodeError:
                continue
            if m.get("app") and str(m.get("time", "")) not in cache_times:
                missing.append(m)
    return missing


def save_failed(msgs):
    """把仍失败的消息写回失败队列（原子替换）"""
    tmp = FAILED_FILE.with_suffix(".tmp")
    try:
        tmp.write_text("\n".join(json.dumps(m, ensure_ascii=False) for m in msgs) + ("\n" if msgs else ""),
                       encoding="utf-8")
        tmp.replace(FAILED_FILE)
        return True
    except OSError as e:
        print(f"  警告: 失败队列更新失败: {e}")
        return False


def main():
    if not cm.AI_KEY:
        print("错误: 未配置 API Key（DEEPSEEK_API_KEY 或 config.local.json 的 api_key），无法补分类")
        sys.exit(1)

    dry_run = "--dry-run" in sys.argv
    cache = cm.load_cache()
    failed = load_failed()
    missing = find_missing_from_messages()

    # 失败队列为主，消息扫描为兜底（避免重复补同一批）
    target = failed if failed else missing
    if not target:
        print("没有需要补分类的消息 🎉")
        return

    print(f"需要补分类 {len(target)} 条（来源: {'失败队列' if failed else '消息扫描'}）\n")
    still_failed = []
    done = 0
    for m in target:
        t = m.get("time", "")
        title = m.get("title", "")
        text = (m.get("full_text") or m.get("text") or m.get("raw", ""))[:50]
        # 已在缓存中（可能另一轮已补）则跳过
        if t and any(str(r.get("time", "")) == str(t) for r in cache):
            continue
        print(f"[{t}] {title}: {text}")
        rule = cm.rule_classify(m)
        cls = rule if rule else cm.classify_with_ai(m)
        if not cls:
            print("  分类失败，保留在失败队列（可用 --dry-run 只看不动）")
            still_failed.append(m)
            continue
        result = cm.format_result(m, cls)
        if not cm._cache_has(cache, result):
            cache.append(result)
        done += 1
        tag = "规则" if rule else "AI"
        print(f"  → [{tag}] {'💼' if result['is_work'] else ''}{'🔴' if result['importance']=='high' else ''}{'📌' if result['needs_todo'] else ''} {result['category']}: {result['summary']}")
        time.sleep(0.5)

    if dry_run:
        print(f"\n(dry-run) 未写入任何文件。将补 {done} 条，仍失败 {len(still_failed)} 条")
        return

    if done == 0 and not still_failed:
        print("\n没有新补分类（目标消息均已在缓存中）")
        return

    # 更新失败队列（仅保留仍失败的），写缓存，重建分析文件
    save_failed(still_failed)
    if cm.save_cache(cache):
        print(f"\n缓存更新完成，共 {len(cache)} 条")
    else:
        print("\n严重: 缓存保存失败")
    out = cm.write_analysis(cache)
    print(f"分析文件已重建: {out}")


if __name__ == "__main__":
    main()
