# hermes-sync

通过私有 GitHub 仓库，在多台机器之间同步 [Hermes Agent](https://github.com/NousResearch/hermes-agent) 的持久化内容（**Windows ↔ Mac**）。

## 同步什么

| 已同步 | 永不提交（机密） |
|--------|------------------|
| `skills/` — 技能库 | `.env` / `auth.json` / `config.yaml` |
| `memories/` — 记忆 / 长期记忆 | 消息平台账号登录态（weixin / whatsapp …） |
| `SOUL.md` — 人格设定 | `state.db` 等会话数据库 |

采用**白名单式 `.gitignore`**（默认忽略一切，只放行安全项），即使误执行 `git add .` 也不会泄露密钥。

## 在新机器上接入

> ⚠️ 不要 `git clone` 覆盖本机的 `~/.hermes`（会冲掉本地 `.env`/`config.yaml`）。在已存在的目录里挂 remote 再检出：

```bash
cd ~/.hermes            # Windows 为 ~/AppData/Local/hermes
git init
git remote add origin https://github.com/ZQ-jhon/hermes-sync.git
git fetch origin
git checkout -f master  # 本地 .env / config.yaml 受 .gitignore 保护，不会被覆盖
```

## 日常同步

```bash
git add -A && git commit -m "sync: ..." && git push   # 本机改动推上去
git pull --rebase                                      # 拉取另一台的改动
```

> Windows 端访问 GitHub 需走本地代理：`-c http.proxy=http://127.0.0.1:7890`（仅当次命令生效，不改全局配置）。
