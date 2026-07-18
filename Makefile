# ============================================================
# FUND-OS 运维便捷命令（证书 + 健康检查 + 回归测试）
# 用法：
#   make cert                     签发证书（单域名，默认 DOMAIN）
#   make cert CERT_DOMAINS="your-domain.com *.your-domain.com"
#   make cert-renew              续期并复制 + 重载 nginx（cron 调用）
#   make check                   部署后健康检查
#   make test                    运行常驻回归套件（P0/P1/冒烟，已验证）
#   make test-all                运行全部测试（含旧接口用例，可能需完整依赖）
# ============================================================

DOMAIN       ?= pay.your-domain.com
CERT_DOMAINS ?= $(DOMAIN)
CERT_EMAIL   ?= admin@your-domain.com

# 测试环境：CI 中仓库根即包内容，需软链使 fund_estimation_system.* 可导入
ifeq ($(OS),Windows_NT)
	PYTEST := pytest
else
	PYTEST := pytest
endif

.PHONY: help cert cert-renew cert-copy check test test-all

help:
	@echo "FUND-OS 命令:"
	@echo "  make cert        签发证书（CERT_DOMAINS 可多域名 / 泛域名）"
	@echo "  make cert-renew  续期并复制 + 重载 nginx"
	@echo "  make cert-copy   仅复制已有证书并重载 nginx"
	@echo "  make check       部署后健康检查（DOMAIN=...）"
	@echo "  make test        运行常驻回归套件（P0 安全/计费、P1 限流/密码策略、端到端冒烟）"
	@echo "  make test-all    运行全部测试（含旧接口用例，需完整依赖）"
	@echo ""
	@echo "示例:"
	@echo "  make cert CERT_DOMAINS=\"your-domain.com *.your-domain.com\""
	@echo "  make check DOMAIN=pay.your-domain.com"
	@echo "  make test"

cert:
	CERT_DOMAINS="$(CERT_DOMAINS)" CERT_EMAIL="$(CERT_EMAIL)" ./scripts/renew_cert.sh issue

cert-renew:
	./scripts/renew_cert.sh renew

cert-copy:
	./scripts/renew_cert.sh copy

check:
	DOMAIN="$(DOMAIN)" ./scripts/deploy_check.sh

test:
	$(PYTEST) -m regression -v

test-all:
	$(PYTEST) -v
