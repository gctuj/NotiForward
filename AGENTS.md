# AGENTS.md — 项目交接与需求说明（给 AI 助手）

> 本文档是给**另一个 AI 助手（Agent）**看的。用户让你复查或修改本仓库代码时，先完整阅读本文，再读代码。
> 它包含：用户的核心需求、系统架构、编写思路、关键设计决策、代码结构、已知边界与改进方向。

---

## 1. 项目一句话

把**手机微信通知**转发到电脑，用 **AI 自动分类**（工作/重要/待办），供用户在手机上随时向 AI 提问"今天有什么重要消息"。

- 技术路线：Android「通知使用权」（NotificationListenerService）+ 公网中转（ntfy.sh）+ PC 端 Python 脚本
- 核心理念：**免 Root、免 Hook、零封号风险**（微信无法感知），代价是只能拿到通知栏信息

## 2. 用户的核心需求（改代码前必须理解）

1. 用户是**建筑监理工程师**，工作消息来自微信群（工程芜湖项目部监理群、芜湖施工现场调度群等），想要"高效获取工作消息"
2. **怕封号**是首要约束 → 明确选择"通知转发"这个绿色方案，**不要**改成 Hook/无障碍/协议方案（那是用户否决过的方向）
3. 绿色方案的代价（只有通知栏信息、无历史/图片原图）是**已知且接受的边界**，README 已如实说明
4. 用户希望**用 AI 管理一切**：装好后在手机上问 AI（WorkBuddy/OpenClaw/Hermes 等支持 QQ/微信接入的 Agent），AI 读 `analysis/` 汇总消息
5. 用户文档风格：**平实不浮夸**（无营销腔、无 emoji 装饰、不堆徽章）；安装教程写给**第一次用的人**
6. 涉及 API 密钥的配置：**必须支持任意 OpenAI 兼容服务**（base_url/model/api_key 可配），不要默认写死 DeepSeek

## 3. 系统架构与数据流

```
手机微信通知
   │ NotificationListenerService
   ▼
NotiForward App (Android, Java) ──POST──▶ ntfy.sh（公网中转）
                                              │ 长轮询 + since=<last_id> 断点续传
                                              ▼
                                    ntfy_receiver.py（PC 接收器）
                                              │ 落盘 messages/YYYY-MM-DD.jsonl
                                              ▼
                                    classify_messages.py（AI 分类器）
                                              │ 输出 analysis/YYYY-MM-DD.md（待办/重要/工作归档）
```

- **手机端薄**：只做监听→过滤→转发（含失败队列），不存历史
- **PC 端厚**：接收、去重、落盘、AI 分类、清理、摘要
- 两端通过 **ntfy topic（频道号）** 配对，必须一致

## 4. 功能清单（已实现，全部可用）

| 功能 | 实现位置 | 说明 |
|---|---|---|
| 微信通知监听转发 | `NotificationForwardService.java` | 通知使用权，免 Root |
| 黑名单过滤 | `BlockListManager.java` + `BlockListActivity.java` | 群名/联系人包含匹配，App 内可增删，预填游戏群 |
| 发送队列重试 | `QueueManager.java` | 断网/限流时排队补发：上限 200 条、单条重试 50 次、60s 间隔 |
| 断点续传 | `ntfy_receiver.py` | SSE 长轮询 + `since=<last_id>`，重启不重复不漏收 |
| AI 分类 | `classify_messages.py` | 规则层优先（工作/游戏关键词零延迟）→ OpenAI 兼容 API；输出工作/重要/待办 |
| 时间游标进度 | `classify_messages.py` | 清理旧记录不影响后续分类（有单测） |
| 自动清理 | `cleanup_old_records.py` | 删超过保留天数（默认 7 天），**需外部定时触发** |
| 一键启动 | `collector_launcher.py` | Windows 双击启动，关窗即停（Job Object 兜底） |
| 补分类 | `fix_missing.py` | 重试分类失败的消息 |
| 摘要生成 | `summary.py` | QQ 友好格式的精简摘要 |
| 单元测试 | `tests/test_classify_progress.py` | 5 个 unittest，全绿 |

## 5. 编写思路与关键设计决策（每个都有理由）

1. **选通知方案**：对比过 无障碍（微信检测风险）/ Hook（高危），通知最安全。README《方案对比》有表
2. **黑名单而非白名单**：默认全转发，只屏蔽指定群（用户游戏群：fpsのgun king、永劫糕手）。群免打扰会导致不弹通知 = 转发不到（README《通知最大化指南》解释）
3. **队列放 App 端**：手机断网也要能补发，不能依赖 PC 在线
4. **时间游标而非条数索引**：旧版用"已分类条数"切片，清理脚本删旧文件后索引错位→新消息永不被分类（已修，有测试 `test_cleanup_does_not_break_progress`）
5. **密钥通用化**：`_cfg_val()` 环境变量→`config.local.json` 取值，支持 `api_key`/`base_url`/`model` 字段，默认 DeepSeek 只是兜底（用户明确要求）
6. **topic 两端配对**：App 首次打开自动生成 `notiforward-xxx`，PC 端 `ntfy_receiver.py` 顶部 `NTFY_TOPIC` 必须相同；改任一端都要同步另一端
7. **单实例锁**：接收器/分类器用端口绑定（8899/8897）防多开；锁 socket 引用必须保持（GC 会关掉导致锁失效）
8. **去重**：App 端 `recentKeys`（200 条滑动）；PC 端内存去重 + 启动时加载历史
9. **Windows 构建**：`build_apk.ps1` 每次构建前清理 gradle 状态目录（Windows 文件锁会导致构建失败）；**不要用 taskkill 强杀 gradle daemon**；用 PowerShell 执行

## 6. 代码结构（文件职责）

**Android（`app/src/main/java/com/enthalpy/notiforward/`）**
- `NotificationForwardService.java` — 核心：通知监听、包名过滤、黑名单过滤、构建 JSON、线程池发送、60s 队列补发定时器
- `BlockListManager.java` — 屏蔽关键词（SharedPreferences+JSON，包含匹配，预填游戏群，记录 seen_titles）
- `QueueManager.java` — 待发队列（上限 200/重试 50，flush 补发，异常条目保留不静默丢）
- `BlockListActivity.java` — 屏蔽管理界面（手输关键词 + 最近收到勾选 + 点击删除）
- `MainActivity.java` — 主界面（topic/包名/开关/屏蔽入口/待补发状态/测试按钮）
- `BootReceiver.java` — 开机自启

**PC 端（仓库根目录）**
- `ntfy_receiver.py` — 接收器（SSE 长轮询、断点续传、去重、落盘 jsonl）
- `classify_messages.py` — 分类器（规则层+AI、时间游标、--watch 监听、写 analysis/）
- `collector_launcher.py` — Windows 启动器（Job Object 管子进程，关窗即停）
- `cleanup_old_records.py` — 清理过期记录
- `fix_missing.py` — 补分类
- `summary.py` — 摘要生成
- `dedup_messages.py` / `check_state.py` / `reset_classify.py` / `rebuild_analysis.py` / `view_messages.py` / `view_important.py` — 辅助工具

**文档**：`README.md`（使用说明）、`AGENT_INSTALL.md`（给 AI 的安装引导剧本，分阶段带主人操作）、`UPLOAD.md`（GitHub 上传指南）、`CONTRIBUTING.md`、`CHANGELOG.md`、`SECURITY.md`、`LICENSE`（MIT）、`tests/`（unittest）

## 7. 开发环境与命令

```bash
# 构建 Android APK（Windows）
powershell -ExecutionPolicy Bypass -File build_apk.ps1   # 产物 Claw\NotiForward.apk

# PC 端测试（必须全绿）
python -m unittest discover -s tests -v

# 语法检查
python -m py_compile classify_messages.py ntfy_receiver.py collector_launcher.py

# 本机运行
python collector_launcher.py          # 或分别跑 ntfy_receiver.py + classify_messages.py --watch
```

## 8. 已知边界与问题（改代码时注意）

1. **通知方案固有边界**：免打扰的群不弹通知、订阅号折叠、图片只记录"[图片]"占位——README 已如实说明，属设计内，不要"修"
2. **落盘与断点原子性**（✅ 2026-08-05 已修）：`ntfy_receiver.py` 先落盘成功再推进 `last_id`，失败不推进、下轮重拉（内存 seen 去重防重复）；状态文件临时文件+原子替换；去重键含 ntfy `id`；备用文件带日期按天切换。回归测试在 `tests/test_fixes.py`
3. **PC 端配置散落**：topic/路径/端口在各脚本顶部硬编码，改动需多处同步（架构上建议集中到 config 模块，尚未做）
4. **自动清理无内置调度**：依赖外部定时任务（README 已注明）
5. **Android 无测试框架**：当前无 JUnit 依赖，队列/线程逻辑靠构建+人工验证
6. git 历史中有用户在 GitHub 网页的直接修改（commit `3f6d973`），本地与远端需先 fetch 再 push，勿强推
7. （✅ 2026-08-05 已修）`classify_messages.py`：main 与 watch 均规则层优先；缓存原子写+去重；无 time 消息不再被游标跳过；无 key 不发空认证请求；分类失败写入 `failed_classify.jsonl`
8. （✅ 2026-08-05 已修）`fix_missing.py` 通用化：优先读失败队列、兜底扫描 messages、补后自动重建 analysis；`summary.py --date/--all` 按天过滤
9. （✅ 2026-08-05 已修）Android：`QueueManager.flush` 不再持锁做网络 I/O（原主线程 ANR 隐患）；WakeLock 限时 10 分钟；去重窗口 LRU；`startForeground` try-catch；Manifest 关明文/关备份/补 FGS property；BootReceiver 改引导式

## 9. 可能的改进方向（给接手 Agent 的候选任务）

按优先级：
1. ~~**P0**：`ntfy_receiver.py` 落盘与断点推进原子化~~（✅ 已修 2026-08-05，见上）
2. **P1**：PC 端配置集中化（config.py 统一 topic/路径/端口/API 配置，各脚本引用）
3. ~~**P1**：分类失败消息自动重试~~（✅ 已修 2026-08-05：失败入 `failed_classify.jsonl`，`fix_missing.py` 通用补）
4. **P2**：Android 加 JUnit 测试（QueueManager 边界、BlockListManager 匹配逻辑）
5. **P2**：GitHub Actions CI（跑 unittest）
6. **P2**：`collector_launcher.py` 增加子进程崩溃自动拉起

## 9.5 同类轮子吸收记录（2026-08-05）

对比调研（SmsForwarder 27.4k⭐ / ItsAzni/NotificationForwarder / BennoGAP 均深入读码）后已吸收：
- **断线自动重绑**：`onListenerDisconnected` → `NotificationListenerService.requestRebind(ComponentName)`（注意：无参实例版在新 SDK 已移除，必须静态带参）
- **跳过分组汇总通知**：`FLAG_GROUP_SUMMARY`
- **黑名单正则**：`/正则/` 显式语法，非法降级去斜杠 contains + 记日志（原降级实现静默失效是 bug）
- **队列指数退避**：`60s * 2^min(retry,5)` 封顶 32 分钟，`next_retry_at` 到期才发（替代固定 60s 全量重试）；队列项用 `id`（AtomicLong）判重合并，不用时间戳（同毫秒竞态会丢消息）
- **首页状态卡**：电池优化白名单实时检测
- **规则测试器**：`test_rule.py`（粘贴样本看规则命中/分类，展示顺序与 rule_classify 优先级一致；注意 WORK_SOURCES 仅作参考提示，规则层实际不用它）
- 有意不吸收：Room/WorkManager 全套（200 条队列数据量下性能无差，DB 退避已轻量实现 90% 收益）、Cactus 强保活（违背 Play 政策）

## 10. 建议使用的技能

接手方推荐技能：`tdd`（改逻辑先写测试）、`code-review`（复查）、`diagnosing-bugs`（排查问题）、`grill-me`（需求不明确时先拷问用户）。

## 11. 敏感信息（重要）

- 密钥：只在本地 `config.local.json`（已被 .gitignore 排除），**永不入 git**；环境变量 `DEEPSEEK_API_KEY`
- 用户真实 ntfy topic、真实聊天记录在 `messages/`、`analysis/`（gitignore 排除）——不要提交、不要外泄
- git 提交用 `git -c user.name="enthalpy" -c user.email="enthalpy@users.noreply.github.com"`（匿名邮箱）

## 12. 当前状态（2026-08-05）

- ✅ 功能全部实现并部署：手机 App（v1.0.0）+ PC 收集器（本机运行中）
- ✅ GitHub 已上传：https://github.com/gctuj/NotiForward（Release v1.0.0 带 APK）
- ✅ 代码审查 + TDD 修复已完成（分类进度游标、Android 线程、队列丢消息等）
- ⏳ Gitee 镜像：仓库已导入（gctuj/NotiForward），**自动同步尚未配置**（用户手动配或接手方协助）
- 📌 下一个大目标：无（项目处于稳定使用状态；改动前先与用户确认需求）
