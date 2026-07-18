# FUND-OS 基金智能估算系统

面向基金净值估算、组合分析、实时行情与商业化订阅（支付）的一站式平台。
后端 Python（Flask + Gunicorn），前端 Vue 3，数据层 PostgreSQL + Redis，Docker 一键编排，
Nginx 负责静态资源与 API 反向代理。

---

## 技术栈

- **后端**：Flask（蓝图拆分）、Gunicorn（gevent worker）、SQLAlchemy / PostgreSQL、Redis
- **前端**：Vue 3 + Vite，构建产物由 Nginx 托管
- **支付**：支付宝（RSA2 全字段签名 / 扫码 precreate）、微信支付（API v2 MD5 / 统一下单）
- **部署**：Docker Compose（app + postgres + redis + prometheus + grafana），Nginx 反代 + TLS

---

## 目录结构（要点）

```
fund_estimation_system/
├── visualization/            # Flask 应用、蓝图、模板
│   ├── web_server.py        # 应用工厂 + 单例客户端
│   └── blueprints/
│       └── billing_bp.py    # 支付/订阅路由（订单、notify、return、sandbox）
├── data_fetcher/
│   └── payment_service.py   # 支付宝/微信签名、验签、下单、回调处理
├── config.py                # 配置（含证书路径、支付模式、回调域名）
├── docker/
│   ├── nginx.conf           # HTTPS 反代 + HSTS + ACME（详见下）
│   ├── Dockerfile
│   ├── entrypoint.sh        # 同时启动 Nginx + Gunicorn
│   └── HTTPS_SETUP.md       # 生产证书申请与上线清单（权威文档）
├── scripts/
│   ├── renew_cert.sh        # 证书签发 / 续期（多域名 + 泛域名）
│   ├── deploy_check.sh      # 部署后健康检查（上线门禁）
│   └── lint_sh.sh           # shell 脚本静态检查包装（bash -n + shellcheck）
├── .github/workflows/
│   ├── deploy-check.yml     # CI 上线健康检查（SSH → make check）
│   └── lint.yml             # CI shell 脚本静态检查
├── .pre-commit-config.yaml  # 提交前自动校验 scripts/*.sh
├── Makefile                 # make cert / make check 便捷入口
├── docker-compose.yml
└── .env.example             # 生产配置模板（复制为 .env 后填真实值）
```

---

## 快速开始

### 本地 / 演示（沙箱）

```bash
cp .env.example .env          # PAYMENT_MODE 默认 sandbox，可用模拟支付
docker compose up -d
# 访问 http://localhost:5000
```

沙箱模式下 `/sandbox/pay-confirm` 提供模拟支付确认页，无需真实商户号即可跑通变现闭环；
**生产模式该路由返回 403**，杜绝伪造入账。

### 生产（真实收款 + HTTPS）

1. 复制 `.env.example` 为 `.env`，填真实支付宝/微信参数，设 `PAYMENT_MODE=production`。
2. 申请 TLS 证书并配置 Nginx 反代（**详细步骤见 [`docker/HTTPS_SETUP.md`](docker/HTTPS_SETUP.md)**）。
3. 关键环境变量（生产必须为公网 HTTPS 域名）：
   ```dotenv
   PAYMENT_NOTIFY_BASE=https://pay.your-domain.com
   PAYMENT_RETURN_URL=https://pay.your-domain.com/api/billing/return
   ```
   > 回跳 `return_url` 必须是 `/api/billing/return`（即生产 RSA2 验签路由），
   > 支付宝/微信异步回调则自动拼为 `/api/billing/notify/{alipay|wechat}`。

---

## 生产支付与 HTTPS 运维

完整清单（证书申请、挂载、续期、支付后台登记、验证、故障排查）见
[`docker/HTTPS_SETUP.md`](docker/HTTPS_SETUP.md)。

常用命令（`Makefile` 封装）：

```bash
make cert                                      # 签发证书（默认单域名）
make cert CERT_DOMAINS="your-domain.com *.your-domain.com"   # 多域名 / 泛域名
make cert-renew                                # 续期 + 复制 + 重载 nginx（cron 调用）
make check                                     # 部署后健康检查（7 项，失败非 0）
make check DOMAIN=pay.your-domain.com
```

- **证书脚本** `scripts/renew_cert.sh`：支持多域名 SAN 与泛域名（泛域名自动走 DNS-01 挑战）。
- **健康检查** `scripts/deploy_check.sh`：校验本地证书、HTTP→HTTPS 跳转、/api/health、
  HSTS、支付接口、回跳路由、TLS 有效期，可作 CI 上线门禁。
- **CI**：`.github/workflows/deploy-check.yml` 通过 SSH 登录服务器运行 `make check`，
  任一失败即工作流失败（需在仓库 Secrets 配置 `DEPLOY_HOST/USER/SSH_KEY/PATH`）。

**脚本校验（提交门禁）**
运维脚本（`scripts/*.sh`）纳入静态检查，避免把有语法错误的脚本推上线：
- 本地：安装 `pre-commit` 后 `pre-commit install`，提交时自动跑 `bash -n` + `shellcheck`；
  也可手动 `bash scripts/lint_sh.sh scripts/renew_cert.sh`。
- CI：`.github/workflows/lint.yml` 在 PR / 推送时强制校验，未装 shellcheck 的机器仅做语法检查。

---

## 安全要点

- 生产模式禁用 `/sandbox/pay-confirm`（`abort(403)`），仅以异步 `notify` 回调作为入账依据。
- 支付宝同步回跳在生产环境做 RSA2 验签（`verify_alipay_return`），回跳页展示「校验未通过」提示。
- 私钥/公钥推荐用文件加载（`*_PATH` 指向 `/run/secrets/...`），避免明文写入环境变量。
- 全站 HTTPS + HSTS + 安全响应头；`X-Forwarded-Proto` 固定为 `https`，保证回调 URL 为公网 HTTPS。

---

## 测试与回归

回归用例集中在 `tests/`，由正式 `pytest.ini` 驱动，**常驻 CI 门禁**（见 `.github/workflows/ci-cd.yml` 的 `test` 作业，构建/部署前必须通过）。

### 标记约定

- `regression`：已验证的常驻回归套件，作为发布门禁。包含：
  - `test_billing_p0.py` — P0 安全/计费硬伤（认证不可伪造、付费墙、支付跨进程一致、手动激活限 admin）
  - `test_p1.py` — P1 限流（Redis 优先 + 内存兜底）与密码强度策略、改密接口
  - `test_smoke.py` — 端到端冒烟（`create_app` 在完整依赖下可启动、全局限流中间件真实命中 429）
- 其余 `test_*.py` 为旧接口用例（`/api/v1/...`），与当前实现不一致，**不纳入门禁**（未打 `regression` 标记，运行 `make test` / `pytest -m regression` 时自动跳过）。

### 本地运行

```bash
pip install -r requirements.txt -r test-requirements.txt

make test          # 运行常驻回归套件（推荐）
# 等价于：pytest -m regression -v

make test-all      # 运行全部测试（含旧接口用例，需完整依赖栈）
```

> 说明：`test_smoke.py` 中 `create_app` 启动依赖 pandas/tushare 等重型依赖；
> 本地若未安装，该用例经 `pytest.importorskip` 优雅跳过，不会变红。
> CI 装齐依赖后会真正执行，作为「生产可达性闸门」。

### CI

`.github/workflows/ci-cd.yml` 在 `push` / `pull_request` 到 `main` / `develop` 时：

1. `lint-test` — flake8 / 前端 lint / 类型检查；
2. `test` — 安装依赖 → 软链 `fund_estimation_system` 使 `fund_estimation_system.*` 可导入 → `pytest -m regression`；
3. `build` / `deploy-*` — 仅当前两步通过后执行。

回归套件有任何失败，流水线即中止，阻断上线。

---

## 合规页面（P2）

四类合规页面以 **Vue SPA 路由**形式落地（生产面由 Nginx 托管 SPA，Flask 仅反代 `/api`），用户无需登录即可访问：

| 路由 | 页面 | 说明 |
| --- | --- | --- |
| `/disclaimer` | 免责声明 | 信息性质、风险提示、数据/模型局限、免责范围 |
| `/privacy` | 隐私政策 | 信息收集/使用/共享/存储、用户权利（依据 PIPL） |
| `/refund` | 退款政策 | 可退/不可退情形、退款流程与时效 |
| `/about` | 关于我们 / 备案 | 运营主体、联系方式、ICP/公安备案号 |

- 页脚（`AppFooter.vue`）已接入上述四个链接，并展示 **ICP 备案号**（取自站点配置）。
- 备案号/公司名/联系方式等公开展示信息统一由后端 `GET /api/public/site-config` 提供（无需认证），
  前端 `useSiteStore` 启动时拉取并兜底默认值；配置项源自 `config.py`，可用环境变量覆盖
  （见 `.env.example` 的「站点与合规」段：`SITE_NAME` / `COMPANY_NAME` / `ICP_BEIAN` / `POLICE_BEIAN` / `CONTACT_EMAIL` / `SERVICE_TEL`）。
- **上线前务必在 `.env` 填入真实 ICP/公安备案号与运营主体**，否则关于页与页脚将显示占位文案。
