# -*- coding: utf-8 -*-
"""
本次修复的回归测试：
1. 接收器断点与落盘原子性（P0）：落盘失败返回 False，调用方不推进断点
2. 去重键含 ntfy_id：同秒同内容不同 id 不再误判重复
3. save_last_id / save_cache 原子写（临时文件 + os.replace）
4. 分类器 main 与 watch 行为一致：classify_msg 规则层优先、无 key 不发 AI 请求
5. 无 time 字段的消息不被游标永久跳过
6. summary 按天过滤："今日"摘要不再混入历史
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ntfy_receiver as nf
import classify_messages as cm


class TestReceiverAtomicity(unittest.TestCase):
    """P0 回归：落盘与断点推进原子化"""

    def test_save_last_id_atomic_no_tmp_residue(self):
        with tempfile.TemporaryDirectory() as td:
            nf.STATE_FILE = Path(td) / ".last_msg_id"
            self.assertTrue(nf.save_last_id("msg-9"))
            self.assertEqual(nf.STATE_FILE.read_text(encoding="utf-8"), "msg-9")
            # 不应残留临时文件
            self.assertFalse(list(Path(td).glob("*.tmp")))

    def test_process_message_returns_false_on_disk_failure(self):
        """落盘失败（主备用都写不了）时返回 False —— 调用方据此不推进 last_id"""
        with tempfile.TemporaryDirectory() as td:
            # OUTPUT_DIR 指向不存在的子目录：主文件与备用文件都写不了
            nf.OUTPUT_DIR = Path(td) / "missing_subdir"
            data = {"app": "com.tencent.mm", "title": "t", "full_text": "f", "time": "2026-08-05 12:00:00"}
            self.assertFalse(nf.process_message(json.dumps(data), set(), "n1"))

    def test_process_message_falls_back_to_alt_file(self):
        """主文件被锁时自动切到带日期的备用文件，且返回 True"""
        with tempfile.TemporaryDirectory() as td:
            nf.OUTPUT_DIR = Path(td)
            nf._ALT_FILE = None
            today = nf.datetime.now().strftime("%Y-%m-%d")
            (Path(td) / f"{today}.jsonl").mkdir()  # 主文件路径被目录占用
            data = {"app": "com.tencent.mm", "title": "t", "full_text": "f", "time": "2026-08-05 12:00:00"}
            self.assertTrue(nf.process_message(json.dumps(data), set(), "n1"))
            # 备用文件必须带当天日期（修复：原版固定文件名跨天错乱）
            alts = [p for p in Path(td).glob(f"{today}-alt-*.jsonl")]
            self.assertEqual(len(alts), 1)
            nf._ALT_FILE = None

    def test_dedup_key_includes_ntfy_id(self):
        """同秒同内容、不同 ntfy id 是两条独立消息，不能去重"""
        a = {"ntfy_id": "id1", "time": "t", "title": "x", "full_text": "y"}
        b = {"ntfy_id": "id2", "time": "t", "title": "x", "full_text": "y"}
        self.assertNotEqual(nf.make_dedup_key(a), nf.make_dedup_key(b))
        # 无 ntfy_id 的旧记录退化为 (time,title,text)，与老行为兼容
        c = {"time": "t", "title": "x", "full_text": "y"}
        d = {"time": "t", "title": "x", "full_text": "y"}
        self.assertEqual(nf.make_dedup_key(c), nf.make_dedup_key(d))

    def test_load_seen_only_recent_days(self):
        """回归：文件名日期必须取完整 YYYY-MM-DD（原 split('-')[0] 得到 '2026'，
        与 cutoff 比较恒为 False → 去重集为 0，断点回退时全量重拉+重复落盘）"""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            nf.OUTPUT_DIR = Path(td)
            today = nf.datetime.now().strftime("%Y-%m-%d")
            old = (nf.datetime.now().date() - nf.timedelta(days=10)).isoformat()
            # 今日文件（保留期内）应被加载
            (Path(td) / f"{today}.jsonl").write_text(
                json.dumps({"ntfy_id": "n1", "app": "微信", "time": "t1",
                            "title": "x", "full_text": "y"}) + "\n", encoding="utf-8")
            # 10 天前的文件（保留期外）应被跳过
            (Path(td) / f"{old}.jsonl").write_text(
                json.dumps({"ntfy_id": "n2", "app": "微信", "time": "t2",
                            "title": "x", "full_text": "y"}) + "\n", encoding="utf-8")
            seen = nf.load_seen()
            self.assertEqual(len(seen), 1, f"应只加载今日 1 条，实际 {len(seen)}")


class TestClassifierBehavior(unittest.TestCase):
    """main 与 watch 行为一致性 + 失败兜底"""

    def test_classify_msg_rules_first(self):
        """工作关键词命中时 classify_msg 直接走规则层（与 watch 一致）"""
        msg = {"title": "监理群", "full_text": "明天基坑浇筑验收"}
        result = cm.classify_msg(msg)
        self.assertIsNotNone(result)
        self.assertTrue(result["is_work"])

    def test_classify_with_ai_no_key_no_request(self):
        """无 key 时 classify_with_ai 直接返回 None，不发空认证请求"""
        original = cm.AI_KEY
        cm.AI_KEY = ""
        try:
            self.assertIsNone(cm.classify_with_ai({"title": "t", "full_text": "f"}))
        finally:
            cm.AI_KEY = original

    def test_filter_new_keeps_msg_without_time(self):
        """无 time 字段的消息不被游标永久跳过（修复：原实现永远被漏掉）"""
        msgs = [{"time": ""}, {"time": "2026-08-05 10:00:00"}]
        new = cm.filter_new(msgs, "2026-08-05 09:00:00")
        self.assertEqual(len(new), 2)

    def test_cache_has_dedup(self):
        r1 = {"time": "t1", "source": "s", "text": "hello"}
        r2 = {"time": "t1", "source": "s", "text": "hello"}
        r3 = {"time": "t1", "source": "s", "text": "world"}
        self.assertTrue(cm._cache_has([r1], r2))
        self.assertFalse(cm._cache_has([r1], r3))

    def test_save_cache_atomic(self):
        with tempfile.TemporaryDirectory() as td:
            cm.CACHE_FILE = Path(td) / ".analysis_cache.json"
            self.assertTrue(cm.save_cache([{"a": 1}]))
            self.assertEqual(json.loads(cm.CACHE_FILE.read_text(encoding="utf-8")), [{"a": 1}])
            self.assertFalse(list(Path(td).glob("*.tmp")))


class TestSummaryByDate(unittest.TestCase):
    """summary 按天过滤：今日摘要不混入历史"""

    def _build(self):
        import summary as sm
        return sm

    def test_today_excludes_history(self):
        sm = self._build()
        cache = [
            {"time": "2026-08-05 09:00:00", "needs_todo": True, "todo_text": "交资料",
             "importance": "high", "source": "监理群", "summary": "今天要交资料"},
            {"time": "2026-08-04 18:00:00", "needs_todo": False, "todo_text": "",
             "importance": "high", "source": "施工群", "summary": "昨天验收通知"},
        ]
        orig = sm.load_cache
        sm.load_cache = lambda: cache
        try:
            out = sm.build_summary("2026-08-05")
            self.assertIn("交资料", out)
            self.assertNotIn("昨天验收通知", out)  # 历史消息不得混入"今日"
        finally:
            sm.load_cache = orig


if __name__ == "__main__":
    unittest.main()
