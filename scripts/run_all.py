"""Run the Revenue Leakage Agent (FastAPI + Chainlit on a single server)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    env = os.environ.copy()
    api_port = env.get("API_PORT", "8000")
    env.setdefault("API_HOST", "0.0.0.0")
    env.setdefault("API_PORT", api_port)
    env.setdefault("REVENUE_AGENT_API_URL", f"http://localhost:{api_port}/api")

    print(f"Revenue Leakage Agent: http://localhost:{api_port}")
    print(f"  Chat UI:  http://localhost:{api_port}/chat")
    print(f"  API docs: http://localhost:{api_port}/docs")

    cmd = [sys.executable, "-m", "revenue_agent.main"]
    try:
        proc = subprocess.run(cmd, cwd=str(repo_root), env=env)
        return proc.returncode
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
