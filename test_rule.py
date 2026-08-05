# -*- coding: utf-8 -*-
"""NotiForward 规则测试器（吸收自 SmsForwarder 的规则测试器交互）

粘贴/输入一条通知样本，立即看到：
1. 规则层逐条命中情况（工作来源/工作关键词/游戏群/闲聊特征，命中哪一条）
2. 最终分类结果（规则命中则不调 AI；否则调 AI）

用法:
  python test_rule.py --title "工程芜湖项目部监理群" --text "明天基坑浇筑验收，请各班组到场"
  python test_rule.py                    # 交互模式，依次输入标题、内容
  python test_rule.py --title "..." --text "..." --no-ai   # 只看规则层，不调 AI
"""
import argparse
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import classify_messages as cm


def check_rules(msg):
    """逐条说明规则层命中情况，顺序与 rule_classify 真实优先级一致：
    ① 闲聊特征（短文本）→ ② 游戏群（除非含工作关键词）→ ③ 工作关键词。
    返回 (是否被规则层直接分类, 命中描述)"""
    title = (msg.get("title") or "").strip()
    text = (msg.get("full_text") or msg.get("text") or msg.get("raw") or "").strip()
    hits = []

    # ① 闲聊特征（rule_classify 最高优先级，仅短文本）
    chat = [p for p in cm.CHAT_PATTERNS if p in text and len(text) <= 8]
    if chat:
        hits.append(f"[优先级1] 闲聊特征命中: {chat}（短文本，直接归闲聊）")

    # ② 游戏群（内容不含工作关键词才命中）
    gs = [g for g in cm.GAME_SOURCES if g in title]
    if gs:
        wk = [k for k in cm.WORK_KEYWORDS if k in text]
        if wk:
            hits.append(f"[优先级2] 游戏群命中但内容含工作关键词 {wk}（放行给后续判断）")
        else:
            hits.append(f"[优先级2] 游戏群命中: {gs}（直接归游戏）")

    # ③ 工作关键词
    wk = [k for k in cm.WORK_KEYWORDS if k in text]
    if wk:
        hits.append(f"[优先级3] 工作关键词命中: {wk}（直接归工作）")

    # 工作来源仅作参考（rule_classify 不直接用它，交给 AI 判断避免误伤生活闲聊）
    ws = [s for s in cm.WORK_SOURCES if s in title]
    if ws:
        hits.append(f"工作来源命中: {ws}（仅供参考，规则层不直接分类，走 AI 判断）")

    if not hits:
        return False, "未命中任何规则层条件，将走 AI"
    return True, "；".join(hits)


def main():
    ap = argparse.ArgumentParser(description="NotiForward 分类规则测试器")
    ap.add_argument("--title", default="", help="消息来源（群名/联系人）")
    ap.add_argument("--text", default="", help="消息内容")
    ap.add_argument("--no-ai", action="store_true", help="只看规则层，不调 AI")
    args = ap.parse_args()

    title = args.title.strip()
    text = args.text.strip()

    if not title and not text:
        print("=== NotiForward 规则测试器（输入 Ctrl+C 退出）===\n")
        try:
            title = input("消息来源（群名/联系人）: ").strip()
            text = input("消息内容: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n已退出")
            return
        print()

    if not title and not text:
        print("标题和内容都为空，无法测试")
        return

    msg = {"title": title, "full_text": text}
    print(f"样本: [{title}] {text[:60]}")
    print("-" * 50)

    hit, desc = check_rules(msg)
    print(f"规则层: {desc}")

    if hit:
        result = cm.rule_classify(msg)
        if result:
            print(f"→ 规则层直接分类（不调 AI）: {'💼' if result['is_work'] else ''}"
                  f"{'🔴' if result['importance']=='high' else ''}"
                  f"{'📌' if result['needs_todo'] else ''} "
                  f"category={result['category']}, importance={result['importance']}, summary={result['summary']}")
            return
        print("→ 命中特征但 rule_classify 返回 None（进入 AI 判断）")

    if args.no_ai:
        print("(--no-ai) 未调 AI，测试结束")
        return

    if not cm.AI_KEY:
        print("⚠ 未配置 API Key，无法调 AI 分类（规则层已展示）")
        return

    print("调 AI 分类中...")
    cls = cm.classify_with_ai(msg)
    if cls:
        result = cm.format_result(msg, cls)
        print(f"→ AI 分类: {'💼' if result['is_work'] else ''}"
              f"{'🔴' if result['importance']=='high' else ''}"
              f"{'📌' if result['needs_todo'] else ''} "
              f"category={result['category']}, importance={result['importance']}, summary={result['summary']}")
    else:
        print("→ AI 分类失败")


if __name__ == "__main__":
    main()
