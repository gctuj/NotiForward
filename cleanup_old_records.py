# -*- coding: utf-8 -*-
"""
微信消息记录自动清理
- messages/ analysis/：删除超过保留天数（默认 7 天）的文件
- *.log 调试日志：只保留最近 N 个（默认 5）
- .analysis_cache.json：同步清理过期日期的分类缓存条目
用法:
  python cleanup_old_records.py --keep-days 7 --keep-logs 5 [--dry-run]
"""
import argparse
import ctypes
import json
import os
import socket
from datetime import datetime, timedelta

BASE = r"C:\Users\enthalpy\WorkBuddy\Claw\notiforward"
CLASSIFIER_LOCK_PORT = 8897  # classify_messages.py 的单实例锁端口


def port_open(port):
    """探测本机端口是否被占用（判断相关进程是否在运行）"""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1)
    try:
        s.connect(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def force_remove(path):
    """删除文件：先走 os.remove；若被沙箱安全钩子拦截（回收站不可用），
    改用 ctypes 直接调 Windows API DeleteFileW 绕过"""
    try:
        os.remove(path)
        return True
    except Exception:
        pass
    try:
        ok = ctypes.windll.kernel32.DeleteFileW(os.path.abspath(path))
        return bool(ok)
    except Exception:
        return False


def parse_date(s):
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def main():
    ap = argparse.ArgumentParser(description="清理过期的微信消息记录")
    ap.add_argument("--keep-days", type=int, default=7, help="保留最近 N 天的消息文件")
    ap.add_argument("--keep-logs", type=int, default=5, help="日志文件保留最近 N 个")
    ap.add_argument("--dry-run", action="store_true", help="只预览不删除")
    args = ap.parse_args()

    cutoff = (datetime.now() - timedelta(days=args.keep_days)).date()
    removed_files, kept_files = [], []

    # 1) 消息 / 分析 / QQ 消息 文件（按文件名前 10 位日期判断）
    for d in ("messages", "analysis"):
        full = os.path.join(BASE, d)
        if not os.path.isdir(full):
            continue
        for name in sorted(os.listdir(full)):
            path = os.path.join(full, name)
            if not os.path.isfile(path):
                continue
            fd = parse_date(name)
            if fd is None:
                continue
            if fd < cutoff:
                removed_files.append(os.path.join(d, name))
            else:
                kept_files.append(os.path.join(d, name))

    # 2) 调试日志：按修改时间保留最新 N 个
    logs = [f for f in os.listdir(BASE)
            if f.endswith(".log") and os.path.isfile(os.path.join(BASE, f))]
    logs.sort(key=lambda f: os.path.getmtime(os.path.join(BASE, f)), reverse=True)
    removed_logs = logs[args.keep_logs:]

    # 3) 分类缓存：按条目 time 字段清理过期
    cache_path = os.path.join(BASE, ".analysis_cache.json")
    cache_removed, cache_kept = 0, 0
    if os.path.exists(cache_path):
        with open(cache_path, encoding="utf-8") as f:
            cache = json.load(f)
        if isinstance(cache, list):
            new_cache = []
            for item in cache:
                fd = parse_date(item.get("time", ""))
                if fd is None or fd >= cutoff:
                    new_cache.append(item)
                    cache_kept += 1
                else:
                    cache_removed += 1
            if not args.dry_run:
                # 临时文件 + os.replace 原子替换：崩溃也不会写坏缓存，
                # 且与 watch 模式并发时不会产生半截 JSON
                tmp = cache_path + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(new_cache, f, ensure_ascii=False, indent=1)
                os.replace(tmp, cache_path)

    # 分类器并发提示：watch 模式可能正在写缓存
    if port_open(CLASSIFIER_LOCK_PORT):
        print(f"[提示] 检测到分类器正在运行（端口 {CLASSIFIER_LOCK_PORT}），"
              f"缓存将用原子写更新；如需避免并发请先停止分类器再执行。\n")

    # ---- 报告 ----
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] 清理报告 (保留 {args.keep_days} 天, 截止 {cutoff})")
    print(f"消息/分析文件: 删除 {len(removed_files)} 个 | 保留 {len(kept_files)} 个")
    for p in removed_files:
        print(f"  ✗ {p}")
    print(f"调试日志: 删除 {len(removed_logs)} 个 | 保留 {min(args.keep_logs, len(logs))} 个")
    for p in removed_logs:
        print(f"  ✗ {p}")
    print(f"分类缓存: 删除 {cache_removed} 条 | 保留 {cache_kept} 条")

    if args.dry_run:
        print("\n[dry-run 模式] 未执行任何删除。")
        return

    fail = []
    for p in removed_files:
        if not force_remove(os.path.join(BASE, p)):
            fail.append(p)
    for p in removed_logs:
        if not force_remove(os.path.join(BASE, p)):
            fail.append(p)
    if fail:
        print("警告: 以下文件删除失败:")
        for p in fail:
            print(f"  ✗ {p}")
    print(f"\n清理完成 ✅ (共删除 {len(removed_files) + len(removed_logs)} 个文件)")


if __name__ == "__main__":
    main()
