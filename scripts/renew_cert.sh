#!/usr/bin/env bash
# ============================================================
# FUND-OS TLS 证书一键签发 / 续期脚本
# 依赖：宿主机已安装 certbot（apt install -y certbot）
# 证书最终落地到项目 ./certs/{fullchain.pem,privkey.pem}
# （由 docker-compose 以只读挂载进 nginx:/etc/nginx/certs）
#
# 用法：
#   多域名（含子域）首次签发：
#     CERT_DOMAINS="pay.your-domain.com www.your-domain.com" \
#     CERT_EMAIL="admin@your-domain.com" \
#     ./scripts/renew_cert.sh issue
#
#   泛域名（*.your-domain.com，需 DNS-01 挑战）：
#     CERT_DOMAINS="your-domain.com *.your-domain.com" \
#     ./scripts/renew_cert.sh issue
#
#   后续续期（cron 调用，90 天证书自动续）：
#     ./scripts/renew_cert.sh renew
#
#   仅把已存在的证书复制到 ./certs 并重载 nginx：
#     ./scripts/renew_cert.sh copy
# ============================================================
set -euo pipefail

# 项目根目录（脚本位于 scripts/ 下，上级即根）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

CERTS_DIR="$ROOT_DIR/certs"
WEBROOT_DIR="$ROOT_DIR/certbot"
COMPOSE_FILE="$ROOT_DIR/docker-compose.yml"

EMAIL="${CERT_EMAIL:-admin@your-domain.com}"
# 默认单域名；可传多个（空格分隔），支持泛域名 *.xxx
DOMAINS="${CERT_DOMAINS:-pay.your-domain.com}"

# 是否包含泛域名（泛域名只能走 DNS-01 挑战，不能用 webroot）
HAS_WILDCARD=0
for d in $DOMAINS; do
  case "$d" in
    *\** ) HAS_WILDCARD=1 ;;
  esac
done

mkdir -p "$CERTS_DIR" "$WEBROOT_DIR"

# 用数组累积 "-d <domain>" 参数，避免词拆分被 shellcheck 误报 (SC2086)

# 复制证书并重载 nginx
copy_certs() {
  # 优先从 `certbot certificates` 解析正式路径，兼容 SAN/多域名
  local cert_path
  cert_path="$(certbot certificates 2>/dev/null | awk '/Certificate Path/ {print $3; exit}')"

  if [[ -z "$cert_path" ]]; then
    # 兜底：用首个域名目录
    local first_domain
    first_domain="$(echo "$DOMAINS" | awk '{print $1}')"
    cert_path="/etc/letsencrypt/live/$first_domain/fullchain.pem"
  fi

  local live_dir
  live_dir="$(dirname "$cert_path")"

  if [[ ! -f "$live_dir/fullchain.pem" || ! -f "$live_dir/privkey.pem" ]]; then
    echo "错误：未在 $live_dir 找到证书文件，请先执行 issue。" >&2
    exit 1
  fi

  cp "$live_dir/fullchain.pem" "$CERTS_DIR/fullchain.pem"
  cp "$live_dir/privkey.pem"  "$CERTS_DIR/privkey.pem"
  chmod 644 "$CERTS_DIR"/*.pem
  echo "✓ 证书已复制到 $CERTS_DIR"

  # 重载 nginx（容器名为 docker-compose 中的 app 服务）
  if docker compose -f "$COMPOSE_FILE" ps app >/dev/null 2>&1; then
    if docker compose -f "$COMPOSE_FILE" exec -T app nginx -s reload 2>/dev/null; then
      echo "✓ 已通知 nginx 重载配置"
    else
      echo "⚠ nginx 重载失败（容器未运行或名称不同），请手动 reload。" >&2
    fi
  else
    echo "⚠ 未检测到运行中的容器，跳过 nginx 重载（证书已就位，下次启动生效）。"
  fi
}

issue() {
  local dargs=()
  for d in $DOMAINS; do
    dargs+=(-d "$d")
  done
  if [[ "$HAS_WILDCARD" -eq 1 ]]; then
    echo "检测到泛域名，需使用 DNS-01 挑战。"
    echo "提示：可安装对应 DNS 插件（如 certbot-dns-aliyun）实现自动校验；"
    echo "      否则将进入 --manual 模式，需按提示手动添加 _acme-challenge TXT 记录。"
    certbot certonly --manual --preferred-challenges dns \
      --email "$EMAIL" --agree-tos --non-interactive \
      "${dargs[@]}"
  else
    certbot certonly --webroot -w "$WEBROOT_DIR" \
      --email "$EMAIL" --agree-tos --non-interactive \
      "${dargs[@]}"
  fi
  copy_certs
}

renew() {
  # certbot renew 只对 30 天内到期的证书实际续期，安全可每日/每月调用
  certbot renew --quiet || true
  copy_certs
}

case "${1:-renew}" in
  issue) issue ;;
  renew) renew ;;
  copy)  copy_certs ;;
  *) echo "用法: $0 [issue|renew|copy]" >&2; exit 1 ;;
esac
