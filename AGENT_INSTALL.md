# AGENT_INSTALL.md — 安装说明（给 AI 助手看）

> 本文件写给任何 AI 助手（Agent）。用户把这份文档丢给你，就是让你**照着把 NotiForward 装好并跑通**。
> 你可以直接执行下面的命令；遇到"需要用户决定"的步骤，向用户确认即可。

## 项目是什么

NotiForward = Android App（监听微信通知转发到 ntfy.sh）+ PC 端脚本（接收 + AI 分类）。
目标机器：一台 Windows 电脑（跑接收/分类）+ 一台 Android 手机（转发通知）。

## 0. 前置检查

```bash
python --version        # 需要 3.10+（本仓库 PC 端仅用标准库，无 pip 依赖）
```

Windows 用户如果没装 Python：https://www.python.org/downloads/ 装 3.10+，安装时勾选 "Add to PATH"。

## 1. 获取代码

```bash
git clone https://github.com/gctuj/NotiForward.git
cd NotiForward
```

（没有 git 就下载 ZIP 解压：仓库页面 → Code → Download ZIP）

## 2. 配置 AI Key（分类用，必配否则分类器会警告但不影响接收）

二选一：

```bash
# 方式 A：环境变量
export DEEPSEEK_API_KEY="用户提供的 key"     # Windows: set DEEPSEEK_API_KEY=...

# 方式 B：本地配置文件（推荐，Windows 友好）
# 在项目根目录创建 config.local.json：
# {"deepseek_api_key": "用户提供的 key"}
```

> ⚠️ `config.local.json` 已在 .gitignore 中，不会上传。key 向用户索取（DeepSeek 开放平台申请）。

## 3. 启动 PC 端（接收器 + 分类器）

```bash
# 方式 A（推荐，Windows）：一键启动器，关窗即停
python collector_launcher.py

# 方式 B：分开跑（更直观）
python ntfy_receiver.py          # 终端 1：接收器（长轮询，断点续传）
python classify_messages.py --watch   # 终端 2：分类器（监听新消息自动分类）
```

验证：终端出现 `轮询 ntfy.sh (since=...)` 即接收器正常；`智能分类监听启动` 即分类器正常。

> ⚠️ 接收器/分类器都有单实例锁（端口 8899/8897），重复启动会被拒绝——这是正常的。
> Windows 中文乱码时：`set PYTHONIOENCODING=utf-8` 后再运行。

## 4. 手机端 App

### 4.1 获取 APK

```bash
# 方式 A：项目内一键构建（Windows，需要 JDK 17 + Android SDK）
powershell -ExecutionPolicy Bypass -File build_apk.ps1
# 产物在脚本配置的输出路径（默认 Claw\NotiForward.apk）

# 方式 B：Android Studio 打开 app/ 目录 Run
# 方式 C：如果仓库有 Release，直接下载现成 APK
```

### 4.2 安装与授权（必须按顺序）

1. APK 传到手机安装（QQ/微信文件助手、USB、或 `adb install -r`）
   - ⚠️ 升级请**覆盖安装**，不要卸载重装（卸载会清掉 ntfy topic 配置）
2. 打开 App → 点「开启通知权限」→ 系统设置授予 NotiForward「通知使用权」
   - 部分国产 ROM（ColorOS/OriginOS）需**重启手机**才生效
3. 点「设置电池优化」加入白名单（防后台被杀，否则收不到）
4. 通知栏出现"NotiForward 运行中"常驻通知 = 服务活着

### 4.3 topic 同步（关键，App 与 PC 必须一致）

- App 主界面可查看当前 topic（形如 `notiforward-xxx`）
- PC 端 `ntfy_receiver.py` 顶部的 `NTFY_TOPIC` 必须与 App 相同
- 不一致时：改 `ntfy_receiver.py` 后重启接收器（Agent 确认两端一致即可）

## 5. 端到端验证

1. 手机 App 点「发送测试消息」→ PC 接收器终端应打印该消息（测试消息不落盘，只打印）
2. 手机微信收到一条真实通知 → PC 端 `messages/YYYY-MM-DD.jsonl` 出现新记录、`analysis/YYYY-MM-DD.md` 更新
3. 全部通过 = 安装完成 ✅

## 6. 常见问题（Agent 排查用）

| 症状 | 排查 |
|---|---|
| 手机收不到/PC 没消息 | ① 通知栏有无"NotiForward 运行中"（无=后台被杀，打开 App 恢复）② PC 接收器是否在跑 ③ 通知使用权是否被 ROM 重置 |
| 接收器反复"连接断开" | 网络问题，10 秒后自动重连，无需处理 |
| "被限流，60秒后重试" | ntfy.sh 免费版 429，约 1 小时自动解除 |
| 分类器报"未配置 API Key" | 见第 2 步配置 DEEPSEEK_API_KEY |
| 中文乱码 | Windows：`set PYTHONIOENCODING=utf-8` |

## 7. 定期维护（可选）

```bash
# 清理超过 7 天的记录（建议配合系统计划任务每 2 天跑一次）
python cleanup_old_records.py --keep-days 7 --keep-logs 5
```
