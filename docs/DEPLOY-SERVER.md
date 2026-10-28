# 远程服务器部署指南（fork 版）

本文档描述将 **zjing123/ai-goofish-monitor**（含本地定制的 fork）部署到远程服务器的完整流程。
定制内容：国内镜像源构建、DeepSeek/Qwen3 禁用思考模式兼容、AI 前置黑名单（任务级 + 全局）。

## 架构

```
浏览器/手机 ──HTTPS──▶ Caddy (basic_auth + 自动证书)
                          │ reverse_proxy
                          ▼
                    127.0.0.1:8000（仅本机回环）
                          │ docker port mapping
                          ▼
                    ai-goofish-monitor 容器（本地构建镜像）
                          │
                          ▼
                    闲鱼 / DeepSeek API / WxPusher（出站）
```

安全边界：`/api/*` 后端本身无鉴权（上游 issue #491），全部依赖 Caddy 的 basic_auth 挡在前面。
**容器端口必须保持 `127.0.0.1:8000:8000` 绑定，绝不能改成 `0.0.0.0`，否则可绕过 Caddy 直连。**

## 一、前置条件

- 服务器已安装 Docker + Docker Compose v2（`docker compose version` 可用）
- 服务器已有 Caddy 并正常运行（本文不覆盖 Caddy 安装）
- 一个解析到服务器的域名（用于自动 HTTPS）
- SSH 可用密钥登录（禁用密码登录）

## 二、获取代码

```bash
cd /opt            # 或你的常用目录
sudo git clone https://github.com/zjing123/ai-goofish-monitor.git
cd ai-goofish-monitor
```

> ⚠️ **必须使用 `docker-compose.dev.yaml`**（本地构建）。
> 默认的 `docker-compose.yaml` 拉取官方 ghcr 镜像，**不包含** DeepSeek 兼容和黑名单等定制功能。

## 三、配置 .env

```bash
cp .env.example .env
chmod 600 .env
vim .env
```

最小必改项：

```ini
# ---- AI（DeepSeek 多模态）----
OPENAI_API_KEY=sk-你自己的key        # 萌主自行填写，勿提交进仓库
OPENAI_BASE_URL=https://api.deepseek.com
OPENAI_MODEL_NAME=deepseek-flash
ENABLE_THINKING=true                  # 保持 true：触发"禁用思考"参数，勿改

# ---- Web 登录（第二道门，Caddy 是第一道）----
WEB_USERNAME=admin
WEB_PASSWORD=请换成强密码

# ---- 微信推送（WxPusher，走通用 Webhook 渠道）----
WEBHOOK_URL=https://wxpusher.zjiecode.com/api/send/message
WEBHOOK_METHOD=POST
WEBHOOK_CONTENT_TYPE=JSON
WEBHOOK_BODY={"appToken":"AT_xxx","content":"${content}","summary":"${title}","contentType":1,"uids":["UID_xxx"]}
```

> WEBHOOK_BODY 里换成自己的 WxPusher appToken/UID；也可部署后在
> 系统设置 → 通知推送 → Webhook 页面里图形化配置并测试。

全局黑名单关键词 `TITLE_BLACKLIST_KEYWORDS` 建议部署后在
**系统设置 → 黑名单规则** 页面维护（JSON 格式自动存储，支持 `re:` 正则）。

## 四、迁移本地数据（可选，推荐）

把本地已跑通的数据拷过去，任务/结果/黑名单/登录态直接继承。

数据位置对照：

| 目录/文件 | 内容 | 是否必须 |
|---|---|---|
| `data/app.sqlite3` | 任务、抓取结果、全局/结果黑名单 | ✅ |
| `prompts/*_criteria.txt` | 任务引用的 AI 分析标准 | ✅（缺了任务会跳过 AI 分析）|
| `state/XY_*.json` | 闲鱼登录态（cookies） | ✅（在 `state/` 目录，非根目录）|
| `jsonl/`、`price_history/` | 旧版结果/价格快照 | 通常为空，可不迁 |

> ⚠️ SQLite 为 WAL 模式，**两侧容器都要先停**再拷贝，避免热拷贝丢数据或拷到写一半的文件。
> ⚠️ 同步会**覆盖服务器上同名数据**（若服务器上已建过任务会丢失）。
> ⚠️ 同一闲鱼登录态不要两台机器同时跑任务（风控/互踢风险）。同步后建议本地保持停止，以服务器为唯一数据源。

```bash
SERVER=user@your-server
DIR=/opt/ai-goofish-monitor          # 服务器上仓库路径

# 1) 两侧停容器，保证 SQLite 一致性
docker compose -f docker-compose.dev.yaml stop app
ssh $SERVER "cd $DIR && docker compose -f docker-compose.dev.yaml stop app"

# 2) 同步（rsync 为例；无 rsync 用 scp -r）
rsync -av data/    $SERVER:$DIR/data/
rsync -av prompts/ $SERVER:$DIR/prompts/
rsync -av state/   $SERVER:$DIR/state/

# 3) 服务器启动并验证
ssh $SERVER "cd $DIR && docker compose -f docker-compose.dev.yaml up -d"
# 验证：Web UI 任务列表、结果页历史条数、系统设置→黑名单规则、账号管理里的登录态

# 4) 本地容器保持停止（避免双跑）；确需本地再跑：docker compose -f docker-compose.dev.yaml start app
```

`.env` **不迁移**（服务器已按第三章配置好）。

不迁移也可以：部署后在 Web UI 重新创建任务、重新上传登录态。

## 五、构建并启动

```bash
docker compose -f docker-compose.dev.yaml build app     # 首次约 3~10 分钟
docker compose -f docker-compose.dev.yaml up -d
curl -s http://127.0.0.1:8000/health                    # 应返回 healthy
```

## 六、配置 Caddy

编辑服务器上的 Caddyfile（通常在 `/etc/caddy/Caddyfile`），追加站点：

```caddyfile
monitor.example.com {
    basic_auth {            # Caddy < 2.7 指令名为 basicauth
        admin $2a$14$xxxx   # caddy hash-password 生成，替换为你的哈希
    }
    reverse_proxy 127.0.0.1:8000
}
```

重载：

```bash
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

验证鉴权生效：

```bash
curl -s https://monitor.example.com/health        # 应返回 401
curl -s -u admin:密码 https://monitor.example.com/health   # 应返回 healthy
```

说明：
- WebSocket（`/ws` 实时日志）由 Caddy 原生支持，无需额外配置
- 前端 API 全部为同源相对路径，浏览器 Basic Auth 凭据自动携带，接口调用不受影响

## 七、首次上线检查清单

- [ ] `curl http://127.0.0.1:8000/health` 服务器本机返回 healthy
- [ ] `curl https://域名/health` 未带凭据返回 401
- [ ] Web UI 能登录，任务列表完整（如迁移了 data/）
- [ ] 系统设置 → 通知推送 → 测试，微信收到消息
- [ ] 手动启动一次任务，结果页出现商品、日志无 AI 解析报错
- [ ] 触发一次黑名单商品，结果中出现"命中黑名单关键词，跳过分析"

## 八、安全加固

```bash
# .env 与登录态文件收紧权限
chmod 600 .env xianyu_state.json

# 防火墙：只开 SSH + 443（80 仅限 Caddy 申请证书时用）
sudo ufw allow 22/tcp && sudo ufw allow 80,443/tcp && sudo ufw enable
sudo ufw status   # 确认没有 8000
```

- SSH：`PasswordAuthentication no`，仅密钥登录
- 定期检查 `docker logs ai-goofish-monitor-app` 有无异常外联

## 九、日常运维

### 更新（上游有新版本时）

```bash
# 1. 本地开发机：合并上游，推送 fork
git fetch upstream
git merge upstream/master        # 冲突时手动解决后 commit
git push origin master

# 2. 服务器：拉取并重建
cd /opt/ai-goofish-monitor
git pull origin master
docker compose -f docker-compose.dev.yaml build app
docker compose -f docker-compose.dev.yaml up -d --renew-anon-volumes
```

> `--renew-anon-volumes` 必带：`/app/dist` 是匿名卷，不带会保留旧版前端。

### 常用命令

```bash
docker compose -f docker-compose.dev.yaml logs -f app   # 实时日志
docker compose -f docker-compose.dev.yaml restart app   # 改 .env 后重启
```

### 常见问题

| 现象 | 处理 |
|---|---|
| 抓取提示登录态失效 | Web UI → 账号管理，重新扫码/上传登录态 |
| AI 分析报 Connection error | 检查容器内 `HTTP_PROXY` 是否为空：`docker exec ai-goofish-monitor-app env \| grep -i proxy` |
| 滑动验证码卡住 | `.env` 设 `RUN_HEADLESS=false`，本机跑一次过验证后再迁回服务器 |
| AI 结果 JSON 解析失败 | 确认 `ENABLE_THINKING=true`（触发禁用思考参数） |

## 十、数据备份

所有有状态数据都在仓库目录内，直接打包即可：

```bash
tar czf xianyu-backup-$(date +%F).tar.gz .env xianyu_state.json data/ prompts/ state/
```

建议 cron 每日打包并传走（OSS/rsync 均可）。
