"""
DurableAgent se smyčkou v Claude Agent SDK a trvalostí v Dapru – testovaný objekt harnessu.

Záměrně kopíruje tvar oficiálního příkladu ``examples/13-agent-executor-claude``
z dapr-agents 1.0.9, aby harness měřil chování knihovny, ne našeho kódu.
Jediný rozdíl: ``transfer_money`` zapisuje do *účetní knihy* (ledger), aby šlo
po restartu spočítat, kolikrát se nástroj se side-effectem skutečně spustil.

Proměnné prostředí (nastavuje harness.py):
    HARNESS_LEDGER            cesta k ledger.jsonl (povinné)
    CLAUDE_MODEL              výchozí claude-haiku-4-5
    APPROVAL_TIMEOUT_SECONDS  auto-deny timeout schvalování, výchozí 7 dní
    SLOW_TOOL_SECONDS         zpoždění uvnitř transfer_money mezi "start" a "end"
                              (okno pro scénář "restart během běhu nástroje")
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone

from dapr_agents import DurableAgent, tool
from dapr_agents.agents.configs import AgentExecutionConfig, AgentStateConfig
from dapr_agents.agents.executors import (
    ClaudeAgentExecutor,
    ClaudeAgentExecutorConfig,
)
from dapr_agents.hooks import (
    HookDecision,
    Hooks,
    Proceed,
    RequireApproval,
    ToolHookContext,
)
from dapr_agents.storage.daprstores.stateservice import StateStoreService

STATE_STORE = "agentstatestore"
AGENT_NAME = "ClaudeHarness"
DEFAULT_MODEL = "claude-haiku-4-5"
DEFAULT_APPROVAL_TIMEOUT = 7 * 24 * 3600
MAX_ITERATIONS = 6

# Stejné instrukce jako v oficiálním příkladu – bez nich Claude místo volání
# nástroje žádá o potvrzení v chatu a schvalovací bod nikdy nenastane.
INSTRUCTIONS = (
    "Be concise and use the available tools to answer.",
    "Call at most one tool at a time.",
    "Never retry a transfer that a human rejected.",
    "Do not ask the user to confirm a transfer. Call transfer_money directly;"
    " the system asks a human approver before any money moves.",
)

WEATHER = {
    "paris": "sunny, 22°C",
    "london": "light rain, 15°C",
    "tokyo": "cloudy, 18°C",
}


def _ledger(phase: str, **fields: object) -> None:
    """Připíše řádek do účetní knihy. Jediný side-effect v celém agentovi."""
    path = os.environ["HARNESS_LEDGER"]
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "pid": os.getpid(),
        "phase": phase,
        **fields,
    }
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


@tool
def get_weather(city: str) -> str:
    """Get the current weather for a city."""
    forecast = WEATHER.get(city.strip().lower(), "clear skies, 20°C")
    return f"The weather in {city} is {forecast}."


@tool
def transfer_money(to: str, amount: float) -> str:
    """Transfer an amount of US dollars from the user's account to a recipient."""
    _ledger("start", to=to, amount=amount)
    slow = float(os.getenv("SLOW_TOOL_SECONDS", "0") or 0)
    if slow > 0:
        time.sleep(slow)
    _ledger("end", to=to, amount=amount)
    return f"Transferred ${amount:.2f} to {to}."


def require_approval_for_transfers(ctx: ToolHookContext) -> HookDecision:
    """Každý převod čeká na člověka – to je schvalovací bod, přes který se restartuje."""
    if ctx.step_name == "transfer_money":
        timeout = int(os.getenv("APPROVAL_TIMEOUT_SECONDS", DEFAULT_APPROVAL_TIMEOUT))
        return RequireApproval(
            timeout_seconds=timeout,
            instructions=(
                f"Approve sending ${ctx.payload.get('amount')} "
                f"to {ctx.payload.get('to')}?"
            ),
        )
    return Proceed()


def build_executor() -> ClaudeAgentExecutor:
    """Jen Claude-specifické nastavení; prompt, nástroje, hooky a session store
    dodá DurableAgent při bindu."""
    return ClaudeAgentExecutor(
        ClaudeAgentExecutorConfig(
            model=os.getenv("CLAUDE_MODEL", DEFAULT_MODEL),
            max_budget_usd=float(os.getenv("CLAUDE_MAX_BUDGET_USD", "0.50")),
        )
    )


def build_agent() -> DurableAgent:
    return DurableAgent(
        name=AGENT_NAME,
        role="Personal Assistant",
        goal="Answer questions and move money only with human approval.",
        instructions=list(INSTRUCTIONS),
        executor=build_executor(),
        tools=[get_weather, transfer_money],
        hooks=Hooks(before_tool_call=[require_approval_for_transfers]),
        state=AgentStateConfig(store=StateStoreService(store_name=STATE_STORE)),
        execution=AgentExecutionConfig(max_iterations=MAX_ITERATIONS),
    )
