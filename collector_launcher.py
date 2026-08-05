# -*- coding: utf-8 -*-
"""
微信消息收集器 — 一键启动/停止（控制台版）
双击运行：打开窗口并启动 消息接收器 + 智能分类器，实时消息显示在窗口里。
关闭窗口（或按 Ctrl+C / 任务管理器结束）：自动停止接收器和分类器。

机制：
  1. 子进程共享本窗口的控制台（关闭窗口时 Windows 会广播关闭事件）
  2. 子进程挂到 Job Object（KILL_ON_JOB_CLOSE）：本进程无论以何种方式退出，
     内核都会强制结束所有子进程 —— 保证不会留下后台残留
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


# ---------- 主流程 ----------
def main():
    print()
    print("=" * 62)
    print("   微信消息收集器")
    print("   手机微信通知 -> ntfy.sh -> 本机接收 -> 智能分类")
    print("   (关闭本窗口即停止收集)")
    print("=" * 62)
    print()

    if port_open(PORT_RECEIVER) or port_open(PORT_CLASSIFIER):
        print("⚠ 检测到接收器/分类器已经在运行（可能是开机自启的实例）。")
        print("  如果要用本程序管理，请先停止已运行的实例，再双击本程序。")
        print("  3 秒后自动退出...")
        time.sleep(3)
        return

    job = make_job()

    print("[1/2] 正在启动 智能分类器 ...")
    c1 = spawn(job, CLASSIFIER, "--watch")
    time.sleep(1.5)

    print("[2/2] 正在启动 消息接收器 ...")
    c2 = spawn(job, RECEIVER)
    time.sleep(1.5)

    print()
    print("✅ 已启动！下方会实时显示收到的微信消息和分类结果。")
    print("   不用时直接关闭本窗口即可全部停止。")
    print("-" * 62)
    print()

    try:
        while True:
            if c1.poll() is not None and c2.poll() is not None:
                print()
                print("⚠ 接收器和分类器都已退出（可能出错），窗口将保持打开。")
                print("  请查看上方错误信息，或关闭窗口后重新双击启动。")
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
