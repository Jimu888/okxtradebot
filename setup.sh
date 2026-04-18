#!/bin/bash
set -e

echo "=== OKX Compound Strategy Setup ==="

# 1. Check Node.js
if ! command -v node &>/dev/null; then
  echo "ERROR: Node.js not found. Install from https://nodejs.org (v18+)"
  exit 1
fi
echo "✓ Node.js $(node -v)"

# 2. Check Python
if ! command -v python3 &>/dev/null; then
  echo "ERROR: Python3 not found."
  exit 1
fi
echo "✓ Python $(python3 --version)"

# 3. Install OKX CLI
echo ""
echo "Installing OKX Trade CLI..."
npm install -g @okx_ai/okx-trade-cli
echo "✓ OKX CLI installed"

# 4. Install OKX official skills
echo ""
echo "Installing OKX official skills..."
npx skills add okx/agent-skills
echo "✓ OKX skills installed"

# 5. Configure OKX API keys
echo ""
echo "Configuring OKX API credentials..."
echo "You will need: API Key, Secret Key, Passphrase from OKX > API Management"
okx config init
echo "✓ OKX credentials configured"

# 6. Python dependencies
echo ""
echo "Installing Python dependencies..."
cd "$(dirname "$0")/runner"
python3 -m pip install -r requirements.txt
echo "✓ Python dependencies installed"

# 7. Setup .env
cd "$(dirname "$0")"
if [ ! -f .env ]; then
  cp .env.example .env
  echo ""
  echo "⚠️  Created .env from template."
  echo "    Edit .env and set your ANTHROPIC_API_KEY before running."
else
  echo "✓ .env already exists"
fi

echo ""
echo "=== Setup complete ==="
echo ""
echo "Next steps:"
echo "  1. Edit .env — set ANTHROPIC_API_KEY"
echo "  2. Run: python3 runner/agent_loop.py"
echo ""
echo "To run in background (24/7):"
echo "  nohup python3 runner/agent_loop.py > runner/nohup.log 2>&1 &"
echo "  echo \$! > runner/agent.pid"
echo ""
echo "To stop:"
echo "  kill \$(cat runner/agent.pid)"
