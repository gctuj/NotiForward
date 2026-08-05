# GitHub 上传与仓库设置指南（UPLOAD.md）

> 把 NotiForward 上传到 GitHub 的完整操作手册，从建仓库到发布 Release，照着做就行。

---

## 1️⃣ 上传（一次性操作）

### 1.1 新建 GitHub 仓库

1. 登录 [github.com](https://github.com)，点右上角 **+ → New repository**
2. 填写：
   - **Repository name**：`NotiForward`（或任意英文名）
   - **Description**：`Forward WeChat notifications to PC with AI classification (零侵入微信通知转发 + AI 分类)`
   - **Public** 或 **Private** 随你（建议 Public 开源）
   - ⚠️ **不要勾选** "Add a README / .gitignore / License"——仓库里已经有，避免冲突
3. 点 **Create repository**

### 1.2 关联并推送（在电脑上执行）

```bash
cd C:\Users\enthalpy\WorkBuddy\Claw\notiforward

# 关联远程仓库（把 <你的用户名> 换成你的 GitHub 用户名）
git remote add origin https://github.com/<你的用户名>/NotiForward.git

# 推送到 GitHub（仓库已在本地初始化并提交过）
git push -u origin master
```

> 如果提示需要登录：首次 push 会弹出 GitHub 登录（浏览器授权）或要求 Personal Access Token。
> Token 获取：GitHub → Settings → Developer settings → Personal access tokens → Generate new token，
> 勾选 `repo` 权限，生成后作为密码粘贴即可（建议用 [GitHub CLI](https://cli.github.com/)：`gh auth login` 更省事）。

### 1.3 以后每次更新

```bash
git add -A
git commit -m "说明这次改了什么"
git push
```

## 2️⃣ 上传之后要填/要做的设置

### 2.1 仓库 About 栏（右侧，必须填）

| 字段 | 建议内容 |
|---|---|
| **About 描述** | `Forward Android notifications (WeChat) to your PC with AI classification. 零侵入微信通知转发 + AI 智能分类（工作/重要/待办）。` |
| **Website** | 留空即可 |
| **Topics（标签）** | `wechat`、`notification-forwarding`、`android`、`notifications`、`ntfy`、`ai-classification`、`python`、`java`（可加 `hacktoberfest`） |

填 Topics 后仓库会更容易被搜索到。

### 2.2 分支保护（可选，多人协作时建议）

- Settings → Branches → Add rule：
  - **Branch name pattern**：`master`
  - 勾选 `Require pull request reviews before merging`、`Require status checks`（如测试）
- 单人项目可跳过。

### 2.3 Actions（CI，可选进阶）

仓库已带 `tests/` 单测，可加 GitHub Actions 自动跑测试：

```yaml
# .github/workflows/test.yml（放在仓库 .github/workflows/ 下）
name: test
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: python -m unittest discover -s tests -v
```

### 2.4 Release 发布（打完 tag 后）

```bash
git tag v1.0.0
git push origin v1.0.0
```

然后在 GitHub 仓库页面 **Releases → Create a new release**：
- Tag：`v1.0.0`
- 标题：`v1.0.0`
- 正文：复制 [CHANGELOG.md](CHANGELOG.md) 中对应版本的改动说明
- 附件（可选）：把构建好的 `NotiForward.apk` 拖进去，用户可直接下载安装

### 2.5 让 README 显示完整

推送后 GitHub 会自动渲染根目录的 `README.md`（已写好徽章、架构图、使用说明）。若显示异常：
- 检查图片链接：徽章用静态 shields.io，无需上传图片
- 检查相对链接（如 `UPLOAD.md`）：文件必须在仓库根目录且文件名一致

## 3️⃣ 仓库已有文档一览

| 文件 | 作用 |
|---|---|
| `README.md` | 主页介绍：特性、架构、快速开始、配置、FAQ |
| `UPLOAD.md` | 本文档：上传与仓库设置 |
| `CONTRIBUTING.md` | 贡献指南：如何构建、测试、提 PR |
| `CHANGELOG.md` | 版本历史 |
| `SECURITY.md` | 隐私与安全说明、密钥管理 |
| `LICENSE` | MIT 许可证 |
| `tests/` | PC 端核心逻辑单元测试 |

## 4️⃣ 常见问题

**Q：push 报错 "rejected" / "non-fast-forward"？**
远程和本地历史不一致。若远程是全新空仓库，执行 `git pull origin master --allow-unrelated-histories` 再 push；否则不要 force push。

**Q：忘了把密钥删掉就提交了？**
⚠️ 立即处理：1) 去对应平台**重置密钥**（如 DeepSeek 控制台删 key 重建）；2) 本地 `git rm --cached` 相关文件并加入 `.gitignore`；3) 重写历史（`git filter-repo`）或删仓重建。本项目已在上传前完成脱敏，密钥未进过 git。

**Q：push 后 README 徽章不显示？**
shields.io 静态徽章不需要仓库在线即可显示；若仍空白，换用 `https://img.shields.io/badge/...` 标准格式，或等待几秒刷新。
