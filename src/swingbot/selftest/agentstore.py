from __future__ import annotations

import json
import os


class AgentRunStore:
    """Ring of recent usage-agent runs, JSON-backed under DATA_DIR/agent/.

    Runs are plain dicts (dataclasses serialized with asdict upstream) so the
    file stays readable by the web endpoints without import coupling.
    """

    def __init__(self, agent_dir: str, cap: int = 20):
        self.agent_dir = agent_dir
        self.path = os.path.join(agent_dir, "runs.json")
        self.cap = cap

    @property
    def screenshot_dir(self) -> str:
        return os.path.join(self.agent_dir, "screenshots")

    def all(self) -> list[dict]:
        try:
            with open(self.path) as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except (OSError, ValueError):
            return []

    def latest(self) -> dict | None:
        runs = self.all()
        return runs[-1] if runs else None

    def add(self, run: dict) -> None:
        os.makedirs(self.agent_dir, exist_ok=True)
        runs = (self.all() + [run])[-self.cap:]
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(runs, f)
        os.replace(tmp, self.path)
