# 贡献指南（CONTRIBUTING.md）

感谢你对 NotiForward 感兴趣！任何形式的贡献都欢迎：提 Issue、修 bug、加功能、完善文档。

## 开发环境

| 端 | 依赖 | 说明 |
|---|---|---|
| Android | JDK 17+ / Android SDK（compileSdk 37, minSdk 24） | Gradle 9.4.1 构建 |
| PC | Python 3.10+（**仅标准库**，无第三方依赖） | 直接运行 |

## 目录速览

```
app/                     # Android 端（Java + XML）
  src/main/java/com/enthalpy/notiforward/
    NotificationForwardService.java   # 通知监听 + 过滤 + 队列发送（核心）
    BlockListManager.java             # 黑名单过滤
    QueueManager.java                 # 发送队列（失败重试）
    BlockListActivity.java            # 屏蔽管理界面
    MainActivity.java                 # 主界面
ntfy_receiver.py         # PC 接收器
classify_messages.py    # AI 分类器
tests/                  # PC 端单元测试（unittest）
```

## 构建与测试

### Android（构建 APK）

```powershell
# Windows 一键构建（自动清理 gradle 状态）
powershell -ExecutionPolicy Bypass -File build_apk.ps1
# 产物：NotiForward.apk

# 或使用 Android Studio：打开 app/ 目录 → Run
```

> ⚠️ Windows 构建注意事项：不要用 `taskkill /F` 强杀 gradle daemon（文件锁残留会导致后续构建失败）；每次构建前确保清理状态目录（脚本已内置）。

### PC 端（测试）

```bash
# 跑全部单元测试（必须，提交前）
python -m unittest discover -s tests -v

# 语法检查
python -m py_compile classify_messages.py ntfy_receiver.py collector_launcher.py
```

## 提 PR 流程

1. **先开 Issue 讨论**（功能/改动较大时），避免做无用功
2. Fork 仓库 → 新建分支（`feat/xxx` 或 `fix/xxx`）
3. 改动要求：
   - 代码风格跟随现有文件（Java 缩进 4 空格 / Python 4 空格，注释用中文或英文均可但保持一致）
   - **PC 端逻辑改动必须补单元测试**（`tests/`，unittest）
   - 改动后跑通全部测试
   - 涉及使用方式变更时同步更新 `README.md`
4. 提交信息建议格式：`feat: 描述` / `fix: 描述` / `docs: 描述` / `chore: 描述`
5. 推送分支 → 发起 Pull Request，描述清楚"改了什么、为什么、如何验证"

## 行为准则

- 保持友善、就事论事
- 本项目涉及消息转发，**任何涉及用户隐私的功能改动**需在 PR 中明确说明数据流向
- 不要提交密钥、token、真实聊天记录等敏感信息（已在 `.gitignore` 中防御，请勿强行绕过）
