# NotiForward — 微信消息自动化收集与智能分类

> 零侵入地把手机微信通知转发到电脑，用 AI 自动分类（工作 / 重要 / 待办）。

<div align="center">

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Platform](https://img.shields.io/badge/platform-Android%207%2B%20%7C%20Windows-lightgrey.svg)
![Android](https://img.shields.io/badge/Android-Java%20%2B%20XML-green.svg)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB.svg)
![Status](https://img.shields.io/badge/status-stable-brightgreen.svg)

</div>

## 📚 文档导航

| 文档 | 说明 |
|---|---|
| [UPLOAD.md](UPLOAD.md) | **GitHub 上传完整指南**（建仓、推送、仓库设置） |
| [CONTRIBUTING.md](CONTRIBUTING.md) | 贡献指南（构建、测试、提 PR） |
| [CHANGELOG.md](CHANGELOG.md) | 版本更新日志 |
| [SECURITY.md](SECURITY.md) | 隐私与安全说明 |

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

**方式 A：直接构建 APK（推荐）**
```powershell
# Windows：一键构建（自动清理 gradle 状态）
powershell -ExecutionPolicy Bypass -File build_apk.ps1
# 产物：Claw\NotiForward.apk（脚本内置输出路径，可自行修改）
```

**方式 B：Android Studio 打开 `app/` 目录直接 Run**

**安装与授权（重要，按顺序）**
1. 把 APK 传到手机（QQ/微信文件助手、USB 或 `adb install -r`）并安装
   - ⚠️ **升级请选"覆盖安装"，不要卸载重装**——卸载会清空 App 配置（ntfy topic 会变，需要重新同步 PC 端）
2. 打开 App，点「开启通知权限」→ 系统设置里授予 NotiForward「通知使用权」
   - 部分国产 ROM（ColorOS/OriginOS 等）需**重启手机后**才生效
3. 点「设置电池优化」加入白名单，防止后台被杀（保活关键）
4. 建议确认：通知栏出现"NotiForward 运行中"常驻通知 = 正常工作
5. 点「发送测试消息」，PC 端能收到即链路打通

### PC 端（Windows / macOS / Linux，Python 3.10+，仅标准库）

```bash
# 1. 配置 AI Key（二选一）
export DEEPSEEK_API_KEY="your-key"        # 环境变量
# 或创建 config.local.json（不入 git）：
# {"deepseek_api_key": "your-key"}

# 2. 确认 topic 与 App 一致（App 主界面可查看）
#    ntfy_receiver.py 顶部 NTFY_TOPIC 需与 App 相同

# 3. 启动接收器（接收手机转发的消息）
python ntfy_receiver.py

# 4. 启动分类器（监听模式，自动用 AI 分类新消息）
python classify_messages.py --watch

# 5. Windows 懒人模式：用 collector_launcher.py
python collector_launcher.py   # 双击启动，关窗即停，自动拉起接收器+分类器
```

### 清理旧记录（可选）

```bash
# 手动清理：删除超过 7 天的记录
python cleanup_old_records.py --keep-days 7 --keep-logs 5 --dry-run   # 先预览
python cleanup_old_records.py --keep-days 7 --keep-logs 5             # 实际执行

# 建议用系统计划任务每 2 天执行一次（脚本本身不带调度）
```

## ⚙️ 配置说明

| 配置项 | 位置 | 说明 |
|---|---|---|
| `DEEPSEEK_API_KEY` | 环境变量 / `config.local.json` | DeepSeek 密钥（AI 分类用，**不入 git**） |
| ntfy topic | App 主界面 ↔ `ntfy_receiver.py` 的 `NTFY_TOPIC` | **两端必须一致**，改任一端都要同步另一端 |
| 屏蔽名单 | App「屏蔽群管理」 | 黑名单模式，包含匹配；预填游戏群，可增删 |
| 包名过滤 | App 主界面 | 默认仅微信（`com.tencent.mm`），可扩展其他 App |
| 队列参数 | `QueueManager.java` 常量 | 上限 200 条、单条重试 50 次、补发间隔 60 秒 |
| 保留天数 | `cleanup_old_records.py --keep-days N` | 默认 7 天 |

## ❓ FAQ

**Q：会封号吗？**
不会。只读系统通知栏接口，不碰微信进程/数据，微信无法感知。这也是选通知方案而非 Hook 的原因。

**Q：游戏群消息还会进来吗？**
默认已屏蔽常见游戏群（`fpsのgun king`、`永劫糕手`）。App 内「屏蔽群管理」可随时增删，支持关键词模糊匹配。

**Q：断网时消息会丢吗？**
不会。App 有发送队列（上限 200 条），断网/限流时排队，恢复后每 60 秒自动补发，超过 50 次重试才放弃。

**Q：清理脚本删了旧记录，分类器会乱吗？**
不会。分类进度是**时间游标**（不是条数索引），清理不会影响后续分类（有单测覆盖）。

**Q：图片/语音能转发吗？**
通知里的文字和发送者可转发；图片目前只记录"[图片]"占位（通知缩略图未提取），语音只记录时长。

**Q：为什么收不到消息了？**
① 手机通知栏是否还有"NotiForward 运行中"？没有 → 打开 App 恢复（后台被杀是常见原因）
② PC 端接收器是否开着？（`python ntfy_receiver.py` 或启动器窗口）
③ 手机「通知使用权」是否还在？部分 ROM 重启后会被重置

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
