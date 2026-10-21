"""
Hostuje agenta z agent.py jako HTTP službu přes AgentRunner.serve().

Spouští ho harness.py pod ``dapr run``; samostatně:

    dapr run --app-id claude-harness --app-port 8001 \
        --dapr-http-port 3500 --dapr-grpc-port 50001 \
        --resources-path ./resources -- python app.py

Vystavené cesty (dapr-agents 1.0.9):
    POST /agent/run                               {"task": ..., "session_id": ...} -> {"instance_id", "status_url"}
    GET  /agent/instances/{instance_id}           stav workflow instance
    GET  /hitl/approvals                          čekající schválení
    POST /hitl/approvals/{approval_request_id}/respond   {"approved": bool, "reason": str}
"""

import logging
import os

from dotenv import load_dotenv

from agent import build_agent
from dapr_agents.workflow.runners import AgentRunner


def main() -> None:
    load_dotenv()
    logging.basicConfig(
        level=os.getenv("HARNESS_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if "HARNESS_LEDGER" not in os.environ:
        raise SystemExit("HARNESS_LEDGER není nastaveno – spouštěj přes harness.py")
    agent = build_agent()
    runner = AgentRunner()
    # serve() bez vlastní FastAPI instance sám spustí uvicorn a blokuje.
    runner.serve(agent, port=int(os.getenv("APP_PORT", "8001")))


if __name__ == "__main__":
    main()
