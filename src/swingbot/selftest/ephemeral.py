from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request


def _default_popen(cmd: list[str], env: dict, **kwargs):
    return subprocess.Popen(cmd, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _default_http_get(url: str, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return 200 <= r.status < 500
    except Exception:
        return False


def _default_kill(pid: int) -> None:
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass


class EphemeralApp:
    """Throwaway swingbot web instance: own port, own SWINGBOT_DATA_DIR,
    torn down after use. The live container's state is never touched.

    A pidfile under agent_dir lets the next run kill a leaked instance.
    """

    def __init__(self, port: int = 8001, agent_dir: str = "",
                 python: str = sys.executable, popen_fn=None, http_get=None,
                 kill_fn=None, startup_timeout_s: float = 30.0,
                 poll_interval_s: float = 0.5):
        self.port = port
        self.agent_dir = agent_dir
        self.python = python
        self.popen_fn = popen_fn or _default_popen
        self.http_get = http_get or _default_http_get
        self.kill_fn = kill_fn or _default_kill
        self.startup_timeout_s = startup_timeout_s
        self.poll_interval_s = poll_interval_s
        self.token = "agent-ephemeral-token"
        self.data_dir: str | None = None
        self.proc = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def _pidfile(self) -> str:
        return os.path.join(self.agent_dir, "ephemeral.pid")

    def _kill_stale(self) -> None:
        if not self.agent_dir:
            return
        try:
            with open(self._pidfile) as f:
                meta = json.load(f)
            self.kill_fn(int(meta["pid"]))
            os.remove(self._pidfile)
        except (OSError, ValueError, KeyError):
            pass

    def start(self) -> None:
        self._kill_stale()
        self.data_dir = tempfile.mkdtemp(prefix="swingbot-agent-")
        # Pre-write the token so it is known (webmain reuses an existing file).
        with open(os.path.join(self.data_dir, "token"), "w") as f:
            f.write(self.token)
        env = {**os.environ,
               "SWINGBOT_DATA_DIR": self.data_dir,
               "SWINGBOT_HOST": "127.0.0.1",
               "SWINGBOT_PORT": str(self.port)}
        self.proc = self.popen_fn([self.python, "-m", "swingbot.webmain"], env=env)
        if self.agent_dir:
            os.makedirs(self.agent_dir, exist_ok=True)
            with open(self._pidfile, "w") as f:
                json.dump({"pid": self.proc.pid, "port": self.port}, f)
        deadline = time.monotonic() + self.startup_timeout_s
        while time.monotonic() < deadline:
            rc = self.proc.poll()
            if rc is not None:
                self.stop()
                raise RuntimeError(f"ephemeral app exited rc={rc}")
            if self.http_get(f"{self.base_url}/api/state"):
                return
            time.sleep(self.poll_interval_s)
        self.stop()
        raise RuntimeError(f"ephemeral app on :{self.port} not ready "
                           f"after {self.startup_timeout_s}s (port busy?)")

    def seed_proposals(self, proposals: list[dict]) -> None:
        """Write proposal dicts straight into the ephemeral brain inbox.
        ProposalStore re-reads the file per request, so no restart is needed."""
        assert self.data_dir, "seed_proposals before start()"
        with open(os.path.join(self.data_dir, "brain_proposals.json"), "w") as f:
            json.dump(proposals, f)

    def stop(self) -> None:
        if self.proc is not None:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=10)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
            self.proc = None
        if self.agent_dir:
            try:
                os.remove(self._pidfile)
            except OSError:
                pass
        if self.data_dir:
            shutil.rmtree(self.data_dir, ignore_errors=True)
            self.data_dir = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.stop()
        return False
