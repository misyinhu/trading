#!/bin/bash
# =============================================================================
# 部署到远程服务器 — 含测试门禁 + 部署后自验
# 本地运行
# =============================================================================

set -e

REMOTE_HOST="openclaw@100.102.240.31"
REMOTE_DIR="/tmp"
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TEMP_FILE="/tmp/trading_deploy.tar.gz"

# ── 1. 测试门禁 ────────────────────────────────────────────────────────
echo "🧪 运行测试门禁..."
cd "$PROJECT_DIR"
python -m pytest tests/legacy/test_risk_gate.py tests/legacy/test_order_manager.py tests/legacy/test_signal_api.py tests/legacy/test_place_order_func.py -q --tb=short || {
    echo "❌ 测试未通过，部署中止"
    exit 1
}
echo "✅ 测试门禁通过"

# ── 2. 打包 ──────────────────────────────────────────────────────────────
echo "📦 打包项目文件..."
tar -czf "$TEMP_FILE" \
  --exclude='.git' \
  --exclude='config/settings.yaml' \
  --exclude='AGENTS.md' \
  --exclude='.DS_Store' \
  --exclude='data/z120_status.json' \
  -C "$PROJECT_DIR" .

# ── 3. 传输 ──────────────────────────────────────────────────────────────
echo "📤 传输到 $REMOTE_HOST..."
scp "$TEMP_FILE" "$REMOTE_HOST:$REMOTE_DIR/"

# ── 4. 远程部署 ──────────────────────────────────────────────────────────
echo "🚀 远程部署..."
ssh "$REMOTE_HOST" "cd ~/.openclaw/workspace/trading && tar -xzf $REMOTE_DIR/trading_deploy.tar.gz && ./scripts/deploy.sh"

# ── 5. 部署后自验 ────────────────────────────────────────────────────────
echo "🔍 部署后自验..."
sleep 3
ssh "$REMOTE_HOST" "curl -s http://localhost:5002/health | python3 -m json.tool" || echo "⚠️ 健康检查无法执行（服务可能尚未启动）"
echo ""
echo "✅ 部署流程完成"
