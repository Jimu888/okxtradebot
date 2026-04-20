# Setup on a New Machine — 1:1 Strategy Clone

Goal: get this OKX trading strategy running on a fresh machine with Claude Code in under 10 minutes.

## Prerequisites
- macOS or Linux with `node`, `npm`, `git` installed
- Claude Code installed (`claude` command available)
- A working SOCKS/HTTP proxy listening on `127.0.0.1:59527` (or whatever your proxy uses) — required for OKX CLI to reach OKX from mainland China
- Your OKX API key, secret, passphrase

## Step 1 — Clone repo

```bash
git clone https://github.com/Jimu888/okxtradebot.git ~/okx-compound-strategy
cd ~/okx-compound-strategy
```

## Step 2 — Install OKX CLI

```bash
npm install -g @okx_ai/okx-trade-cli
which okx   # should print /usr/local/bin/okx or /opt/homebrew/bin/okx
npm root -g # note this path — you'll need it in step 4
```

## Step 3 — Create OKX config

```bash
mkdir -p ~/.okx
cat > ~/.okx/config.toml << 'EOF'
default_profile = "tradebot"
proxy_url = "http://127.0.0.1:59527"

[profiles.tradebot]
api_key = "YOUR_API_KEY"
secret_key = "YOUR_SECRET"
passphrase = "YOUR_PASSPHRASE"
demo = false
EOF
```
Fill in your real OKX API credentials. **Never commit this file.**

## Step 4 — Create proxy injector

OKX CLI uses `undici` internally, which doesn't respect `https_proxy` env var. We monkey-patch via `NODE_OPTIONS --require`.

```bash
NPM_GLOBAL=$(npm root -g)
cat > ~/.okx/proxy-inject.cjs << EOF
process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0';
const { ProxyAgent, setGlobalDispatcher } = require('${NPM_GLOBAL}/@okx_ai/okx-trade-cli/node_modules/undici');
setGlobalDispatcher(new ProxyAgent('http://127.0.0.1:59527'));
EOF
```

## Step 5 — Update shell rc

```bash
cat >> ~/.zshrc << EOF

# OKX CLI proxy fix
export https_proxy=http://127.0.0.1:59527
export http_proxy=http://127.0.0.1:59527
export NODE_OPTIONS="--require $HOME/.okx/proxy-inject.cjs"
EOF
source ~/.zshrc
```

## Step 6 — Verify CLI works

```bash
okx account balance
# should print USDT, etc.
```

If it errors out, check:
- Is your proxy actually running on 59527?
- Did `npm root -g` path get expanded correctly in proxy-inject.cjs? `cat ~/.okx/proxy-inject.cjs`

## Step 7 — Place memory files where Claude Code reads them

Claude Code's auto-memory lives in `~/.claude/projects/-Users-<your-username>/memory/`. The repo includes a `memory/` folder with the strategy's persistent rules. Symlink (or copy) it:

```bash
USERNAME=$(whoami)
MEM_DIR="$HOME/.claude/projects/-Users-${USERNAME}/memory"
mkdir -p "$MEM_DIR"
cp ~/okx-compound-strategy/memory/*.md "$MEM_DIR/"
```

## Step 8 — First run with Claude Code

Inside `~/okx-compound-strategy`, start Claude Code and tell it:

```
读取 skills/okx-compound-strategy/SKILL.md 和 memory 里的 feedback_okx_*.md。
账户当前状态见 runner/strategy_log.md 末尾几个 cycle。
继续运行 OKX 复合策略 v3.14 的自主交易循环。
```

Claude will load the skill, the memory rules, and pick up from where the log left off.

## ⚠️ Two-machine warning

Running this on two machines simultaneously against the **same OKX account** will cause:
- Duplicate orders (both Claudes see "no position" and open the same trade)
- OCO sz mismatches (one machine amends, the other doesn't see)
- Race conditions on grid stops

**One-machine-at-a-time only.** If you want a hot standby, the second machine should be in read-only mode (no `okx swap place / bot grid create / swap algo place / swap close`).

## Files NOT in this repo (sensitive)

- `~/.okx/config.toml` — API credentials
- `~/.okx/proxy-inject.cjs` — has hardcoded local path
- `~/.zshrc` snippet — local

These have to be created fresh on each machine following steps 3-5 above.
