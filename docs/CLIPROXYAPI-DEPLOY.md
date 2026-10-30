# CLIProxyAPI 部署指南（阿里云免费额度聚合 → goofish）

目标：把阿里云百炼多个模型的免费额度聚合成一个 OpenAI 兼容端点，额度耗尽自动切换到池内下一个模型，供 ai-goofish-monitor 使用。

```
goofish 容器 ──http──▶ cli-proxy-api 容器:8317 ──https──▶ dashscope.aliyuncs.com
                        （模型池 goofish：qwen-turbo/plus/max/...）
                        429/额度错误 → 自动换下一个模型 + 冷却
```

## 一、准备

- 阿里云百炼控制台开通所需模型（有免费额度的都开），创建 API Key（`sk-` 开头）
- 确认哪些模型有免费额度（控制台 → 模型广场 → 每个模型页有"免费额度"标注），记下模型名

## 二、部署目录与配置

```bash
sudo mkdir -p /opt/cliproxyapi && cd /opt/cliproxyapi
sudo mkdir -p auths logs plugins
```

创建 `/opt/cliproxyapi/config.yaml`（模板见下，替换两处：百炼 API Key、下游访问 key）：

```yaml
config-version: 8

server:
  host: ""          # 只在 docker 网络内暴露，不映射宿主机端口
  port: 8317

# goofish 连接代理时用的鉴权 key（自己随机生成一个，与百炼 Key 无关）
access:
  api-keys:
    - "sk-goofish-换成一串随机字符"

management:
  secret-key: ""    # 需要管理面板时再配；留空=禁用管理 API（更安全）

routing:
  strategy: "round-robin"
  retry:
    request-retry: 3          # 403/408/429/5xx 自动换目标重试
    max-retry-credentials: 0
    max-retry-interval: 30
  cooldown:
    disable-cooling: false    # 额度耗尽的模型进冷却，请求路由到池内其他模型

openai-compatibility:
  - name: "aliyun-bailian"
    base-url: "https://dashscope.aliyuncs.com/compatible-mode/v1"
    keys:
      - api-key: "sk-百炼的APIKey"
    request-scoped-errors:
      # 额度类错误：换下一个模型并冷却当前模型（按状态码兜底已含 429/403）
      - status: 429
        match: ["quota", "Quota", "Throttling", "exhausted", "Arrearage"]
        action: "continue-and-cooldown"
      - status: 403
        match: ["quota", "Quota", "Arrearage"]
        action: "continue-and-cooldown"
    models:
      # ↓ 模型池：别名全部相同 = 自动轮换/故障转移池
      # 按你实际有免费额度的模型增删；模型名以百炼控制台为准
      - name: "qwen-turbo"
        alias: "goofish"
      - name: "qwen-plus"
        alias: "goofish"
      - name: "qwen-max"
        alias: "goofish"
      - name: "qwen-long"
        alias: "goofish"
      # 如有视觉模型额度且任务保留"分析图片"，加入并声明多模态：
      # - name: "qwen-vl-plus"
      #   alias: "goofish"
      #   input-modalities: [text, image]
```

## 三、Docker 网络 + 启动

两个容器走同一个 Docker 内部网络（不暴露任何宿主机端口，最安全）：

```bash
# 1) 创建共享网络（一次性）
docker network create ai-net
```

创建 `/opt/cliproxyapi/docker-compose.yaml`：

```yaml
services:
  cli-proxy-api:
    image: eceasy/cli-proxy-api:latest
    container_name: cli-proxy-api
    restart: unless-stopped
    volumes:
      - ./config.yaml:/CLIProxyAPI/config.yaml
      - ./auths:/root/.cli-proxy-api
      - ./logs:/CLIProxyAPI/logs
      - ./plugins:/CLIProxyAPI/plugins
    networks:
      - ai-net

networks:
  ai-net:
    external: true
```

```bash
# 2) 启动
docker compose up -d
docker logs cli-proxy-api 2>&1 | head -20    # 应看到监听 8317、加载 aliyun-bailian
```

## 四、把 goofish 接进来

编辑 `/opt/ai-goofish-monitor/docker-compose.dev.yaml`，给 `app` 服务加网络：

```yaml
services:
  app:
    # ...原有内容不动...
    networks:
      - ai-net

networks:
  ai-net:
    external: true
```

编辑 `/opt/ai-goofish-monitor/.env`：

```ini
OPENAI_BASE_URL=http://cli-proxy-api:8317/v1
OPENAI_API_KEY=sk-goofish-刚才随机生成的那串
OPENAI_MODEL_NAME=goofish
ENABLE_THINKING=false    # qwen 商业版默认不推理；true 会带 DeepSeek 专用参数，百炼可能报 400
```

```bash
cd /opt/ai-goofish-monitor
docker compose -f docker-compose.dev.yaml up -d     # 重建容器使网络生效
```

## 五、验证

1. Web UI → 系统设置 → AI 模型 → **测试连接**（应返回成功）
2. 触发一次任务，日志中 AI 分析正常返回 JSON
3. 观察切换：`docker logs -f cli-proxy-api`，额度耗尽的模型会进入冷却、请求转到池内下一个

## 六、注意事项

| 事项 | 说明 |
|---|---|
| 纯文本模型池 | 任务的「分析商品图片」开关必须关闭（编辑任务 → 关闭 → 保存），否则带图请求会被文本模型 400 拒绝 |
| 免费额度期限 | 阿里云免费额度多为首次调用后 90/180 天有效，尽早用 |
| 安全 | 代理持有百炼 Key；本方案不映射宿主机端口、管理 API 默认禁用，只允许 docker 网络内访问 |
| 换回 DeepSeek | `.env` 三行改回 api.deepseek.com + deepseek-flash，`ENABLE_THINKING=true`，重启容器即可 |
