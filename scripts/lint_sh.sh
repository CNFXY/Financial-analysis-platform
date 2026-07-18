#!/usr/bin/env bash
# ============================================================
# 运维 shell 脚本静态检查包装
#   - 必做：bash -n 语法检查（bash 环境必有）
#   - 可选：shellcheck 静态检查（未安装则告警跳过，不阻断）
# 供 .pre-commit-config.yaml 与 CI 统一调用：bash scripts/lint_sh.sh <file>
# ============================================================
set -uo pipefail

f="${1:-}"
if [[ -z "$f" || ! -f "$f" ]]; then
  echo "用法: $0 <shell脚本路径>" >&2
  exit 1
fi

# 语法检查（失败即阻断）
if ! bash -n "$f"; then
  echo "❌ bash 语法错误: $f"
  exit 1
fi
echo "✓ bash -n 通过: $f"

# 静态检查（可选）
if command -v shellcheck >/dev/null 2>&1; then
  if shellcheck "$f"; then
    echo "✓ shellcheck 通过: $f"
  else
    echo "❌ shellcheck 发现问题: $f"
    exit 1
  fi
else
  echo "⚠ 未安装 shellcheck，跳过静态检查（建议 apt/brew install shellcheck）"
fi
