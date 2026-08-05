"""
NotiForward 智能消息分类脚本
用 DeepSeek API 判断微信消息：是否工作、是否重要、是否待办
读取 notiforward/messages/*.jsonl 中的新消息，输出分类结果
"""
import json
import os
import socket
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

# ===== 配置 =====
MESSAGES_DIR = Path(r"C:\Users\enthalpy\WorkBuddy\Claw\notiforward\messages")
OUTPUT_DIR = Path(r"C:\Users\enthalpy\WorkBuddy\Claw\notiforward\analysis")
# ===== 状态文件 =====
STATE_FILE = Path(r"C:\Users\enthalpy\WorkBuddy\Claw\notiforward\.classified_count")
CACHE_FILE = Path(r"C:\Users\enthalpy\WorkBuddy\Claw\notiforward\.analysis_cache.json")  # 已分类结果缓存，防止覆盖历史
LOCK_PORT = 8897  # 单实例锁端口，防止多个分类器同时运行

# ===== AI 配置（默认 DeepSeek；任何 OpenAI 兼容接口都可用） =====
def _load_local_config():
    cfg = {}
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.local.json"),
                  encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        pass
    return cfg


def _cfg_val(env_name, cfg, *keys, default=""):
    """按 环境变量 → 本地配置 的顺序取值（keys 为 config.local.json 中的字段名）"""
    v = os.environ.get(env_name, "").strip()
    if v:
        return v
    for k in keys:
        v = cfg.get(k)
        if v:
            return str(v)
    return default


_LOCAL = _load_local_config()
# 任意 OpenAI 兼容服务的 base_url / model / api_key 均可，通过环境变量或 config.local.json 切换
AI_URL = _cfg_val("AI_BASE_URL", _LOCAL, "base_url", default="https://api.deepseek.com/chat/completions")
AI_MODEL = _cfg_val("AI_MODEL", _LOCAL, "model", default="deepseek-v4-flash")
AI_KEY = _cfg_val("DEEPSEEK_API_KEY", _LOCAL, "api_key", "deepseek_api_key")
if not AI_KEY:
    print("⚠ 未配置 API Key：设置环境变量 DEEPSEEK_API_KEY，或 config.local.json 的 api_key 字段（任意 OpenAI 兼容服务的 Key 均可）")

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def acquire_lock():
    """通过绑定本地端口实现单实例锁，已有实例在运行时直接退出"""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", LOCK_PORT))
        s.listen(1)
        return s
    except OSError:
        print(f"[{now()}] 已有分类器实例在运行 (端口 {LOCK_PORT} 被占用)，本实例退出")
        sys.exit(0)

# ===== 规则层配置（优先于 AI，保证精准 + 零延迟） =====
# 用户确认过的工作来源（这些来源基本都算工作消息）
WORK_SOURCES = [
    "陈国良", "吴克奇", "白福欣", "工程芜湖项目部监理群",
]
# 工作关键词（消息内容命中即视为工作）
WORK_KEYWORDS = [
    "铁塔", "监理", "旁站", "基坑", "混凝土", "浇筑", "验收", "图纸",
    "项目部", "施工", "甲方", "会议", "资料", "项目",
]
# 游戏群（这些群聊基本都是游戏，不是工作）
GAME_SOURCES = [
    "永劫糕手", "fpsのgun king", "FPS", "游戏",
]
# 闲聊特征：纯表情、单个字、语气词
CHAT_PATTERNS = [
    "ww", "哈哈", "呵呵", "嗯", "哦", "好的", "ok", "OK", "收到", "在吗", "？", "?", "。。", "……", "牛逼", "傻逼",
]


def rule_classify(msg):
    """规则层预分类：只处理高置信度情况，命中直接返回结果不调 AI。返回 None 表示需要 AI 兜底"""
    title = (msg.get("title") or "").strip()
    text = (msg.get("full_text") or msg.get("text") or msg.get("raw") or "").strip()

    # 1. 纯闲聊特征（表情/单字/语气词）→ 闲聊（最高优先级，任何来源都适用）
    if len(text) <= 8:
        for p in CHAT_PATTERNS:
            if p in text:
                return {
                    "is_work": False,
                    "importance": "low",
                    "needs_todo": False,
                    "todo_text": "",
                    "category": "闲聊",
                    "summary": "闲聊消息"
                }

    # 2. 游戏群直接归为游戏（除非内容含工作关键词，如铁塔项目名误发）
    is_game_group = any(g in title for g in GAME_SOURCES)
    if is_game_group and not any(kw in text for kw in WORK_KEYWORDS):
        return {
            "is_work": False,
            "importance": "low",
            "needs_todo": False,
            "todo_text": "",
            "category": "游戏",
            "summary": "游戏群消息"
        }

    # 3. 工作关键词命中 → 工作（高置信度）
    if any(kw in text for kw in WORK_KEYWORDS):
        return {
            "is_work": True,
            "importance": "medium",
            "needs_todo": False,
            "todo_text": "",
            "category": "工作",
            "summary": text[:60]
        }

    # 其余情况（包括工作来源但内容不明确）交给 AI 判断，保证精准
    return None



SYSTEM_PROMPT = """你是一个微信消息分类助手。用户是建筑监理工程师。
对每条消息（title 是群名或联系人），输出 JSON 格式分类结果：
{
  "is_work": true/false,          // 是否工作相关消息
  "importance": "high"/"medium"/"low",  // 重要程度
  "needs_todo": true/false,       // 是否需要做待办
  "todo_text": "待办内容",         // 如果是待办，具体要做什么（否则空字符串）
  "category": "工作/学校/游戏/生活/闲聊",  // 消息类别
  "summary": "一句话摘要"          // 简洁摘要
}
判断标准：
- is_work：涉及监理、工程、项目、施工、验收、资料、甲方、同事工作安排等。
  注意：来自工作联系人（陈国良、吴克奇、白福欣）的消息倾向于工作，但如果是明显的生活闲聊（问吃的、聊天、钱的事等）则不算工作。
- importance high：紧急事项、截止日期、上级/领导安排、需要立即处理
- needs_todo：消息里有明确行动要求（回复某人、交资料、参加会议、完成任务等）
- 游戏群闲聊、朋友闲聊归为 low importance
只输出 JSON，不要其他文字。"""


def load_cache():
    """读取已分类的结果缓存（list of dict）"""
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_cache(results):
    """保存全部分类结果到缓存，带重试"""
    for attempt in range(3):
        try:
            CACHE_FILE.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
            return True
        except Exception as e:
            if attempt < 2:
                time.sleep(1)
            else:
                print(f"  警告: 缓存保存失败: {e}")


def get_all_messages():
    """读取所有消息，按时间排序"""
    all_msgs = []
    for f in sorted(MESSAGES_DIR.glob("*.jsonl")):
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    all_msgs.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return all_msgs


def filter_new(all_msgs, cursor):
    """按时间游标筛选新消息（消息 time 字符串大于游标视为新）
    cursor 为空时全部视为新消息。相比旧版"已分类条数"索引方案，
    游标方案在清理脚本删除旧文件后不会错位。"""
    if not cursor:
        return list(all_msgs)
    return [m for m in all_msgs if str(m.get("time", "")) > cursor]


def migrate_cursor_from_cache(cache):
    """旧版进度（数字条数）迁移为时间游标：取缓存中最后一条消息的时间。
    无缓存或全空时返回空串（相当于从零开始）。"""
    times = [str(r.get("time", "")) for r in cache if r.get("time")]
    return max(times) if times else ""


def load_cursor():
    """读取进度游标。新格式 = 最后处理消息的时间；旧格式（纯数字条数）返回空串，由调用方从缓存迁移。"""
    try:
        raw = STATE_FILE.read_text().strip()
    except Exception:
        return ""
    if not raw or raw.isdigit():
        return ""
    return raw


def save_cursor(cursor):
    """保存进度游标，带重试（Windows 文件锁冲突时重试）"""
    for attempt in range(3):
        try:
            STATE_FILE.write_text(str(cursor))
            return True
        except Exception as e:
            if attempt < 2:
                time.sleep(1)
            else:
                print(f"  警告: 进度保存失败: {e}")
    return False


def classify_with_ai(msg):
    """调用 AI（智谱 GLM）分类单条消息"""
    title = msg.get("title", "")
    text = msg.get("full_text") or msg.get("text") or msg.get("raw", "")
    content = f"消息来源(群名或联系人): {title}\n消息内容: {text}"

    payload = json.dumps({
        "model": AI_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content}
        ],
        "max_tokens": 1000,
        "temperature": 0.1
    }).encode("utf-8")

    req = urllib.request.Request(AI_URL, data=payload, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {AI_KEY}"
    })

    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            message = result["choices"][0]["message"]
            # GLM reasoning 模型：content 为空时尝试 reasoning_content
            content = message.get("content") or ""
            if not content.strip():
                content = message.get("reasoning_content") or ""
            return extract_json(content)
    except urllib.error.HTTPError as e:
        if e.code == 429:
            print(f"  分类被限流(429)，跳过")
        else:
            print(f"  HTTP错误: {e.code}")
        return None
    except Exception as e:
        print(f"  分类失败: {e}")
        return None


def extract_json(content):
    """从模型输出中提取 JSON（容错处理 markdown 代码块、截断等）"""
    content = content.strip()
    # 去掉 markdown 代码块
    if content.startswith("```"):
        content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
    # 尝试找到第一个 { 和最后一个 }
    try:
        start = content.index("{")
        end = content.rindex("}")
        return json.loads(content[start:end + 1])
    except (ValueError, json.JSONDecodeError):
        pass
    # 最后尝试修复截断的 JSON（补引号/括号）
    try:
        import re
        # 移除非法尾逗号，尝试补齐
        content = re.sub(r",\s*}", "}", content)
        start = content.index("{")
        end = content.rindex("}")
        return json.loads(content[start:end + 1])
    except Exception:
        return None


def format_result(msg, classification):
    """格式化分类结果输出"""
    title = msg.get("title", "")
    text = msg.get("full_text") or msg.get("text") or msg.get("raw", "")
    ts = msg.get("time", "")

    if not classification:
        return None

    is_work = classification.get("is_work", False)
    importance = classification.get("importance", "low")
    needs_todo = classification.get("needs_todo", False)
    todo_text = classification.get("todo_text", "")
    category = classification.get("category", "闲聊")
    summary = classification.get("summary", "")

    # 标记
    tags = []
    if is_work:
        tags.append("💼工作")
    if importance == "high":
        tags.append("🔴重要")
    elif importance == "medium":
        tags.append("🟡一般")
    if needs_todo:
        tags.append("📌待办")

    return {
        "time": ts,
        "source": title,
        "text": text,
        "app": msg.get("app", ""),   # 消息来源应用：微信 / QQ
        "tags": tags,
        "importance": importance,
        "is_work": is_work,
        "needs_todo": needs_todo,
        "todo_text": todo_text,
        "category": category,
        "summary": summary
    }


def write_analysis(results):
    """把分类结果写入当天分析文件"""
    today = datetime.now().strftime("%Y-%m-%d")
    out_file = OUTPUT_DIR / f"{today}.md"

    todos = [r for r in results if r and r["needs_todo"]]
    high = [r for r in results if r and r["importance"] == "high"]
    work = [r for r in results if r and r["is_work"]]
    others = [r for r in results if r and not r["is_work"] and not r["needs_todo"] and r["importance"] != "high"]

    lines = [f"# 微信消息分析 {today}", ""]

    if todos:
        lines.append("## 📌 待办事项")
        for r in todos:
            lines.append(f"- [ ] **{r['todo_text']}**（来自 {r['source']}，{r['time']}）")
        lines.append("")

    if high:
        lines.append("## 🔴 重要消息")
        for r in high:
            lines.append(f"- [{r['time']}] {r['source']}：{r['summary']}")
            lines.append(f"  - 原文：{r['text'][:100]}")
        lines.append("")

    if work:
        lines.append("## 💼 工作消息")
        for r in work:
            lines.append(f"- [{r['time']}] {r['source']}：{r['summary']}")
        lines.append("")

    if others:
        lines.append("## 其他消息")
        for r in others:
            lines.append(f"- [{r['time']}] {r['source']}：{r['summary']}")

    out_file.write_text("\n".join(lines), encoding="utf-8")
    return out_file


def main():
    print(f"NotiForward 智能分类启动")
    print(f"模型: {AI_MODEL}")
    print(f"消息目录: {MESSAGES_DIR}\n")

    cursor = load_cursor()
    if not cursor:
        cursor = migrate_cursor_from_cache(load_cache())
    all_msgs = get_all_messages()

    # 只处理新消息（时间游标，清理旧文件不影响）
    new_msgs = filter_new(all_msgs, cursor)
    if not new_msgs:
        print("没有新消息需要分类")
        return

    print(f"发现 {len(new_msgs)} 条新消息，开始分类...")

    cache = load_cache()
    results = []
    for i, msg in enumerate(new_msgs):
        title = msg.get("title", "")
        text = (msg.get("full_text") or msg.get("text") or msg.get("raw", ""))[:50]
        print(f"[{i+1}/{len(new_msgs)}] {title}: {text}")
        classification = classify_with_ai(msg)
        if classification:
            result = format_result(msg, classification)
            results.append(result)
            cache.append(result)
            print(f"  → {'💼' if result['is_work'] else ''}{'🔴' if result['importance']=='high' else ''}{'📌' if result['needs_todo'] else ''} {result['category']}: {result['summary']}")
        else:
            results.append(None)
        time.sleep(0.5)  # 避免触发限流

    # 保存进度（时间游标）和缓存
    last_time = max(str(m.get("time", "")) for m in new_msgs)
    save_cursor(last_time)
    save_cache(cache)

    if results:
        out_file = write_analysis(cache)
        print(f"\n分类完成！结果已保存: {out_file}")


def classify_msg(msg):
    """分类单条消息：规则层优先，未命中才调 AI"""
    rule_result = rule_classify(msg)
    if rule_result:
        return rule_result
    return classify_with_ai(msg)


def watch():
    """常驻监听模式：检测到消息文件变化立即分类，空闲时每 10 秒检查"""
    print(f"NotiForward 智能分类监听启动（即时触发模式）")
    print(f"模型: {AI_MODEL}")
    print(f"规则层优先，未命中才调 AI\n")

    last_mtime = 0.0
    while True:
        try:
            # 检测消息文件是否变化
            latest_mtime = 0.0
            for f in MESSAGES_DIR.glob("*.jsonl"):
                try:
                    latest_mtime = max(latest_mtime, f.stat().st_mtime)
                except OSError:
                    continue

            if latest_mtime > last_mtime:
                last_mtime = latest_mtime
                cursor = load_cursor()
                if not cursor:
                    cursor = migrate_cursor_from_cache(load_cache())
                all_msgs = get_all_messages()
                new_msgs = filter_new(all_msgs, cursor)

                if new_msgs:
                    print(f"[{now()}] 发现 {len(new_msgs)} 条新消息，即时分类...")
                    cache = load_cache()
                    for i, msg in enumerate(new_msgs):
                        title = msg.get("title", "")
                        text = (msg.get("full_text") or msg.get("text") or msg.get("raw", ""))[:50]
                        print(f"[{i+1}/{len(new_msgs)}] {title}: {text}")
                        classification = classify_msg(msg)
                        if classification:
                            result = format_result(msg, classification)
                            cache.append(result)
                            tag = "规则" if rule_classify(msg) else "AI"
                            print(f"  → [{tag}] {'💼' if result['is_work'] else ''}{'🔴' if result['importance']=='high' else ''}{'📌' if result['needs_todo'] else ''} {result['category']}: {result['summary']}")
                        time.sleep(0.3)

                    last_time = max(str(m.get("time", "")) for m in new_msgs)
                    save_cursor(last_time)
                    save_cache(cache)
                    out_file = write_analysis(cache)
                    print(f"分类完成！结果已保存: {out_file}")
        except Exception as e:
            print(f"[{now()}] 监听出错: {e}")

        time.sleep(10)  # 10 秒检查一次，比 60 秒灵敏


def now():
    return datetime.now().strftime("%H:%M:%S")


if __name__ == "__main__":
    _lock = acquire_lock()  # 必须保持引用，否则 socket 被 GC 关闭导致锁失效
    if "--watch" in sys.argv:
        watch()
    else:
        main()
