# FUND-OS 生产 HTTPS 与支付证书上线清单

本清单配合 `docker/nginx.conf`（已启用 443 + HSTS + ACME 校验目录）使用，目标是让
支付宝/微信支付的**异步回调（notify）与同步回跳（return）走 HTTPS 公网**，并完成 TLS 证书的申请、挂载与续期。

---

## 0. 前置条件

- [ ] 一台拥有**公网 IP** 的服务器（已部署本项目的 Docker Compose 栈）。
- [ ] 一个已备案/可解析的**域名**，例如 `pay.your-domain.com`。
- [ ] 域名的 **A 记录**已指向服务器公网 IP（TTL 调小，便于验证）。
- [ ] 服务器 **80 与 443 端口**在防火墙/安全组中放行（Let's Encrypt 需要 80 做 http-01 校验）。
- [ ] 已复制 `.env.example` 为 `.env` 并填好支付宝/微信真实参数（见下文第 4 步）。

> 支付回调必须由支付宝/微信服务器主动访问，因此**必须是公网 HTTPS 域名**，不能是
> `127.0.0.1` / 内网 IP / IP 直连（微信 H5、支付宝回调均会拒绝）。

---

## 1. 申请 TLS 证书（二选一）

### 方案 A：Let's Encrypt（免费、自动续期，推荐）

容器已把宿主机 `./certbot` 挂载到 `/var/www/certbot` 作为 webroot，且 nginx 的
`location ^~ /.well-known/acme-challenge/` 已放行，因此用 **webroot 模式**即可，无需停服。

**1) 在宿主机安装 certbot**（以 Ubuntu 为例）：
```bash
sudo apt update && sudo apt install -y certbot
```

**2) 签发证书**（把下面的域名换成你的）：
```bash
sudo certbot certonly --webroot \
  -w /path/to/fund_estimation_system/certbot \
  -d pay.your-domain.com \
  --email admin@your-domain.com \
  --agree-tos --non-interactive
```
成功后证书位于：
```
/etc/letsencrypt/live/pay.your-domain.com/fullchain.pem
/etc/letsencrypt/live/pay.your-domain.com/privkey.pem
```

**3) 复制到项目的 `./certs` 目录**（nginx 挂载点），并按约定命名：
```bash
mkdir -p /path/to/fund_estimation_system/certs
sudo cp /etc/letsencrypt/live/pay.your-domain.com/fullchain.pem \
        /path/to/fund_estimation_system/certs/fullchain.pem
sudo cp /etc/letsencrypt/live/pay.your-domain.com/privkey.pem \
        /path/to/fund_estimation_system/certs/privkey.pem
sudo chmod 644 /path/to/fund_estimation_system/certs/*.pem
```
> nginx.conf 中证书路径为 `/etc/nginx/certs/fullchain.pem` 与 `/etc/nginx/certs/privkey.pem`，
> 即通过 `./certs:/etc/nginx/certs:ro` 挂载进来，名称必须一致。

**4) 自动续期**（Let's Encrypt 证书 90 天有效）：
```bash
# 加入 crontab，每月尝试续期并复制新证书
echo "0 3 1 * * certbot renew --quiet && \
  cp /etc/letsencrypt/live/pay.your-domain.com/fullchain.pem /path/to/fund_estimation_system/certs/fullchain.pem && \
  cp /etc/letsencrypt/live/pay.your-domain.com/privkey.pem /path/to/fund_estimation_system/certs/privkey.pem && \
  docker compose -f /path/to/fund_estimation_system/docker-compose.yml exec -T app nginx -s reload" \
  | sudo crontab -
```

### 方案 B：云厂商免费证书（阿里云/腾讯云/DigiCert 等）

- 在云厂商控制台申请**免费 DV 证书**（通常 1 年有效）。
- 下载 **Nginx 格式**证书包，得到 `xxx.pem`（证书链）与 `xxx.key`（私钥）。
- 重命名为 `fullchain.pem` / `privkey.pem` 放入项目 `./certs`。
- 手动在证书到期前重新下载替换（无自动续期，建议设日历提醒）。

---

## 2. 启动 / 重载

证书就位后：

```bash
cd /path/to/fund_estimation_system
docker compose up -d          # 首次启动会挂载 ./certs 与 ./certbot
# 若已运行，仅重载 nginx 使新证书生效：
docker compose exec app nginx -s reload
```

验证监听：
```bash
docker compose ps            # 应看到 80/443 映射
curl -I http://pay.your-domain.com/api/health     # 期望 301 跳转到 https
curl -I https://pay.your-domain.com/api/health    # 期望 200
```

---

## 3. 在支付宝 / 微信后台登记回调域名

证书与反代就绪后，把公网 HTTPS 地址登记到商户平台：

### 支付宝（开放平台 open.alipay.com）
- **授权回调地址 / 应用网关**：`https://pay.your-domain.com`
- 代码中 `notify_url` 自动拼接为
  `https://pay.your-domain.com/api/billing/notify/alipay`
- `return_url` 自动拼接为（由 `PAYMENT_RETURN_URL` 决定）
  `https://pay.your-domain.com/api/billing/return`

### 微信支付（商户平台 pay.weixin.qq.com）
- **支付通知地址（Notify URL）**：
  `https://pay.your-domain.com/api/billing/notify/wechat`
  （微信后台一般只填域名根或完整 URL，必须 HTTPS 且公网可达）
- 微信 H5 支付还要求**备案域名**与 **Referer/域名白名单**一致。

---

## 4. 填写 `.env` 关键项

```dotenv
PAYMENT_MODE=production

# 必须为公网 HTTPS 域名（与证书域名一致）
PAYMENT_NOTIFY_BASE=https://pay.your-domain.com
# 注意：回跳必须是 /api/billing/return（验签路由），不是 /billing/return
PAYMENT_RETURN_URL=https://pay.your-domain.com/api/billing/return

# 支付宝公钥 / 微信 API Key 等按 .env.example 填真实值
```

改完 `.env` 后重启应用栈使环境变量生效：
```bash
docker compose up -d
```

---

## 5. 验证支付闭环

- [ ] `curl -I http://域名/...` 返回 301→HTTPS。
- [ ] `curl https://域名/api/health` 返回 200。
- [ ] 浏览器访问 `https://域名/` 地址栏显示锁标，无混合内容告警。
- [ ] 创建一笔测试订单 → 支付宝/微信扫码 → 手机完成支付 →
      商户平台能看到 `notify` 请求命中
      `https://域名/api/billing/notify/{alipay|wechat}`（看应用日志 `[billing]`）。
- [ ] 支付完成后浏览器被带回 `https://域名/api/billing/return?...`，
      页面显示「回跳签名校验通过」（生产模式已做 RSA2 验签）。
- [ ] 订单状态变为 `paid`，订阅/配额正确联动。

> 以上步骤可一键自动化：运行 `scripts/deploy_check.sh`（自动校验 TLS 证书文件、
> HTTP→HTTPS 跳转、/api/health、HSTS 头、支付接口、回跳路由、证书有效期），
> 任一失败项返回非 0 退出码，可作为上线门禁 / CI 步骤。
> ```bash
> DOMAIN=pay.your-domain.com ./scripts/deploy_check.sh
> ```

---

## 6. 常见故障排查

| 现象 | 原因 | 处理 |
|------|------|------|
| 回跳 404 | `PAYMENT_RETURN_URL` 写成 `/billing/return`（无此路由） | 改为 `/api/billing/return` |
| 回调 404 | nginx `proxy_pass` 掉了 `/api` 前缀 | 已修复：所有 `proxy_pass` 不带尾斜杠 |
| 回调收不到 | 域名非公网 / 80+443 未放行 / 证书域名不符 | 检查 DNS、安全组、HTTPS 可达性 |
| 微信 H5 报「域名未备案」 | 商户平台支付域名未配置/不一致 | 在微信后台补全 H5 域名白名单 |
| 证书续期后仍 502 | nginx 未 reload | 续期脚本中执行 `nginx -s reload` |
| 混合内容告警 | 前端资源用 http 加载 | 全站 HTTPS；CSP 已限制 `default-src 'self'` |

---

## 7. 一键签发/续期脚本（scripts/renew_cert.sh）

日常运维可用脚本替代手工 certbot 命令，自动完成「签发/续期 → 复制到 ./certs → 重载 nginx」。

```bash
# 多域名（含子域）首次签发
CERT_DOMAINS="pay.your-domain.com www.your-domain.com" \
CERT_EMAIL="admin@your-domain.com" \
./scripts/renew_cert.sh issue

# 泛域名（*.your-domain.com）：脚本自动切换 DNS-01 挑战
CERT_DOMAINS="your-domain.com *.your-domain.com" \
./scripts/renew_cert.sh issue

# 续期（crontab 每月调用，仅临期才真正续）
./scripts/renew_cert.sh renew

# 仅复制并重载（证书由其他方式签发时）
./scripts/renew_cert.sh copy
```

**多域名 / 泛域名说明**
- 普通多域名（如 `pay.x.com` + `www.x.com`）：脚本用 `--webroot` 一次签发一张 **SAN 证书**；nginx 的 `server_name _` 已对所有域名生效，无需改 `nginx.conf`。
- **泛域名**（`*.x.com`）：Let's Encrypt 仅支持 **DNS-01** 挑战，脚本自动改用 `--manual --preferred-challenges dns`；生产建议安装云厂商 DNS 插件（如 `certbot-dns-aliyun`）实现无人值守。泛域名证书同样为单文件，nginx 路径不变。
- 无论单/多/泛域名，证书文件名统一为 `fullchain.pem` / `privkey.pem`，与 `nginx.conf` 的 `/etc/nginx/certs/` 挂载点一致。

**推荐 crontab（每月 1 号 03:00 续期）**
```bash
0 3 1 * * /path/to/fund_estimation_system/scripts/renew_cert.sh renew >> /var/log/renew_cert.log 2>&1
```

**Makefile 便捷入口**
项目根目录提供 `Makefile`，封装上述脚本，免去记命令：
```bash
make cert                                  # 签发（默认单域名）
make cert CERT_DOMAINS="your-domain.com *.your-domain.com"   # 多域名 / 泛域名
make cert-renew                            # 续期
make check                                 # 部署后健康检查
make check DOMAIN=pay.your-domain.com
```

**CI 自动校验（GitHub Actions）**
仓库已内置 `.github/workflows/deploy-check.yml`：通过 SSH 登录部署服务器运行
`make check`，任一项失败即工作流失败，可作为上线门禁。

在仓库 **Settings → Secrets** 配置：
- `DEPLOY_HOST`：服务器公网 IP / 域名
- `DEPLOY_USER`：SSH 用户名
- `DEPLOY_SSH_KEY`：SSH 私钥（对应服务器 `authorized_keys`）
- `DEPLOY_PATH`：服务器上项目根目录（含 Makefile / scripts/）

触发：GitHub → Actions → **Deploy Health Check** → Run workflow，输入已上线域名。
也可接在部署流程之后自动跑（文件内已注释示例 `workflow_run`）。


## 8. 目录约定（部署后）

```
fund_estimation_system/
├── certs/                 # 宿主机证书目录 → 挂载到 /etc/nginx/certs（只读）
│   ├── fullchain.pem
│   └── privkey.pem
├── certbot/               # certbot webroot 校验目录 → 挂载到 /var/www/certbot
├── docker/
│   ├── nginx.conf         # 已启用 443 / HSTS / ACME
│   └── HTTPS_SETUP.md     # 本文件
├── scripts/
│   ├── renew_cert.sh      # 证书签发 / 续期（多域名 + 泛域名）
│   └── deploy_check.sh    # 部署后健康检查（上线门禁）
├── Makefile               # make cert / make check 便捷入口
└── docker-compose.yml     # 已暴露 443 并挂载 certs / certbot
```

---

## 9. 回滚与应急预案

### 9.1 证书泄露 / 私钥泄露轮换

一旦 `privkey.pem` 或支付宝/微信密钥可能泄露，按以下顺序处置：

1. **立即吊销并重新签发 TLS 证书**（Let's Encrypt 旧证书仍可信，但私钥已不可信）：
   ```bash
   # 吊销旧证书（可选，Let's Encrypt 无强制吊销场景也建议做）
   certbot revoke --cert-path /etc/letsencrypt/live/域名/fullchain.pem
   # 重新签发（生成全新密钥对）
   CERT_DOMAINS="pay.your-domain.com" ./scripts/renew_cert.sh issue
   # 或：make cert
   ```
2. **轮换应用侧密钥**（若一并泄露）：
   - 支付宝：**重签应用公钥** → 开放平台「开发设置 → 加签方式」重新生成密钥对，
     把新私钥写入 `*_PATH` 指向的 `/run/secrets/`，新**支付宝公钥**填入 `ALIPAY_PUBLIC_KEY`。
   - 微信：商户平台「API 安全 → API 密钥」**重置 APIv2 密钥**，更新 `WECHAT_API_KEY`。
3. **轮换服务器 SSH / 仓库 Secrets**：若 `DEPLOY_SSH_KEY` 泄露，作废对应公钥并重发。
4. **验证**：`make check` 确认新证书生效、回跳验签仍通过；观察 1~2 小时无异常回调。

> 私钥切勿进 Git / 镜像层。本方案用 `*_PATH` 文件加载 + `docker-compose` 只读挂载，
> 泄露面仅限运行时宿主机 `/run/secrets` 与 `./certs`，便于定点轮换。

### 9.2 误上线 / 故障止血

**场景 A：生产配置错误，回调收不到 / 回跳 404**
- 多半是 nginx 配置回退到旧版（掉了 `/api` 前缀）或 `return_url` 写错。
- 止血：`docker compose exec app nginx -s reload` 重载**修正版** `nginx.conf`（已随镜像内置）。
- 确认：`make check` 第 2/3/6 项必须全绿。

**场景 B：nginx 改坏导致 502/无法 reload**
- 回滚配置：`cp docker/nginx.conf.bak /etc/nginx/nginx.conf && nginx -s reload`
  （建议每次改 nginx.conf 前 `cp nginx.conf nginx.conf.bak`）。
- 极端情况停 Nginx 直连后端临时恢复：`docker compose stop app` 后改端口映射，仅作应急。

**场景 C：怀疑假支付 / 异常订单入账**
- 生产仅以**异步 notify** 为入账依据；sandbox 路由已 `abort(403)`，正常不会伪造。
- 若发现异常订单：查 `cache/billing_orders.json`，定位 `status=paid` 的可疑单，
  通过**商务手动激活接口** `POST /api/billing/activate` 仅用于线下合同，不用于修正；
  异常单应冻结并人工核对支付宝/微信商户后台流水，必要时联系支付机构调单。
- 临时停止收款（止血）：将 `PAYMENT_MODE` 切回 `sandbox` 并 `docker compose up -d`，
  使新建订单走模拟通道、生产回调不再触发入账，待排查清楚再切回。

**场景 D：证书即将过期但续期失败**
- webroot 模式失败：确认 80 端口与 `.well-known/acme-challenge` 可达（`make check` 第 2 项）。
- DNS 模式（泛域名）失败：手动按提示添加 `_acme-challenge` TXT 记录后重试。
- 应急：先用**自签/云厂商临时证书**替换 `./certs` 保住 HTTPS（业务不中断），
  再排期彻底修复续期链路。切勿为「先恢复」而关 TLS 退回 HTTP——支付回调会被支付宝/微信拒绝。

**通用止血 checklist**
- [ ] 保留现场：先 `cp nginx.conf nginx.conf.bak`、备份 `billing_orders.json`
- [ ] 评估影响面：哪些渠道（支付宝/微信）、哪些订单受影响
- [ ] 止血优先于修复：先停风险入口（切 sandbox / 停 Nginx / 冻结订单）
- [ ] 用 `make check` 验证恢复后再开放流量
- [ ] 事后复盘：补 `cron` 续期监控、加 `deploy-check.yml` 门禁、密钥定期轮换
