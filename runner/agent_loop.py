#!/usr/bin/env python3
"""
OKX Compound Strategy Agent Loop
Reads SKILL.md and drives Claude to analyze market data and execute trades every 5 minutes.
"""

import json
import os
import subprocess
import time
import logging
from pathlib import Path
from datetime import datetime

import anthropic
from dotenv import load_dotenv

load_dotenv()

# ── Config ──────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
OKX_PROFILE = os.getenv("OKX_PROFILE", "live")
LOOP_INTERVAL = int(os.getenv("LOOP_INTERVAL_SECONDS", "300"))  # 5 minutes
MAX_TOOL_ROUNDS = 30  # max tool call rounds per cycle

BASE_DIR = Path(__file__).parent.parent
SKILL_FILE = BASE_DIR / "skills" / "okx-compound-strategy" / "SKILL.md"
STATE_FILE = BASE_DIR / "runner" / "state.json"
LOG_FILE = BASE_DIR / "runner" / "agent.log"

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

# ── State ────────────────────────────────────────────────────────────────────
DEFAULT_STATE = {
    "btc_activated": False,
    "btc_position": {
        "active": False,
        "entry_count": 0,
        "avg_entry_price": 0,
        "total_sz": 0,
        "remaining_pct": 100,
    },
    "grid_bots": [],
}


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception as e:
            log.warning(f"Failed to load state.json: {e}. Using default.")
    return DEFAULT_STATE.copy()


def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2))


# ── OKX CLI Tool ─────────────────────────────────────────────────────────────
def run_okx_command(command: str) -> str:
    """Execute an okx CLI command and return output."""
    # Inject profile if not present
    if "--profile" not in command and any(
        cmd in command
        for cmd in ["swap", "spot", "bot", "account"]
    ):
        command = command.rstrip() + f" --profile {OKX_PROFILE}"

    log.info(f"[OKX] {command}")
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = result.stdout.strip() if result.stdout else ""
        error = result.stderr.strip() if result.stderr else ""
        if result.returncode != 0 and error:
            return f"ERROR (exit {result.returncode}): {error}\n{output}"
        return output or "(no output)"
    except subprocess.TimeoutExpired:
        return "ERROR: command timed out after 30s"
    except Exception as e:
        return f"ERROR: {e}"


# ── Claude Tools Definition ──────────────────────────────────────────────────
TOOLS = [
    {
        "name": "run_okx_command",
        "description": (
            "Execute an OKX CLI command using the okx trade CLI. "
            "Use this to fetch market data, check account state, place orders, "
            "and manage grid bots. The --profile flag will be added automatically "
            "for authenticated commands. Always use --json flag for data you need "
            "to parse. Examples: 'okx market ticker BTC-USDT-SWAP', "
            "'okx market indicator RSI BTC-USDT-SWAP --period 14 --bar 5m', "
            "'okx account positions --profile live', "
            "'okx swap place --instId BTC-USDT-SWAP --side buy --ordType market "
            "--sz 10 --posSide long --tdMode isolated --profile live'"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Full okx CLI command to execute",
                }
            },
            "required": ["command"],
        },
    },
    {
        "name": "read_state",
        "description": "Read the current strategy state (positions, bot status, activation flags).",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "write_state",
        "description": "Save updated strategy state. Call this after any position change.",
        "input_schema": {
            "type": "object",
            "properties": {
                "state": {
                    "type": "object",
                    "description": "Full state object to save",
                }
            },
            "required": ["state"],
        },
    },
    {
        "name": "log_action",
        "description": "Log a significant action or decision to the agent log.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "Message to log",
                }
            },
            "required": ["message"],
        },
    },
]


def handle_tool(tool_name: str, tool_input: dict, state: dict) -> tuple[str, dict]:
    """Execute a tool call and return (result_str, updated_state)."""
    if tool_name == "run_okx_command":
        result = run_okx_command(tool_input["command"])
        return result, state

    elif tool_name == "read_state":
        return json.dumps(state, indent=2), state

    elif tool_name == "write_state":
        new_state = tool_input["state"]
        save_state(new_state)
        log.info("[STATE] Saved updated state")
        return "State saved successfully.", new_state

    elif tool_name == "log_action":
        msg = tool_input["message"]
        log.info(f"[STRATEGY] {msg}")
        return "Logged.", state

    return f"Unknown tool: {tool_name}", state


# ── Agent Cycle ──────────────────────────────────────────────────────────────
def run_cycle(client: anthropic.Anthropic, skill_content: str):
    state = load_state()
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    log.info(f"━━━ Cycle start: {now} ━━━")

    system_prompt = f"""You are an autonomous crypto trading agent executing the OKX Compound Strategy.

The full strategy specification is in the SKILL.md below. Follow it exactly.
Execute all phases every cycle: account check → BTC strategy → grid strategy.
Always save state after any position change using write_state tool.
Be precise with numbers. Never skip the stop-loss check.

Current time: {now}
OKX Profile: {OKX_PROFILE}

--- SKILL.MD START ---
{skill_content}
--- SKILL.MD END ---
"""

    user_message = (
        f"Execute one full strategy cycle now. Current state: {json.dumps(state, indent=2)}\n\n"
        "Follow the SKILL.md exactly:\n"
        "1. Account check\n"
        "2. BTC strategy (activation check, entry, exit management)\n"
        "3. Grid strategy (scan top-5, divergence check, bot management)\n"
        "4. Save final state\n"
        "Be concise in reasoning, thorough in execution."
    )

    messages = [{"role": "user", "content": user_message}]

    rounds = 0
    while rounds < MAX_TOOL_ROUNDS:
        rounds += 1
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=4096,
            system=system_prompt,
            tools=TOOLS,
            messages=messages,
        )

        # Collect text output
        for block in response.content:
            if hasattr(block, "text") and block.text:
                log.info(f"[AGENT] {block.text[:500]}")

        # Check stop condition
        if response.stop_reason == "end_turn":
            log.info("Cycle complete (end_turn).")
            break

        if response.stop_reason != "tool_use":
            log.warning(f"Unexpected stop_reason: {response.stop_reason}")
            break

        # Process tool calls
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            result, state = handle_tool(block.name, block.input, state)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": result,
            })

        # Continue conversation
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

    if rounds >= MAX_TOOL_ROUNDS:
        log.warning(f"Reached max tool rounds ({MAX_TOOL_ROUNDS}). Saving state and stopping.")
        save_state(state)

    log.info(f"━━━ Cycle end ({rounds} tool rounds) ━━━\n")


# ── Main Loop ────────────────────────────────────────────────────────────────
def main():
    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY not set in .env")

    if not SKILL_FILE.exists():
        raise FileNotFoundError(f"SKILL.md not found at {SKILL_FILE}")

    skill_content = SKILL_FILE.read_text()
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    log.info("OKX Compound Strategy Agent starting...")
    log.info(f"Loop interval: {LOOP_INTERVAL}s | Profile: {OKX_PROFILE}")
    log.info(f"Skill: {SKILL_FILE}")

    while True:
        try:
            run_cycle(client, skill_content)
        except KeyboardInterrupt:
            log.info("Interrupted by user. Exiting.")
            break
        except Exception as e:
            log.error(f"Cycle failed with error: {e}", exc_info=True)
            log.info("Waiting before retry...")

        log.info(f"Next cycle in {LOOP_INTERVAL}s...")
        time.sleep(LOOP_INTERVAL)


if __name__ == "__main__":
    main()
