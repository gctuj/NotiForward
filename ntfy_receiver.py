"""
NotiForward PC 端接收脚本 v6
从 ntfy.sh 拉取手机转发来的通知，存到本地文件
方案：轮询模式（poll=1 + timeout=60）断点续传，有消息立即返回，无消息 60 秒空返回
相比 SSE 长连接更可靠：连接假死/断线最多 65 秒内自动恢复，配合内存去重绝不重复
"""
import json
import os
import socket
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from pathlib import Path

# Windows 控制台默认 GBK 编码，打印含特殊 Unicode 字符（emoji、替换符等）会抛异常，
# 导致消息处理中断、断点续传不推进。强制 UTF-8 输出。
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ===== 配置 =====
NTFY_TOPIC = "notiforward-1785671711653"  # 和 App 里设置的 topic 一致（2026-08-02 19:59 用户更新）
NTFY_BASE = f"https://ntfy.sh/{NTFY_TOPIC}/json"
OUTPUT_DIR = Path(r"C:\Users\enthalpy\WorkBuddy\Claw\notiforward\messages")
STATE_FILE = Path(r"C:\Users\enthalpy\WorkBuddy\Claw\notiforward\.last_msg_id")
RECONNECT_DELAY = 10  # 秒，断线后重连等待
LOCK_PORT = 8899  # 单实例锁端口，防止多个接收器重复拉取
RETENTION_DAYS = 7  # load_seen 只加载最近 N 天的文件（与 cleanup_old_records.py 默认保留期一致）


def acquire_lock():
    """通过绑定本地端口实现单实例锁，已有实例在运行时直接退出"""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", LOCK_PORT))
        s.listen(1)
        return s
    except OSError:
        print(f"[{now()}] 已有接收器实例在运行 (端口 {LOCK_PORT} 被占用)，本实例退出")
        sys.exit(0)

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def now():
    return datetime.now().strftime("%H:%M:%S")


def load_last_id():
    """读取上次处理到的消息 ID"""
    try:
        return STATE_FILE.read_text().strip()
    except Exception:
        return None


def save_last_id(msg_id):
    """保存最后处理的消息 ID（临时文件 + 原子替换，防进程被杀写坏状态文件）。
    返回是否写入成功，失败时调用方不应继续推进断点。"""
    tmp = STATE_FILE.with_suffix(".tmp")
    try:
        tmp.write_text(msg_id, encoding="utf-8")
        os.replace(tmp, STATE_FILE)
        return True
    except Exception as e:
        print(f"[{now()}] 警告: 保存断点失败（{e}），下轮将重拉本批消息")
        return False


def load_seen():
    """从最近 RETENTION_DAYS 天的消息文件加载去重 key，防止重启后重复落盘。
    只加载最近 N 天：与 cleanup_old_records.py 的默认保留期一致，避免长期运行内存膨胀。"""
    seen = set()
    cutoff = (datetime.now().date() - timedelta(days=RETENTION_DAYS)).isoformat()
    for f in OUTPUT_DIR.glob("*.jsonl"):
        # 文件名形如 YYYY-MM-DD.jsonl 或 YYYY-MM-DD-alt-*.jsonl，只加载保留期内的
        name = f.stem
        date_part = name[:10] if len(name) >= 10 else ""  # 取完整日期前 10 位（YYYY-MM-DD）
        if not (date_part.startswith("20") and date_part >= cutoff):
            continue
        try:
            lines = f.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("app"):
                seen.add(make_dedup_key(d))
    return seen


def make_dedup_key(d):
    """去重键：ntfy 消息 id + 时间 + 来源 + 内容。
    ntfy_id 是服务端唯一键，能区分同秒同内容的独立消息；
    老记录无 ntfy_id 字段时退化为 (time, title, text)。"""
    return (
        d.get("ntfy_id", ""),
        d.get("time", ""),
        d.get("title", ""),
        d.get("full_text", "") or d.get("text", ""),
    )


def subscribe(seen):
    """轮询拉取新消息：poll=1 + timeout=60，有消息立即返回，无消息 60 秒后空返回
    比 SSE 长连接可靠：连接假死/断线最多 65 秒内自动恢复，不会傻等"""
    last_id = load_last_id()
    # 首次运行拉全部历史，之后用 since=<last_id> 只拉新消息
    since = last_id if last_id else "all"
    url = f"{NTFY_BASE}?poll=1&since={since}&timeout=60"
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "NotiForward-PC/6.0")
    req.add_header("Accept", "application/json")

    print(f"[{now()}] 轮询 ntfy.sh (since={since}) ...")
    with urllib.request.urlopen(req, timeout=90) as resp:
        raw = resp.read().decode("utf-8")
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if msg.get("event") != "message":
                continue
            msg_id = msg.get("id", "")
            payload = msg.get("message", "")
            if not payload:
                # keepalive 等空消息不落盘；有 id 仍推进断点，避免下次重复拉取
                if msg_id:
                    save_last_id(msg_id)
                continue
            # 先落盘成功，再推进断点：落盘失败时不推进 last_id，
            # 下轮 since=<旧值> 重拉本批，内存 seen 去重保证已成功的不会重复落盘
            if process_message(payload, seen, msg_id) and msg_id:
                save_last_id(msg_id)


def process_message(raw, seen, ntfy_id=""):
    """处理收到的消息（带去重）。返回是否成功落盘：非通知消息/重复消息视为已处理（True），
    落盘失败返回 False（调用方不推进断点，下轮重拉重试）"""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # 非 JSON 消息（比如测试消息），只打印不存盘
        print(f"[{now()}] 收到(非通知): {raw[:80]}")
        return True

    # 只处理真正的 App 通知（微信等），测试消息不落盘
    if not data.get("app"):
        print(f"[{now()}] 收到(非通知消息): {str(data)[:80]}")
        return True

    data["ntfy_id"] = ntfy_id  # 注入服务端唯一 id，供去重与断点对齐
    # 去重：同一 ntfy id + 时间 + 来源 + 内容 只落盘一次
    dedup_key = make_dedup_key(data)
    if dedup_key in seen:
        print(f"[{now()}] 跳过重复: {data.get('title','')} | {(data.get('full_text') or data.get('text',''))[:30]}")
        return True
    seen.add(dedup_key)

    title = data.get("title", "")
    text = data.get("full_text") or data.get("text", "")
    lines = data.get("text_lines", [])
    ts = data.get("time", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    print(f"\n{'='*50}")
    print(f"[{ts}] {title}")
    if lines:
        for line in lines:
            print(f"  {line}")
    else:
        print(f"  {text}")
    print(f"{'='*50}")

    return save_message(data)


_ALT_FILE = None  # 主文件被锁时的备用文件（按天切换）


def save_message(data):
    """把消息追加到当天的日志文件；主文件写入失败时改用带日期的备用文件。
    返回是否落盘成功。"""
    global _ALT_FILE
    today = datetime.now().strftime("%Y-%m-%d")
    # 跨天后重置备用文件，回到当天主文件
    if _ALT_FILE and not _ALT_FILE.name.startswith(f"{today}-alt"):
        _ALT_FILE = None
    log_file = _ALT_FILE if _ALT_FILE else OUTPUT_DIR / f"{today}.jsonl"
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False) + "\n")
        return True
    except OSError as e:
        # 主文件被锁/磁盘问题：切到带日期的备用文件重试一次
        if log_file != _ALT_FILE:
            alt = OUTPUT_DIR / f"{today}-alt-{datetime.now().strftime('%H%M%S')}.jsonl"
            try:
                with open(alt, "a", encoding="utf-8") as f:
                    f.write(json.dumps(data, ensure_ascii=False) + "\n")
                _ALT_FILE = alt
                print(f"[{now()}] 主文件写入失败（{e}），改用备用文件: {alt.name}")
                return True
            except OSError as e2:
                _ALT_FILE = None  # 备用也失败：重置回主文件，下轮重试
                print(f"[{now()}] 错误: 主文件与备用文件都写入失败: {e2}")
                return False
        else:
            _ALT_FILE = None
            print(f"[{now()}] 错误: 备用文件写入失败（{e}），下轮重试主文件")
            return False


def main():
    print(f"NotiForward PC 接收器 v6 启动")
    print(f"Topic: {NTFY_TOPIC}")
    print(f"消息保存到: {OUTPUT_DIR}")
    print(f"轮询模式（60 秒超时），断点续传只拉新消息\n")

    lock = acquire_lock()
    seen = load_seen()
    print(f"已加载 {len(seen)} 条历史去重记录\n")
    while True:
        try:
            subscribe(seen)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                print(f"[{now()}] 被限流，60秒后重试...")
                time.sleep(60)
            else:
                print(f"[{now()}] HTTP错误: {e.code}，{RECONNECT_DELAY}秒后重连...")
                time.sleep(RECONNECT_DELAY)
        except urllib.error.URLError as e:
            print(f"[{now()}] 网络错误: {e.reason}，{RECONNECT_DELAY}秒后重连...")
            time.sleep(RECONNECT_DELAY)
        except Exception as e:
            print(f"[{now()}] 错误: {e}，{RECONNECT_DELAY}秒后重连...")
            time.sleep(RECONNECT_DELAY)
        else:
            print(f"[{now()}] 轮询结束，5秒后继续...")
            time.sleep(5)


if __name__ == "__main__":
    main()
