#!/usr/bin/env bash
# ============================================================
# FUND-OS 部署后健康检查脚本
# 自动校验：本地证书文件、HTTP(80)→HTTPS(443) 跳转、API 健康、
#           HSTS 头、支付套餐接口、支付宝回跳路由、TLS 证书有效期。
# 存在失败项时退出码非 0，便于 CI / 上线门禁使用。
#
# 用法：
#   DOMAIN=pay.your-domain.com ./scripts/deploy_check.sh
#   ./scripts/deploy_check.sh pay.your-domain.com
# ============================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
DOMAIN="${1:-${DOMAIN:-pay.your-domain.com}}"
CERTS_DIR="$ROOT_DIR/certs"

PASS=0; FAIL=0
ok()   { echo "  ✅ $1"; PASS=$((PASS+1)); }
bad()  { echo "  ❌ $1"; FAIL=$((FAIL+1)); }
info() { echo "▶ $1"; }

echo "==== FUND-OS 部署健康检查: $DOMAIN ===="

# 1) 本地证书文件
info "1) 本地证书文件 (./certs)"
if [[ -f "$CERTS_DIR/fullchain.pem" && -f "$CERTS_DIR/privkey.pem" ]]; then
  ok "certs/fullchain.pem 与 privkey.pem 存在"
else
  bad "certs/ 下缺少 fullchain.pem 或 privkey.pem（先跑 renew_cert.sh issue）"
fi

# 2) HTTP -> HTTPS 跳转
info "2) HTTP(80) → HTTPS(443) 跳转"
LOC=$(curl -s -o /dev/null -w '%{redirect_url}' "http://$DOMAIN/api/health" --max-time 10)
if [[ "$LOC" == https* ]]; then
  ok "http://$DOMAIN 跳转到 $LOC"
else
  bad "未检测到到 HTTPS 的 301 跳转（得到: '$LOC'）"
fi

# 3) HTTPS /api/health
info "3) HTTPS /api/health"
CODE=$(curl -s -o /dev/null -w '%{http_code}' "https://$DOMAIN/api/health" --max-time 10)
if [[ "$CODE" == "200" ]]; then
  ok "GET https://$DOMAIN/api/health → 200"
else
  bad "GET https://$DOMAIN/api/health → $CODE（期望 200）"
fi

# 4) HSTS 安全头
info "4) HSTS 安全头"
HSTS=$(curl -s -I "https://$DOMAIN/api/health" --max-time 10 | grep -i 'strict-transport-security' || true)
if [[ -n "$HSTS" ]]; then
  ok "$(echo "$HSTS" | tr -d '\r')"
else
  bad "响应缺少 Strict-Transport-Security 头"
fi

# 5) 支付套餐接口
info "5) 支付套餐接口 /api/billing/plans"
BODY=$(curl -s "https://$DOMAIN/api/billing/plans" --max-time 10)
if echo "$BODY" | grep -q '"plans"'; then
  ok "GET /api/billing/plans 返回套餐数据"
else
  bad "GET /api/billing/plans 未返回预期 JSON（body: ${BODY:0:120}）"
fi

# 6) 支付宝同步回跳路由（无参数也应渲染页面 200；生产会显示“未通过”提示但不 404）
info "6) 支付宝同步回跳路由 /api/billing/return"
RCODE=$(curl -s -o /dev/null -w '%{http_code}' "https://$DOMAIN/api/billing/return" --max-time 10)
if [[ "$RCODE" == "200" ]]; then
  ok "GET /api/billing/return → 200（页面可达，未被 nginx 误拦截）"
else
  bad "GET /api/billing/return → $RCODE（期望 200，确认 nginx 未误拦截）"
fi

# 7) TLS 证书有效期（需 openssl 且域名公网可达）
info "7) TLS 证书有效期"
if command -v openssl >/dev/null 2>&1; then
  EXP=$(echo | openssl s_client -servername "$DOMAIN" -connect "$DOMAIN:443" 2>/dev/null \
        | openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2)
  if [[ -n "$EXP" ]]; then
    EXP_EPOCH=$(date -d "$EXP" +%s 2>/dev/null || echo 0)
    NOW=$(date +%s)
    DAYS=$(( (EXP_EPOCH - NOW) / 86400 ))
    if [[ "$DAYS" -gt 15 ]]; then
      ok "证书有效期至 $EXP（剩余 $DAYS 天）"
    else
      bad "证书将于 $EXP 过期（剩余 $DAYS 天，请尽快续期）"
    fi
  else
    bad "无法获取服务器证书（域名公网不可达或 443 未开放）"
  fi
else
  info "（跳过：未检测到 openssl）"
fi

echo "========================================="
echo "结果: ✅ $PASS 通过 / ❌ $FAIL 失败"
if [[ "$FAIL" -gt 0 ]]; then
  echo "存在失败项，请排查后再上线。"
  exit 1
else
  echo "全部通过，可上线。"
fi
