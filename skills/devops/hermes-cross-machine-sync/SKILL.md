---
name: hermes-cross-machine-sync
description: "通过 git 仓库将 Hermes 的 skills/memories/SOUL 在多台机器之间同步，并安全排除机密。用于用户希望通过私有 GitHub 仓库在两台电脑（例如 Windows + Mac）之间共享 skills、记忆或人物设定，或要求对 Hermes 主页目录执行 git init 的场景。"
version: 1.0.0
metadata:
  hermes:
    tags: [hermes, git, sync, secrets, gitignore, backup, multi-machine]
---

# Hermes 跨机器同步

将 Hermes 主目录中持久、由人工编写的部分纳入 git 管理，以便通过一个**私有**GitHub 仓库在多台机器之间同步（常见于 Windows ↔ Mac）。

绝对不要将 API 密钥、OAuth 令牌、账户凭证或会话数据库提交到仓库。

Hermes 主目录（Windows 上为 `~/AppData/Local/hermes`，macOS/Linux 上为 `~/.hermes`；配置文件位于 `profiles/<name>/` 下）是一个**高度包含机密**的目录。直接执行 `git init && git add .` 会把 `.env`、`auth.json` 和消息账号登录状态暴露出去。把这件事当作安全关键任务来处理。

## 该同步什么 vs. 永远不提交什么

| 同步（安全、持久） | 永远不提交（机密） | 跳过（机器本地 / 体积大） |
|----------------------|------------------------|------------------------------|
| `skills/` | `.env`, `.env.bak` | `state.db*`, `kanban.db`, `response_store.db` |
| `memories/MEMORY.md`, `memories/USER.md` | `auth.json` | `sessions/`, `logs/`, `cache/`, `*_cache/` |
| `SOUL.md` | `config.yaml` + `*.bak`（可能直接内含 api_key） | `models_dev_cache.json` |
| `.gitignore`, `README.md` | `weixin/`, `whatsapp/`, `pairing/` | `skills/**/node_modules/` |

`skills/.bundled_manifest`（打包 skill 的 name:md5 指纹）是安全的且有助于同步——它只是内容哈希，不是机密。

## 策略：白名单式 `.gitignore`（默认拒绝）

优先使用白名单策略（先 `/*`，然后用 `!` 重新包含）而不是黑名单。这样即使之后有人执行 `git add .`，机密文件仍会默认被排除。用户明确选择了这个更低风险的方案，而不是“把整个目录 git 后再黑名单排除”。

查看 `templates/gitignore-whitelist` 以获取一个已验证的示例文件。核心格式如下：

```gitignore
/*
/.*
!/skills/
!/skills/**
!/memories/
!/memories/**
!/SOUL.md
!/.gitignore
!/README.md
# 在白名单目录中重新排除：
memories/*.lock
skills/**/*.lock
skills/**/node_modules/
skills/**/_tmp_*
skills/**/_route*.js
skills/**/_route*.json
skills/**/.usage.json
skills/**/__pycache__/
skills/**/*.pyc
# 额外的机密文件名模式：
**/.env
**/*.key
**/*.pem
**/auth.json
**/credentials.json
**/secrets*.json
# 持有真实密钥的 skill 特定配置文件（按仓库发现）：
skills/amap-lbs-skill/config.json
```

## 操作步骤

1. **先盘点。** 列出主目录顶层，确认哪些机密文件真实存在，再编写 `.gitignore`。
2. **排查 skills 中藏的密钥。** 有些 skill 会携带 `config.json`，里面含真实密钥（例如 `amap-lbs-skill/config.json` → `webServiceKey`）。使用：
   `search_files(pattern='config.json', target='files', path=.../skills)`，再 grep 内容查找 `api[_-]?key|secret|token|webServiceKey|[a-f0-9]{32}`。
   将每个命中项显式加入 `.gitignore`。保留 `config.example.json`（模板）。
3. 写入白名单 `.gitignore`（从模板复制，并加入仓库特定的密钥文件）。
4. 执行 `git init -q`。
5. **提交前先做干跑验证** — 运行 `scripts/verify-staging.sh`。它会暂存所有内容，并断言不存在机密文件且没有密钥形态内容。
6. 设置本地提交身份（不要修改全局配置）：
   `git config user.name hermes-sync && git config user.email hermes-sync@localhost`
7. 提交。对 `HEAD` 重新运行内容扫描（`git grep ... HEAD`）。
8. 只有在用户提供远程仓库后再连接远程 / 推送（见注意事项）。

## 注意事项

- **`.gitignore` 不会取消已暂存的文件。** 如果你在最终确定忽略规则前已经执行了 `git add`，必须用 `git rm --cached <file>` 删除已暂存的 `_route*.js` / 临时产物。仅加入忽略规则本身不会把它们移出暂存区。
- **基于文件名的机密扫描会对模板产生误报。** 模型配置模板名如 `*config.yaml`（例如 `abliteration-config.yaml`）或文档占位符（MCP 文档中的 `ghp_xx...xxxx`、`sk-xxx...xxxx`）会触发文件名/正则扫描，但它们并不是真正的机密。始终执行内容扫描并人工确认命中项，再决定是否泄露——也在确认安全前做这一步。
- **另一台机器保留自己的机密。** 在 Mac 上 `git pull` 只会同步 skills/memories/SOUL；其本地的 `.env` / `config.yaml` 在双方均被 `.gitignore` 排除，因此不会被覆盖。要向用户强调这一点。
- **Windows 机器上通过网络访问 GitHub git 需要代理。** 直连 push/pull 会遇到 `schannel: SSL/TLS connection failed`。请使用每次命令指定代理：
  `-c http.proxy=http://127.0.0.1:7890 -c https.proxy=http://127.0.0.1:7890`
  （不要修改全局 git 配置——用户对此很坚定）。参见 `clash-proxy` skill。
- **不要替用户盲目推送。** GitHub 仓库的创建/选择应由用户自己决定。要询问用户：是否已有私有仓库 URL，还是希望 `gh repo create --private` + push，或先仅做本地同步。

## 验证

`scripts/verify-staging.sh` 是门槛：它必须在你提交或推送前输出零危险文件和零真实密钥字符串。

## 已部署实例（本用户）

- **远程私有仓库**：`https://github.com/ZQ-jhon/hermes-sync`（GitHub 账号 `ZQ-jhon`，已用 `gh` 登录，含 `repo` 权限）。
- **主机**：Windows，Hermes 主目录 `~/AppData/Local/hermes`，默认分支 `master`。
- **提交身份约定**：用户要求 commit author 署名 `Claude <claude@anthropic.com>`。提交时用
  `git -c user.name="Claude" -c user.email="claude@anthropic.com" commit --author="Claude <claude@anthropic.com>" -m "..."`。
- 首个 init 提交曾用临时身份 `hermes-sync`；之后的提交统一用 Claude。

## Mac 端首次接入（关键：不要 clone 覆盖）

Mac 上的 `~/.hermes/` 已经有自己的 `.env`/`config.yaml` 等本地机密。**绝不能** `git clone` 覆盖整个目录。正确做法是在已存在的目录里挂上 remote 再检出：

```bash
cd ~/.hermes
git init
git remote add origin https://github.com/ZQ-jhon/hermes-sync.git
git fetch origin
git checkout -f master      # 拉下 skills/memories/SOUL.md；本地 .env/config.yaml 因 .gitignore 不受影响、不会被覆盖
```

注意：Mac 端 `.gitignore` 由仓库内的版本提供（它本身被同步），所以检出后机密保护规则自动生效。Mac 直连 GitHub 通常无需代理（代理是 Windows 端特有问题）。

## 日常同步流程（建立后）

- **推送本机改动**（任意一端）：
  ```bash
  cd <hermes-home>
  git add -A
  git -c user.name="Claude" -c user.email="claude@anthropic.com" commit --author="Claude <claude@anthropic.com>" -m "sync: <描述>"
  git push        # Windows 端需临时代理，见下
  ```
- **拉取另一端改动**：`git pull --rebase`（rebase 避免无谓的 merge commit；skills/memories 很少真冲突）。
- **冲突点**：`memories/MEMORY.md`、`USER.md` 两端都会被各自的 Hermes 进程改写，最易冲突。冲突时通常**合并保留两边新增的事实**即可，不要简单丢弃一边。

## Windows 端 push/pull 的代理写法（已验证）

直连会 `schannel: SSL/TLS connection failed`。两种方式（都不污染全局配置）：

```bash
# 方式1：环境变量 + 每命令临时（推荐，gh repo create 也走得通）
export HTTPS_PROXY=http://127.0.0.1:7890 HTTP_PROXY=http://127.0.0.1:7890
git push
# 方式2：仅本次命令
git -c http.proxy=http://127.0.0.1:7890 -c https.proxy=http://127.0.0.1:7890 push
```

若曾用 `git config --local http.proxy ...` 临时设过，**用完务必 `git config --local --unset http.proxy`（及 https.proxy）清除**，避免把代理固化进 `.git/config` 污染该仓库。Clash API/端口细节见 `clash-proxy` skill。
