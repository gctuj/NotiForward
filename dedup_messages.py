# -*- coding: utf-8 -*-
"""
清理消息文件：按 (ntfy id+时间+来源+内容) 去重，剔除无 app 字段的测试消息
用法: python dedup_messages.py [--dry-run]

安全：接收器（端口 8899）运行时拒绝执行，避免与正在 append 的进程并发
导致丢行/半行损坏；写入用临时文件 + os.replace 原子替换。
"""
import json
import socket
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

MESSAGES_DIR = Path(r"C:\Users\enthalpy\WorkBuddy\Claw\notiforward\messages")
RECEIVER_LOCK_PORT = 8899  # ntfy_receiver.py 的单实例锁端口
DRY_RUN = "--dry-run" in sys.argv


def port_open(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1)
    try:
        s.connect(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def dedup_key(d):
    """与 ntfy_receiver.make_dedup_key 保持一致：ntfy_id + 时间 + 来源 + 内容"""
    return (
        d.get("ntfy_id", ""),
        d.get("time", ""),
        d.get("title", ""),
        d.get("full_text", "") or d.get("text", ""),
    )


def main():
    if port_open(RECEIVER_LOCK_PORT):
        print(f"错误: 接收器正在运行（端口 {RECEIVER_LOCK_PORT}），请先停止再执行去重，"
              f"否则会与实时写入冲突导致数据损坏。")
        sys.exit(1)

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
            # 去重 key（含 ntfy_id，同秒同内容不再误删）
            key = dedup_key(d)
            if key in seen:
                removed_dups += 1
                continue
            seen.add(key)
            kept.append(line)

        total_after += len(kept)
        if not DRY_RUN:
            tmp = f.with_suffix(".tmp")
            tmp.write_text("\n".join(kept) + "\n", encoding="utf-8")
            tmp.replace(f)  # 原子替换，崩溃不损坏原文件
        print(f"{f.name}: {len(lines)} -> {len(kept)} (去重 {len(lines)-len(kept)})")

    print(f"\n总计: {total_before} -> {total_after}")
    print(f"删除测试消息: {removed_test}, 删除重复: {removed_dups}")
    print("DRY RUN，未实际修改" if DRY_RUN else "已写入")


if __name__ == "__main__":
    main()
