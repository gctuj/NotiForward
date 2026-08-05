# -*- coding: utf-8 -*-
"""补分类失败的消息（含重试）"""
import json
import os
import sys
import io
import time
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
# 密钥优先读环境变量 DEEPSEEK_API_KEY，其次读本地 config.local.json（不入 git）
def _load_api_key():
    k = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if k:
        return k
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.local.json"),
                  encoding="utf-8") as f:
            return json.load(f).get("deepseek_api_key", "")
    except Exception:
        return ""
DEEPSEEK_KEY = _load_api_key()
DEEPSEEK_MODEL = "deepseek-v4-flash"

WORK_CONTEXT = """
用户职业背景：监理工程师（建筑工程），在合肥城市学院读土木工程相关专业。
工作相关：监理日志、旁站记录、基坑开挖、混凝土浇筑、施工单位（北京锦程前方科技有限公司）、
项目经理刘玉斌、铁塔项目（中国铁塔安徽分公司）、项目资料、验收、图纸、会议、甲方、监理单位。
工作群/联系人例子（这些来源基本都算工作消息）：陈国良、吴克奇、白福欣、工程芜湖项目部监理群、
涉及"铁塔"（中国铁塔安徽分公司）的聊天。
游戏群例子：永劫糕手（都来救瓶中饭）是游戏群不是工作群（铁塔项目名在游戏群出现是疑似误发/分享）。
"""

SYSTEM_PROMPT = """你是一个微信消息分类助手。用户是建筑监理工程师。
对每条微信消息，输出 JSON 格式分类结果：
{
  "is_work": true/false,
  "importance": "high"/"medium"/"low",
  "needs_todo": true/false,
  "todo_text": "待办内容",
  "category": "工作/学校/游戏/生活/闲聊",
  "summary": "一句话摘要"
}
判断标准：
- is_work：涉及监理、工程、项目、施工、验收、资料、甲方、同事工作安排等
- importance high：紧急事项、截止日期、上级/领导安排、钱相关、需要立即处理
- needs_todo：消息里有明确行动要求（回复某人、交资料、参加会议、完成任务等）
- 游戏群闲聊、朋友闲聊归为 low importance
只输出 JSON，不要其他文字。"""


def classify_with_retry(msg, retries=3):
    title = msg.get("title", "")
    text = msg.get("full_text") or msg.get("text") or msg.get("raw", "")
    content = f"消息来源(群名或联系人): {title}\n消息内容: {text}"
    payload = json.dumps({
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT + WORK_CONTEXT},
            {"role": "user", "content": content}
        ],
        "max_tokens": 500,
        "temperature": 0.1
    }).encode("utf-8")

    for attempt in range(retries):
        try:
            req = urllib.request.Request(DEEPSEEK_URL, data=payload, headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {DEEPSEEK_KEY}"
            })
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                content_out = result["choices"][0]["message"]["content"].strip()
            if content_out.startswith("```"):
                content_out = content_out.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            return json.loads(content_out)
        except Exception as e:
            print(f"  第{attempt+1}次失败: {e}")
            time.sleep(2)
    return None


def main():
    # 读取缺失的 4 条消息
    target_times = {"2026-08-02 13:00:12", "2026-08-02 13:49:08", "2026-08-02 13:50:40", "2026-08-02 13:50:45"}
    msgs = []
    with open(r"C:\Users\enthalpy\WorkBuddy\Claw\notiforward\messages\2026-08-02.jsonl", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            m = json.loads(line)
            if m.get("time") in target_times:
                msgs.append(m)

    with open(r"C:\Users\enthalpy\WorkBuddy\Claw\notiforward\.analysis_cache.json", encoding="utf-8") as f:
        cache = json.load(f)
    cache_times = {r["time"] for r in cache}

    print(f"需要补分类 {len(msgs)} 条\n")
    for m in msgs:
        t = m.get("time", "")
        if t in cache_times:
            print(f"[{t}] 已在缓存中，跳过")
            continue
        title = m.get("title", "")
        text = (m.get("full_text") or m.get("text") or "")[:50]
        print(f"[{t}] {title}: {text}")
        cls = classify_with_retry(m)
        if not cls:
            print("  分类失败（重试后仍失败）")
            continue
        is_work = cls.get("is_work", False)
        importance = cls.get("importance", "low")
        needs_todo = cls.get("needs_todo", False)
        category = cls.get("category", "闲聊")
        summary = cls.get("summary", "")
        tags = []
        if is_work:
            tags.append("💼工作")
        if importance == "high":
            tags.append("🔴重要")
        elif importance == "medium":
            tags.append("🟡一般")
        if needs_todo:
            tags.append("📌待办")
        result = {
            "time": t,
            "source": m.get("title", ""),
            "text": m.get("full_text") or m.get("text") or "",
            "tags": tags,
            "importance": importance,
            "is_work": is_work,
            "needs_todo": needs_todo,
            "todo_text": cls.get("todo_text", ""),
            "category": category,
            "summary": summary,
        }
        cache.append(result)
        print(f"  → {' '.join(tags)} {category}: {summary}")
        time.sleep(1)

    with open(r"C:\Users\enthalpy\WorkBuddy\Claw\notiforward\.analysis_cache.json", "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=1)
    print(f"\n缓存更新完成，共 {len(cache)} 条")


if __name__ == "__main__":
    main()
