# NotiForward — 微信消息自动化收集与智能分类

> 零侵入地把手机微信通知转发到电脑，用 AI 自动分类（工作 / 重要 / 待办）。

## ✨ 特性

- **零侵入、零封号风险**：仅使用 Android 系统「通知使用权」（NotificationListenerService），不 Root、不 Hook 微信进程、不读聊天数据库
- **黑名单过滤**：按群名/联系人屏蔽（包含匹配），内置游戏群屏蔽配置，App 内可视化管理
- **防漏三重保障**：前台服务保活 + WakeLock + 开机自启 + **发送队列自动重试**（断网/限流时消息排队补发；队列上限 200 条、单条重试 50 次，超过上限才放弃）
- **断点续传**：PC 端长轮询 + `since=<last_id>`，重启不重复、不漏收
- **AI 智能分类**：规则层优先（工作/游戏关键词零延迟）→ 未命中走 DeepSeek，判断是否工作 / 重要程度 / 是否待办 / 类别（工作/学校/游戏/生活）；进度用**时间游标**，清理旧记录不会导致漏分类
- **自动清理**：`cleanup_old_records.py` 删除超过保留天数的记录（默认 7 天）；**建议配合外部定时任务**（如系统计划任务）每 2 天执行一次
- **一键开关**：桌面双击启动 / 关窗即停（Windows）

## 🏗 架构

```
手机微信通知
   │  NotificationListenerService
   ▼
NotiForward App (Android)  ──POST──▶  ntfy.sh（公网中转）
                                        │  长轮询 + 断点续传
                                        ▼
                              ntfy_receiver.py（PC 接收器）
                                        │  落盘 messages/YYYY-MM-DD.jsonl
                                        ▼
                              classify_messages.py（AI 分类器）
                                        │
                                        ▼
                              analysis/YYYY-MM-DD.md（待办/重要/工作归档）
```

## 📁 目录结构

```
notiforward/
├── app/                          # Android 端（Java + XML）
│   └── src/main/java/com/enthalpy/notiforward/
│       ├── NotificationForwardService.java   # 通知监听 + 过滤 + 队列发送
│       ├── MainActivity.java                 # 主界面（屏蔽管理入口/队列状态）
│       ├── BlockListManager.java             # 黑名单过滤管理
│       ├── QueueManager.java                 # 发送队列（失败重试）
│       ├── BlockListActivity.java            # 屏蔽群管理界面
│       └── BootReceiver.java                 # 开机自启
├── ntfy_receiver.py              # PC 接收器（长轮询 + 断点续传 + 去重）
├── classify_messages.py          # AI 智能分类器（--watch 监听模式）
├── fix_missing.py                # 补分类失败的消息
├── cleanup_old_records.py        # 定期清理过期记录
├── collector_launcher.py         # Windows 一键启动器（关窗即停）
├── summary.py                    # 精简摘要生成（QQ 友好格式）
├── dedup_messages.py             # 消息去重
├── build_apk.ps1                 # Android 一键构建脚本
└── build.gradle / settings.gradle / gradlew.bat
```

## 🚀 快速开始

### 手机端（Android 7.0+）

1. 构建 APK：`powershell -ExecutionPolicy Bypass -File build_apk.ps1`（或用 Android Studio）
2. 安装并打开 App，授予「通知使用权」（设置 → 通知与状态栏 → 通知使用权 → 开启 NotiForward）
3. 建议加入「电池优化白名单」（App 内有引导按钮），防止后台被杀
4. 主界面可配置：ntfy topic、屏蔽群管理（黑名单）、发送测试消息

### PC 端（Windows / Python 3.10+，仅标准库）

```bash
# 1. 配置 AI Key（二选一）
export DEEPSEEK_API_KEY="your-key"        # 环境变量
# 或创建 config.local.json（不入 git）：
# {"deepseek_api_key": "your-key"}

# 2. 启动接收器（接收手机转发的消息）
python ntfy_receiver.py

# 3. 启动分类器（监听模式，自动用 AI 分类新消息）
python classify_messages.py --watch

# 4. Windows 懒人模式：用 collector_launcher.py（双击启动，关窗即停）
```

## ⚙️ 配置说明

| 配置项 | 位置 | 说明 |
|---|---|---|
| `DEEPSEEK_API_KEY` | 环境变量 / `config.local.json` | DeepSeek 密钥（分类用） |
| ntfy topic | App 主界面 | 默认 `notiforward-<时间戳>`，App 与 `ntfy_receiver.py` 需一致 |
| 屏蔽名单 | App「屏蔽群管理」 | 黑名单模式，包含匹配，预填游戏群 |
| 保留天数 | `cleanup_old_records.py --keep-days N` | 默认 7 天 |

## 🧪 测试

```bash
python -m unittest discover -s tests -v   # PC 端核心逻辑测试
```

当前覆盖：分类进度时间游标（清理旧记录后不漏分类）、旧版进度迁移。

## ⚠️ 安全与合规声明

- 本项目仅通过**系统通知接口**获取消息摘要，不涉及聊天数据库、不 Hook、不逆向
- 通知内容会经第三方中转服务（ntfy.sh）传输，**请勿转发含敏感隐私的通知**；如需私密可自托管 ntfy/gotify 服务端
- 请遵守当地法律法规及微信《用户协议》，本项目仅用于个人消息管理，使用风险自负
- 本项目的 AI 分类会把消息摘要发送给 DeepSeek API，同样请注意内容敏感性

## 📄 License

[MIT](LICENSE)
