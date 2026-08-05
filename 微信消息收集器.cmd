@echo off
chcp 65001 >nul
title 微信消息收集器 - 关闭窗口即停止
set PYTHONIOENCODING=utf-8
"C:\Users\enthalpy\.workbuddy\binaries\python\versions\3.13.12\python.exe" -u "C:\Users\enthalpy\WorkBuddy\Claw\notiforward\collector_launcher.py"
