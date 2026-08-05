# NotiForward

把手机微信通知转发到电脑，用 AI 自动分类（工作 / 重要 / 待办）。

基于 Android 系统「通知使用权」（NotificationListenerService），免 Root、免 Hook，微信无法感知。信息只来自通知栏（不含聊天历史、图片原图）。

- License: MIT
- 平台: Android 7.0+ / Windows（PC 端纯 Python 标准库，无第三方依赖）

## 安装

- 手机端：构建 APK（见《快速开始》），或下载 Release 中的现成 APK
- PC 端：`git clone` 后直接运行
- 用 AI 帮你装：把 [AGENT_INSTALL.md](AGENT_INSTALL.md) 发给任何 AI 助手，它会照着完成全部安装配置

## 使用方式（推荐）：交给你的 AI

装好之后，你不必自己记命令、看日志。把本仓库（尤其是 [AGENT_INSTALL.md](AGENT_INSTALL.md) 和 `analysis/` 目录）交给你的 AI 助手，之后只要**在手机上问一句**：

- "今天微信有什么重要消息？" → AI 读 `analysis/` 汇总给你
- "屏蔽某个游戏群" → AI 告诉你改哪里
- "收不到消息了" → AI 按 FAQ 帮你排查

**第一步怎么交给 AI**：装好 App 后，把 App 主界面显示的**频道号**发给你的 AI（"我的频道是 notiforward-xxxxxx，帮我配好电脑端"），AI 会完成 PC 端配置，两端就连通了。

**手机上怎么问 AI**（国内主流方案）：

| 方式 | 说明 |
|---|---|
| **WorkBuddy**（腾讯桌面智能体） | 官方接入：微信（客服号直连）、企业微信、QQ、飞书、钉钉。手机发条消息即可遥控电脑上的 AI |
| **OpenClaw**（开源"小龙虾"） | MIT 开源、本地优先，支持 50+ 消息渠道：微信个人号/企业号、QQ 个人/群组、飞书、钉钉、Telegram、WhatsApp 等 |
| **Hermes Agent**（开源"爱马仕"） | Nous Research 开源（6.6 万+ star），原生支持微信（扫码直连个人微信）、QQ、飞书、钉钉、Telegram 等 14+ 平台，兼容 200+ 模型 |
| **手机 App / 小程序** | Kimi、豆包、腾讯元宝、通义、文心一言、智谱清言、DeepSeek 等，手机装 App 随时可问 |

以上 Agent 均兼容 DeepSeek 等主流模型。把 NotiForward 的文档丢给其中任何一个，它都能帮你读消息、看分类、排故障。

## 方案对比（为什么选通知转发）

| 方案 | 信息完整度 | 封号风险 | 复杂度 |
|---|---|---|---|
| 通知转发（本项目） | 仅通知栏内容 | 低 | 低 |
| 无障碍服务（Accessibility） | 聊天界面文本 | 中（微信会检测） | 中 |
| Hook / 逆向（Xposed、PC 协议） | 全量消息 | 高 | 高 |

通知方案的局限：拿不到聊天历史、图片原图、更早的消息——只有通知栏弹出的内容。见下文《通知最大化指南》尽量多拿一些。

## 特性

- 免 Root 免 Hook：只读系统通知栏接口，不碰微信进程与数据
- 黑名单过滤：按群名/联系人屏蔽（包含匹配），App 内可视化管理
- 防漏保障：前台服务保活 + WakeLock + 开机自启 + 发送队列自动重试（断网/限流时排队补发；队列上限 200 条、单条重试 50 次）
- 断点续传：PC 端长轮询 + `since=<last_id>`，重启不重复、不漏收
- AI 智能分类：规则层优先（工作/游戏关键词零延迟）→ 未命中走 DeepSeek，输出 工作/重要/待办 归档；进度用时间游标，清理旧记录不影响后续分类
- 自动清理：`cleanup_old_records.py` 删除超过保留天数的记录（默认 7 天），建议配合外部定时任务
- 一键开关（Windows）：双击启动 / 关窗即停

## 架构

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

## 目录结构

```
notiforward/
├── app/                          # Android 端（Java + XML）
│   └── src/main/java/com/enthalpy/notiforward/
│       ├── NotificationForwardService.java   # 通知监听 + 过滤 + 队列发送
│       ├── MainActivity.java                 # 主界面
│       ├── BlockListManager.java             # 黑名单过滤管理
│       ├── QueueManager.java                 # 发送队列（失败重试）
│       ├── BlockListActivity.java            # 屏蔽群管理界面
│       └── BootReceiver.java                 # 开机自启
├── ntfy_receiver.py              # PC 接收器（长轮询 + 断点续传 + 去重）
├── classify_messages.py          # AI 智能分类器（--watch 监听模式）
├── collector_launcher.py         # Windows 一键启动器（关窗即停）
├── cleanup_old_records.py        # 定期清理过期记录
├── AGENT_INSTALL.md              # 给 AI 助手的安装说明
├── tests/                        # PC 端单元测试
└── build.gradle / gradlew.bat
```

## 快速开始

### 手机端（Android 7.0+）

```powershell
# Windows 一键构建 APK（需 JDK 17 + Android SDK）
powershell -ExecutionPolicy Bypass -File build_apk.ps1
# 或用 Android Studio 打开 app/ 目录直接 Run；或下载 Release 中的现成 APK
```

首次安装与配置（按顺序）：

1. **安装 APK**：传到手机安装（QQ/微信文件助手、USB、`adb install -r` 均可）
2. **授予通知使用权**：打开 App → 点「开启通知权限」→ 系统设置中开启 NotiForward 的通知使用权（部分国产 ROM 需重启手机后生效）
3. **防后台被杀**：点「设置电池优化」加入白名单
4. **记下你的频道号**：打开 App 主界面，会看到一个**频道名（ntfy topic）**，形如 `notiforward-xxxxxx`——**这是手机和电脑之间的"门牌号"，记下来**
5. **把频道号配到电脑**（二选一）：
   - 告诉你的 AI："我的频道是 notiforward-xxxxxx，帮我配好"——AI 会改 PC 端配置
   - 或手动：编辑 `ntfy_receiver.py` 顶部 `NTFY_TOPIC = "notiforward-xxxxxx"`，保存后重启接收器
6. **验证链路**：App 点「发送测试消息」→ PC 端能收到 = 打通
7. 通知栏出现"NotiForward 运行中"常驻通知 = 服务正常

### PC 端（Windows / macOS / Linux，Python 3.10+，仅标准库）

```bash
# 1. 配置 AI Key（二选一）
export DEEPSEEK_API_KEY="your-key"        # 环境变量
# 或创建 config.local.json（不入 git）：{"deepseek_api_key": "your-key"}

# 2. 确认 topic 与 App 一致（App 主界面可查看；ntfy_receiver.py 顶部 NTFY_TOPIC 需相同）

# 3. 启动（推荐用启动器，自动拉起接收器+分类器，关窗即停）
python collector_launcher.py

# 或分开跑：
# python ntfy_receiver.py
# python classify_messages.py --watch
```

### 清理旧记录（可选）

```bash
python cleanup_old_records.py --keep-days 7 --keep-logs 5 --dry-run   # 先预览
python cleanup_old_records.py --keep-days 7 --keep-logs 5             # 实际执行
```

## 配置说明

| 配置项 | 位置 | 说明 |
|---|---|---|
| `DEEPSEEK_API_KEY` | 环境变量 / `config.local.json` | DeepSeek 密钥（AI 分类用，不入 git） |
| ntfy topic | App 主界面 ↔ `ntfy_receiver.py` 的 `NTFY_TOPIC` | 两端必须一致 |
| 屏蔽名单 | App「屏蔽群管理」 | 黑名单模式，包含匹配 |
| 包名过滤 | App 主界面 | 默认仅微信（`com.tencent.mm`） |
| 保留天数 | `cleanup_old_records.py --keep-days N` | 默认 7 天 |

## 通知最大化指南

信息只能来自通知栏，所以把"通知能显示的"调到最多：

微信内：

| 设置 | 路径 | 作用 |
|---|---|---|
| 群聊免打扰必须关 | 重要群 → `...` → 消息免打扰 → 关 | 免打扰的群不弹通知 = 转发不到（最常见漏消息原因） |
| 新消息通知全开 | 我 → 设置 → 新消息通知 | 消息、语音/视频通话邀请都打开 |
| 锁屏显示内容 | 新消息通知 → 锁屏通知 → 显示消息详情 | 选"隐藏敏感内容"会截断转发内容 |

Android 系统：

| 设置 | 路径 | 作用 |
|---|---|---|
| 允许所有通知类别 | 设置 → 应用管理 → 微信 → 通知 | 消息、群聊、音视频通话都允许 |
| 关闭"隐藏敏感通知" | 设置 → 通知与状态栏 → 锁屏通知 → 显示全部内容 | ColorOS 等默认锁屏隐藏，转发内容会变空 |

仍会漏的情况：被 @ 但群设了"仅接收不提醒"、订阅号折叠通知等——这是通知方案的固有边界。

## FAQ

**会封号吗？** 不会。只读系统通知栏接口，不碰微信进程/数据，微信无法感知。

**游戏群消息还会进来吗？** 默认屏蔽常见游戏群，App 内「屏蔽群管理」可增删。

**断网时消息会丢吗？** 不会。App 有发送队列（上限 200 条），恢复后每 60 秒自动补发，超过 50 次重试才放弃。

**清理旧记录会影响分类吗？** 不会。分类进度是时间游标（不是条数索引），有单测覆盖。

**图片/语音能转发吗？** 通知里的文字和发送者可转发；图片只记录"[图片]"占位，语音只记录时长。

**为什么收不到消息了？** ① 手机通知栏是否还有"NotiForward 运行中"（没有 → 打开 App 恢复）② PC 端接收器是否在跑 ③ 「通知使用权」是否被 ROM 重置。

## 测试

```bash
python -m unittest discover -s tests -v
```

## 安全与合规

- 仅通过系统通知接口获取消息摘要，不涉及聊天数据库、不 Hook、不逆向
- 通知内容会经第三方中转（ntfy.sh）传输，请勿转发含敏感隐私的通知；如需私密可自托管 ntfy/gotify
- 本项目的 AI 分类会把消息摘要发送给 DeepSeek API，请注意内容敏感性
- 请遵守当地法律法规及微信《用户协议》，仅用于个人消息管理，风险自负

## License

MIT
