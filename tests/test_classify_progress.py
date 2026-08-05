# -*- coding: utf-8 -*-
"""
Seam 1 测试：分类进度游标化
背景：.classified_count 原用"已分类条数"做列表索引，清理脚本删除旧消息文件后
索引错位，新消息被跳过（永远不分类）。本测试验证改为"时间游标"后行为正确。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import classify_messages as cm


class TestFilterNew(unittest.TestCase):
    """按时间游标筛选新消息"""

    def test_newer_messages_are_selected(self):
        all_msgs = [
            {"time": "2026-08-01 09:00:00", "title": "a"},
            {"time": "2026-08-01 10:00:00", "title": "b"},
            {"time": "2026-08-05 09:00:00", "title": "c"},
        ]
        new = cm.filter_new(all_msgs, "2026-08-01 10:00:00")
        self.assertEqual([m["title"] for m in new], ["c"])

    def test_empty_cursor_returns_all(self):
        all_msgs = [{"time": "2026-08-05 09:00:00", "title": "x"}]
        self.assertEqual(len(cm.filter_new(all_msgs, "")), 1)

    def test_cleanup_does_not_break_progress(self):
        """核心回归：清理删除旧文件后，剩余消息仍能按时间游标识别为新消息
        （旧实现 all_msgs[N:] 在此场景返回空列表，导致漏分类）"""
        remaining = [
            {"time": "2026-08-05 09:00:00", "title": "n1"},
            {"time": "2026-08-05 10:00:00", "title": "n2"},
        ]
        new = cm.filter_new(remaining, "2026-08-01 10:00:00")
        self.assertEqual(len(new), 2)


class TestCursorMigration(unittest.TestCase):
    """旧版数字条数进度 → 时间游标迁移"""

    def test_migrate_from_cache_max_time(self):
        cache = [
            {"time": "2026-08-01 09:00:00", "is_work": True},
            {"time": "2026-08-01 10:00:00", "is_work": False},
        ]
        self.assertEqual(cm.migrate_cursor_from_cache(cache), "2026-08-01 10:00:00")

    def test_migrate_empty_cache(self):
        self.assertEqual(cm.migrate_cursor_from_cache([]), "")


if __name__ == "__main__":
    unittest.main()
