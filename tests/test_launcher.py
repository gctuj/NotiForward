# -*- coding: utf-8 -*-
"""collector_launcher 崩溃自动重启逻辑测试"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import collector_launcher as cl


class FakeProc:
    """模拟子进程：poll() 前 die_after 次调用返回 None（存活），之后返回 exit_code（已退出）"""

    def __init__(self, exit_code=1, die_after=1):
        self._code = exit_code
        self._die_after = die_after
        self._calls = 0

    def poll(self):
        self._calls += 1
        if self._calls > self._die_after:
            return self._code
        return None


def make_manager(specs):
    """specs: 每次 spawn 的 (exit_code, die_after) 序列；返回 (manager, spawn_calls)"""
    calls = []
    it = iter(specs)

    def fake_spawn(script, *args):
        try:
            code, die_after = next(it)
        except StopIteration:
            code, die_after = 0, 999999  # 默认：存活
        calls.append((script, args))
        return FakeProc(code, die_after)

    m = cl.ManagedProc("测试进程", "x.py", ("--watch",), fake_spawn)
    return m, calls


class TestManagedProcRestart(unittest.TestCase):
    """崩溃自动重启 + 防疯狂重启"""

    def test_alive_process_no_action(self):
        m, _ = make_manager([(0, 999999)])
        m.start(0)
        action, _ = m.tick(100)
        self.assertEqual(action, "ok")
        self.assertEqual(m.last_alive_at, 100)

    def test_stable_run_crash_resets_counter(self):
        """稳定运行超过窗口期后崩溃 → 重启且连续计数重置（不算连续失败）"""
        # 首启存活到第 11 次 poll（die_after=11 → poll1..11 活，poll12 死）
        m, calls = make_manager([(1, 11), (0, 999999)])
        m.start(0)
        for t in range(1, 12):
            self.assertEqual(m.tick(float(t))[0], "ok")  # 存活到 t=11
        # t=12 崩溃：last_alive=11, started=0 → 存活时长 11s >= 窗口 10s → 重置
        action, msg = m.tick(12.0)
        self.assertEqual(action, "restart")
        self.assertIn("已退出", msg)
        self.assertEqual(len(calls), 2)
        self.assertEqual(m.consec, 0)

    def test_quick_crash_counts_consecutive_then_gives_up(self):
        """10s 窗口内反复崩溃 → 连续计数累加，超过 MAX(3) 后放弃"""
        m, calls = make_manager([(1, 1), (1, 0), (1, 0), (1, 0)])
        m.start(0)
        self.assertEqual(m.tick(1)[0], "ok")        # 首启存活（last_alive=1）
        self.assertEqual(m.tick(2)[0], "restart")   # 崩, span=1-0<10 → consec=1
        self.assertEqual(m.consec, 1)
        self.assertEqual(m.tick(3)[0], "restart")   # 又崩, consec=2
        self.assertEqual(m.consec, 2)
        self.assertEqual(m.tick(4)[0], "restart")   # 又崩, consec=3
        self.assertEqual(m.tick(5)[0], "give_up")   # consec=4 > MAX(3)
        self.assertTrue(m.disabled)
        self.assertEqual(len(calls), 4)             # 首启 + 3 次重启

    def test_first_launch_immediate_crash_counts(self):
        """首启就崩溃（无存活记录）也应计入连续失败，并自动重启"""
        m, calls = make_manager([(1, 0), (1, 0), (1, 0), (1, 0)])
        m.start(0)
        self.assertEqual(m.tick(1)[0], "restart")   # 首启即崩, consec=1
        self.assertEqual(m.consec, 1)
        self.assertEqual(m.tick(2)[0], "restart")   # consec=2
        self.assertEqual(m.tick(3)[0], "restart")   # consec=3
        self.assertEqual(m.tick(4)[0], "give_up")   # consec=4 → 放弃
        self.assertTrue(m.disabled)

    def test_disabled_returns_ok(self):
        m, _ = make_manager([(1, 0), (1, 0), (1, 0), (1, 0)])
        m.start(0)
        for t in range(1, 8):
            m.tick(float(t))
        self.assertTrue(m.disabled)
        action, _ = m.tick(99)
        self.assertEqual(action, "ok")              # disabled 后不再动作


if __name__ == "__main__":
    unittest.main()
