# -*- coding: utf-8 -*-
"""
微信消息收集器 — 一键启动/停止（控制台版，v2 增加崩溃自动重启）
双击运行：打开窗口并启动 消息接收器 + 智能分类器，实时消息显示在窗口里。
关闭窗口（或按 Ctrl+C / 任务管理器结束）：自动停止接收器和分类器。

机制：
  1. 子进程共享本窗口的控制台（关闭窗口时 Windows 会广播关闭事件）
  2. 子进程挂到 Job Object（KILL_ON_JOB_CLOSE）：本进程无论以何种方式退出，
     内核都会强制结束所有子进程 —— 保证不会留下后台残留
  3. 崩溃自动重启：任一子进程退出（崩溃/被杀）会自动拉起；连续 N 次
     启动后 10 秒内又崩溃则停止重启并提示（防"疯狂重启"死循环）
"""
import ctypes
import os
import socket
import subprocess
import sys
import time
from ctypes import wintypes

BASE = r"C:\Users\enthalpy\WorkBuddy\Claw\notiforward"
PY = r"C:\Users\enthalpy\.workbuddy\binaries\python\versions\3.13.12\python.exe"
RECEIVER = os.path.join(BASE, "ntfy_receiver.py")
CLASSIFIER = os.path.join(BASE, "classify_messages.py")
PORT_RECEIVER = 8899
PORT_CLASSIFIER = 8897

# 崩溃自动重启策略：连续 MAX_RESTARTS 次在启动后 WATCH_WINDOW 秒内就退出 → 停止自动重启
MAX_CONSECUTIVE_RESTARTS = 3
RESTART_WATCH_WINDOW = 10.0
RESTART_DELAY = 3  # 秒，崩溃后等待再重启

# ---------- Job Object（KILL_ON_JOB_CLOSE 兜底） ----------
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
JobObjectExtendedLimitInformation = 9


class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class IO_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_uint64),
        ("WriteOperationCount", ctypes.c_uint64),
        ("OtherOperationCount", ctypes.c_uint64),
        ("ReadTransferCount", ctypes.c_uint64),
        ("WriteTransferCount", ctypes.c_uint64),
        ("OtherTransferCount", ctypes.c_uint64),
    ]


class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


def _kernel32(name, *argtypes):
    fn = getattr(ctypes.windll.kernel32, name)
    fn.restype = wintypes.HANDLE if name.endswith(("JobObjectW", "OpenProcess")) else wintypes.BOOL
    fn.argtypes = argtypes
    return fn


_CreateJob = _kernel32("CreateJobObjectW", wintypes.LPVOID, wintypes.LPVOID)
_SetJobInfo = _kernel32("SetInformationJobObject", wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD)
_AssignToJob = _kernel32("AssignProcessToJobObject", wintypes.HANDLE, wintypes.HANDLE)


def make_job():
    job = _CreateJob(None, None)
    if not job:
        return None
    info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    ok = _SetJobInfo(job, JobObjectExtendedLimitInformation,
                     ctypes.byref(info), ctypes.sizeof(info))
    if not ok:
        return None
    return job  # 持有引用，进程退出时句柄关闭 → 子进程被强制结束


# ---------- 工具 ----------
def port_open(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.3)
    try:
        return s.connect_ex(("127.0.0.1", port)) == 0
    finally:
        s.close()


def spawn(job, script, *args):
    """启动子进程：共享控制台（输出直接显示在本窗口）+ 挂入 Job Object"""
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    p = subprocess.Popen([PY, "-u", script, *args], cwd=BASE, env=env)
    if job:
        try:
            _AssignToJob(job, int(p._handle))
        except Exception as e:
            # 挂 Job 失败时兜底失效，必须提示（否则关闭窗口会残留子进程）
            print(f"⚠ 警告: 进程 {script} 无法挂入 Job Object（{e}），关闭窗口时可能无法自动停止")
    return p


class ManagedProc:
    """管理一个子进程：监控 + 崩溃自动重启（防"疯狂重启"死循环）。

    tick(now) 返回 (action, message)：
      'ok'       一切正常
      'restart'  已重启（message 说明原因与次数）
      'give_up'  连续崩溃已停止重启（message 说明，需人工介入）
    """

    def __init__(self, name, script, args, spawn_fn):
        self.name = name
        self.script = script
        self.args = args
        self._spawn = spawn_fn
        self.p = None
        self.started_at = None
        self.last_alive_at = None  # 最后确认存活时刻（崩溃窗口判定用，避免检测延迟误判）
        self.consec = 0
        self.disabled = False

    def start(self, now):
        """首次启动（不做崩溃计数）"""
        self.p = self._spawn(self.script, *self.args)
        self.started_at = now
        self.last_alive_at = now
        self.consec = 0

    def _exit_code(self):
        if self.p is None:
            return -1
        try:
            return self.p.poll()
        except Exception:
            return -1

    def tick(self, now):
        if self.disabled:
            return "ok", ""
        if self.p is not None and self.p.poll() is None:
            self.last_alive_at = now  # 确认存活，记录时刻
            return "ok", ""
        code = self._exit_code()
        # 快速崩溃判定：用"最后确认存活时刻 - 启动时刻"，而不是检测时刻——
        # 否则进程活了 9 秒崩、检测延迟 2 秒后才发现（now-started=11s），会被误判为稳定运行
        alive_span = 0.0
        if self.last_alive_at is not None and self.started_at is not None:
            alive_span = self.last_alive_at - self.started_at
        if alive_span < RESTART_WATCH_WINDOW:
            self.consec += 1
        else:
            self.consec = 0
        if self.consec > MAX_CONSECUTIVE_RESTARTS:
            self.disabled = True
            return "give_up", f"⚠ {self.name} 连续启动失败（exit={code}），已停止自动重启，请查看上方错误信息"
        # 立即重启（文案不再声称"X 秒后"，实际重启动作就在此刻发生）
        self.p = self._spawn(self.script, *self.args)
        self.started_at = now
        self.last_alive_at = now
        return "restart", f"⚠ {self.name} 已退出（exit={code}），已自动重启（第 {self.consec} 次）"


# ---------- 主流程 ----------
def main():
    print()
    print("=" * 62)
    print("   微信消息收集器 v2")
    print("   手机微信通知 -> ntfy.sh -> 本机接收 -> 智能分类")
    print("   (关闭本窗口即停止收集；进程崩溃会自动重启)")
    print("=" * 62)
    print()

    # 1. Python 环境校验（路径写死，变了给清晰提示而不是难懂的报错）
    if not os.path.isfile(PY):
        print(f"✗ 找不到 Python: {PY}")
        print("  请检查 collector_launcher.py 顶部的 PY 路径是否正确")
        try:
            input("按回车退出...")
        except EOFError:
            pass
        return

    # 2. 端口校验（已在运行则不重复启动）
    if port_open(PORT_RECEIVER) or port_open(PORT_CLASSIFIER):
        print("⚠ 检测到接收器/分类器已经在运行（可能是之前启动的实例）。")
        print("  如果要用本程序管理，请先停止已运行的实例，再双击本程序。")
        print("  3 秒后自动退出...")
        time.sleep(3)
        return

    job = make_job()

    # 3. 启动两个子进程并确认真的起来了
    procs = [
        ManagedProc("分类器", CLASSIFIER, ("--watch",), lambda s, *a: spawn(job, s, *a)),
        ManagedProc("接收器", RECEIVER, (), lambda s, *a: spawn(job, s, *a)),
    ]
    for mp in procs:
        print(f"[*] 正在启动 {mp.name} ...")
        mp.start(time.time())
        time.sleep(2.0)  # 给子进程一点启动时间
        if mp.p is not None and mp.p.poll() is not None:
            print(f"✗ {mp.name} 启动后立即退出（exit={mp.p.poll()}），请查看上方错误信息")
            try:
                input("按回车退出...")
            except EOFError:
                pass
            return
        print(f"  ✓ {mp.name} 已启动")

    print()
    print("✅ 已启动！下方会实时显示收到的微信消息和分类结果。")
    print("   不用时直接关闭本窗口即可全部停止。进程崩溃会自动重启（连续 3 次失败会提示）。")
    print("-" * 62)
    print()

    try:
        while True:
            any_action = False
            for mp in procs:
                action, msg = mp.tick(time.time())
                if action == "restart":
                    any_action = True
                    print(msg)
                    print("  等待子进程输出中...")
                    time.sleep(RESTART_DELAY)
                elif action == "give_up":
                    any_action = True
                    print(msg)
            # 全部放弃/禁用 → 让用户决定
            if all(mp.disabled for mp in procs):
                print("-" * 62)
                try:
                    input("按回车退出...")
                except EOFError:
                    pass
                return
            time.sleep(2)
    except KeyboardInterrupt:
        pass  # 退出；Job Object 自动清理子进程


if __name__ == "__main__":
    main()
