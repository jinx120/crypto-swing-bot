# Broker Connection Manager Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generalize the single-Alpaca credential path into a broker-agnostic Connection Manager (adapter registry, schema-driven UI, live connection test, hot-reconnect) and make web auth hands-off so the running bot needs zero manual console-token copying.

**Architecture:** A `BrokerAdapter` registry abstracts each broker behind credential-field schemas plus `make_broker`/`make_data`/`test_connection` factories. `CredentialStore` is upgraded to a versioned multi-broker file (with transparent v1→v2 migration) that delegates client construction to the active adapter — its legacy `set/status/get` signatures are preserved so every existing consumer keeps working. The supervisor and `MarketData` build their clients via the store's adapter-backed factories, and a new `supervisor.reconnect()` swaps the active broker live without losing armed strategies. Auth becomes autonomous on a trusted localhost deployment via a `SWINGBOT_TOKEN` env override plus a `/api/auth/bootstrap` endpoint the frontend self-services on load.

**Tech Stack:** Python 3 / FastAPI / pydantic / pytest; React (Vite) frontend; Alpaca SDK (`alpaca-py`); Docker Compose deployment.

## Global Constraints

- Python interpreter is **`.venv/bin/python`** (plain `python`/`pytest` are NOT on PATH). Run tests as `.venv/bin/python -m pytest -q`.
- Linter is **`.venv/bin/ruff`**. Every task must end ruff-clean: `.venv/bin/ruff check src/`.
- Frontend build gate: `cd frontend && npm run build` must be green for any task touching `frontend/`.
- **Single active broker model** — exactly one broker is "active" (connected/trading) at a time. No simultaneous multi-broker routing.
- **Back-compat is mandatory:** the existing `CredentialStore.set(key_id, secret_key, base_url)`, `status() -> {"key_id","has_secret","paper"}`, and `get() -> AlpacaCredentials | None` signatures/shapes MUST be preserved unchanged (existing tests `tests/test_credentials.py` and `tests/test_web_credentials.py` pin them). Operate on the active broker (default `"alpaca"`).
- Secrets are write-only over the API: never return a stored secret value in any status/list response.
- Work on the **`core-engine`** branch (current checkout). Baseline before this plan: **626 passed, 6 skipped**, ruff clean.
- TDD: write the failing test first, watch it fail, implement minimally, watch it pass, commit. One logical change per commit.
- **Docker rebuild policy (standing rule):** the final task rebuilds + restarts the `swingbot` container (`docker compose build swingbot && docker compose up -d swingbot`); the running container does not pick up source changes otherwise.

---

## File Structure

- **Create** `src/swingbot/broker/adapter.py` — `CredentialField`, `BrokerAdapter` protocol, `AlpacaAdapter`, `BROKER_REGISTRY`, `get_adapter()`. The only place that knows broker-specific field schemas and client construction.
- **Modify** `src/swingbot/credentials.py` — upgrade `CredentialStore` to the versioned multi-broker schema with v1→v2 migration; preserve legacy `set/status/get`; add `active/set_active/list_brokers/set_broker/broker_status/make_broker/make_data/test_broker`.
- **Modify** `src/swingbot/supervisor.py` — `build()` constructs the broker via `creds.make_broker(self.mode)`; add `reconnect()` (mirrors `set_mode`'s stop→null→rebuild under `_lifecycle_lock`).
- **Modify** `src/swingbot/data/market.py` — `_provider()` constructs the data client via `creds.make_data()`.
- **Modify** `src/swingbot/web.py` — add `GET /api/brokers`, `POST /api/brokers/{broker_id}/test`, `PUT /api/brokers/{broker_id}/credentials`, `POST /api/brokers/active`, `POST /api/brokers/reconnect`, `GET /api/auth/bootstrap`; route `_resolve_universe` through `make_broker`; thread a `local_trust` flag into `create_app`.
- **Modify** `src/swingbot/webmain.py` — `_ensure_token` prefers `SWINGBOT_TOKEN` env; pass `local_trust=os.environ.get("SWINGBOT_LOCAL_TRUST")=="1"` into `create_app`.
- **Modify** `frontend/src/api.js` — add broker/auth methods; auto-bootstrap the token on load.
- **Modify** `frontend/src/pages/Settings.jsx` — replace the hard-coded Alpaca panel with a schema-driven Broker Connection panel (select active broker, render fields from schema, Test + Save + Reconnect).
- **Modify** `docker-compose.yml` — add `SWINGBOT_TOKEN` and `SWINGBOT_LOCAL_TRUST=1` to the swingbot service env.
- **Create** tests: `tests/test_broker_adapter.py`, `tests/test_credentials_multibroker.py`, `tests/test_supervisor_reconnect.py`, `tests/test_web_brokers.py`, `tests/test_auth_bootstrap.py`.

---

## Task 1: Broker adapter layer

**Files:**
- Create: `src/swingbot/broker/adapter.py`
- Test: `tests/test_broker_adapter.py`

**Interfaces:**
- Consumes: `AlpacaBroker` (`swingbot.broker.alpaca`), `AlpacaData` (`swingbot.data.alpaca`).
- Produces:
  - `CredentialField(name: str, label: str, secret: bool = False, help: str = "")` (frozen dataclass).
  - `BrokerAdapter` protocol with: `id: str`, `label: str`, `fields: list[CredentialField]`, `modes: list[str]`, `validate(values: dict) -> None`, `base_url_for(mode: str) -> str`, `make_broker(values: dict, mode: str)`, `make_data(values: dict)`, `test_connection(values: dict, mode: str) -> dict`.
  - `AlpacaAdapter` instance implementing the protocol (`id="alpaca"`).
  - `BROKER_REGISTRY: dict[str, BrokerAdapter]` (currently `{"alpaca": AlpacaAdapter()}`).
  - `get_adapter(broker_id: str) -> BrokerAdapter` (raises `KeyError`→`ValueError` for unknown id).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_broker_adapter.py
import pytest
from swingbot.broker.adapter import (
    CredentialField, get_adapter, BROKER_REGISTRY,
)


def test_alpaca_adapter_schema():
    a = get_adapter("alpaca")
    assert a.id == "alpaca"
    assert a.label
    assert a.modes == ["paper", "live"]
    names = [f.name for f in a.fields]
    assert names == ["key_id", "secret_key"]
    secret_flags = {f.name: f.secret for f in a.fields}
    assert secret_flags == {"key_id": False, "secret_key": True}
    assert all(isinstance(f, CredentialField) for f in a.fields)


def test_alpaca_base_url_for_mode():
    a = get_adapter("alpaca")
    assert "paper" in a.base_url_for("paper")
    assert "paper" not in a.base_url_for("live")


def test_alpaca_validate_rejects_missing_fields():
    a = get_adapter("alpaca")
    with pytest.raises(ValueError):
        a.validate({"key_id": "K"})            # secret_key missing
    a.validate({"key_id": "K", "secret_key": "S"})   # ok, no raise


def test_make_broker_and_data_use_values(monkeypatch):
    a = get_adapter("alpaca")
    captured = {}

    class FakeClient:
        def __init__(self, *args, **kw): captured["args"] = args; captured["kw"] = kw

    monkeypatch.setattr("swingbot.broker.alpaca.TradingClient", FakeClient)
    monkeypatch.setattr("swingbot.data.alpaca.CryptoHistoricalDataClient", FakeClient)
    a.make_broker({"key_id": "K", "secret_key": "S"}, "paper")
    a.make_data({"key_id": "K", "secret_key": "S"})
    assert ("K", "S") == captured["args"][:2]


def test_registry_unknown_broker_raises():
    with pytest.raises(ValueError):
        get_adapter("nope")
    assert "alpaca" in BROKER_REGISTRY


def test_test_connection_reports_ok_and_failure(monkeypatch):
    a = get_adapter("alpaca")

    class GoodBroker:
        def __init__(self, *a, **k): pass
        def get_account(self): return {"equity": 1000.0}

    monkeypatch.setattr("swingbot.broker.adapter.AlpacaBroker", GoodBroker)
    res = a.test_connection({"key_id": "K", "secret_key": "S"}, "paper")
    assert res["ok"] is True
    assert "1000" in res["detail"]

    class BadBroker:
        def __init__(self, *a, **k): pass
        def get_account(self): raise RuntimeError("401 unauthorized")

    monkeypatch.setattr("swingbot.broker.adapter.AlpacaBroker", BadBroker)
    res = a.test_connection({"key_id": "K", "secret_key": "S"}, "paper")
    assert res["ok"] is False
    assert "401" in res["detail"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_broker_adapter.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.broker.adapter'`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/swingbot/broker/adapter.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from swingbot.broker.alpaca import AlpacaBroker
from swingbot.data.alpaca import AlpacaData


@dataclass(frozen=True)
class CredentialField:
    name: str
    label: str
    secret: bool = False
    help: str = ""


@runtime_checkable
class BrokerAdapter(Protocol):
    id: str
    label: str
    fields: list[CredentialField]
    modes: list[str]

    def validate(self, values: dict) -> None: ...
    def base_url_for(self, mode: str) -> str: ...
    def make_broker(self, values: dict, mode: str): ...
    def make_data(self, values: dict): ...
    def test_connection(self, values: dict, mode: str) -> dict: ...


@dataclass
class AlpacaAdapter:
    id: str = "alpaca"
    label: str = "Alpaca"
    modes: list[str] = field(default_factory=lambda: ["paper", "live"])
    fields: list[CredentialField] = field(default_factory=lambda: [
        CredentialField("key_id", "Key ID", secret=False,
                        help="Public identifier of your Alpaca API key pair."),
        CredentialField("secret_key", "Secret Key", secret=True,
                        help="Private half of the key pair — treated like a password, write-only."),
    ])

    def validate(self, values: dict) -> None:
        for f in self.fields:
            if not values.get(f.name):
                raise ValueError(f"missing required field {f.name!r}")

    def base_url_for(self, mode: str) -> str:
        return ("https://paper-api.alpaca.markets" if mode == "paper"
                else "https://api.alpaca.markets")

    def make_broker(self, values: dict, mode: str):
        self.validate(values)
        return AlpacaBroker(values["key_id"], values["secret_key"], paper=(mode == "paper"))

    def make_data(self, values: dict):
        self.validate(values)
        return AlpacaData(values["key_id"], values["secret_key"])

    def test_connection(self, values: dict, mode: str) -> dict:
        try:
            self.validate(values)
            broker = AlpacaBroker(values["key_id"], values["secret_key"],
                                  paper=(mode == "paper"))
            acct = broker.get_account()
            return {"ok": True, "detail": f"connected; equity={acct.get('equity')}"}
        except Exception as exc:  # any SDK/credential failure -> truthful, never raises
            return {"ok": False, "detail": str(exc)}


BROKER_REGISTRY: dict[str, BrokerAdapter] = {"alpaca": AlpacaAdapter()}


def get_adapter(broker_id: str) -> BrokerAdapter:
    try:
        return BROKER_REGISTRY[broker_id]
    except KeyError:
        raise ValueError(f"unknown broker {broker_id!r}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_broker_adapter.py -q && .venv/bin/ruff check src/`
Expected: PASS, ruff clean.

- [ ] **Step 5: Commit**

```bash
git add src/swingbot/broker/adapter.py tests/test_broker_adapter.py
git commit -m "feat(broker): add broker adapter registry with Alpaca adapter"
```

---

## Task 2: CredentialStore v2 schema + transparent migration

**Files:**
- Modify: `src/swingbot/credentials.py`
- Test: `tests/test_credentials_multibroker.py`

**Interfaces:**
- Consumes: `get_adapter`, `BROKER_REGISTRY` (Task 1); `AlpacaCredentials` (`swingbot.config`).
- Produces (additions to `CredentialStore`, all legacy methods unchanged):
  - Internal file schema v2: `{"version": 2, "active": "alpaca", "brokers": {"alpaca": {"key_id","secret_key","base_url"}}}`.
  - `active() -> str` (defaults `"alpaca"`).
  - `_load()` transparently migrates a legacy flat `{key_id,secret_key,base_url}` doc to v2 in memory.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_credentials_multibroker.py
import json
from swingbot.credentials import CredentialStore


def test_legacy_v1_file_migrates_on_load(tmp_path):
    path = tmp_path / "creds.json"
    path.write_text(json.dumps({"key_id": "OLD", "secret_key": "S",
                                "base_url": "https://api.alpaca.markets"}))
    c = CredentialStore(str(path))
    assert c.active() == "alpaca"
    st = c.status()                      # legacy shape preserved
    assert st["key_id"] == "OLD"
    assert st["has_secret"] is True
    assert st["paper"] is False
    full = c.get()
    assert full.key_id == "OLD" and full.paper is False


def test_set_writes_v2_schema_under_active_broker(tmp_path):
    path = tmp_path / "creds.json"
    c = CredentialStore(str(path))
    c.set("KID", "SECRET", "https://paper-api.alpaca.markets")
    raw = json.loads(path.read_text())
    assert raw["version"] == 2
    assert raw["active"] == "alpaca"
    assert raw["brokers"]["alpaca"]["key_id"] == "KID"


def test_active_defaults_to_alpaca_when_unset(tmp_path):
    c = CredentialStore(str(tmp_path / "creds.json"))
    assert c.active() == "alpaca"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_credentials_multibroker.py -q`
Expected: FAIL — `AttributeError: 'CredentialStore' object has no attribute 'active'`.

- [ ] **Step 3: Write minimal implementation**

Replace the entire body of `src/swingbot/credentials.py` with:

```python
from __future__ import annotations

import json
import os

from swingbot.config import AlpacaCredentials

_DEFAULT_BROKER = "alpaca"


class CredentialStore:
    """Versioned multi-broker credential file (chmod 600). Exactly one broker is
    active. Legacy flat {key_id,secret_key,base_url} files migrate transparently
    to v2 on load. Secrets are never exposed via status()/broker_status()."""

    def __init__(self, path: str):
        self.path = path

    # ---- file IO + migration ----
    def _raw(self) -> dict | None:
        if not os.path.exists(self.path):
            return None
        with open(self.path) as f:
            return json.load(f)

    def _load(self) -> dict:
        """Always returns a normalized v2 doc (migrating legacy in memory)."""
        raw = self._raw()
        if not raw:
            return {"version": 2, "active": _DEFAULT_BROKER, "brokers": {}}
        if raw.get("version") == 2 and "brokers" in raw:
            raw.setdefault("active", _DEFAULT_BROKER)
            return raw
        # legacy v1: flat alpaca creds
        broker = {k: raw.get(k) for k in ("key_id", "secret_key", "base_url")
                  if raw.get(k) is not None}
        return {"version": 2, "active": _DEFAULT_BROKER,
                "brokers": {_DEFAULT_BROKER: broker} if broker else {}}

    def _save(self, doc: dict) -> None:
        with open(self.path, "w") as f:
            json.dump(doc, f)
        os.chmod(self.path, 0o600)

    def active(self) -> str:
        return self._load().get("active", _DEFAULT_BROKER)

    # ---- legacy API (operates on the active broker; signatures unchanged) ----
    def set(self, key_id: str, secret_key: str, base_url: str) -> None:
        doc = self._load()
        doc["active"] = _DEFAULT_BROKER
        doc["brokers"][_DEFAULT_BROKER] = {
            "key_id": key_id, "secret_key": secret_key, "base_url": base_url}
        self._save(doc)

    def status(self) -> dict:
        d = self._load()["brokers"].get(self.active())
        if not d:
            return {"key_id": None, "has_secret": False, "paper": True}
        return {
            "key_id": d.get("key_id"),
            "has_secret": bool(d.get("secret_key")),
            "paper": "paper" in d.get("base_url", "paper"),
        }

    def get(self) -> AlpacaCredentials | None:
        d = self._load()["brokers"].get(self.active())
        if not d or not d.get("key_id") or not d.get("secret_key"):
            return None
        base_url = d.get("base_url", "https://paper-api.alpaca.markets")
        return AlpacaCredentials(key_id=d["key_id"], secret_key=d["secret_key"],
                                 base_url=base_url, paper="paper" in base_url)
```

- [ ] **Step 4: Run the new + legacy credential tests**

Run: `.venv/bin/python -m pytest tests/test_credentials_multibroker.py tests/test_credentials.py -q && .venv/bin/ruff check src/`
Expected: PASS (both new and the 4 legacy tests), ruff clean.

- [ ] **Step 5: Commit**

```bash
git add src/swingbot/credentials.py tests/test_credentials_multibroker.py
git commit -m "feat(credentials): versioned multi-broker store with v1->v2 migration"
```

---

## Task 3: CredentialStore multi-broker management methods

**Files:**
- Modify: `src/swingbot/credentials.py`
- Test: `tests/test_credentials_multibroker.py` (extend)

**Interfaces:**
- Consumes: `BROKER_REGISTRY`, `get_adapter` (Task 1).
- Produces (new methods):
  - `set_active(broker_id: str) -> None` (validates against registry).
  - `set_broker(broker_id: str, values: dict) -> None` (validates via adapter, persists under `brokers[broker_id]`).
  - `broker_status(broker_id: str) -> dict` — `{"broker", "configured", "fields": {name: {"set": bool, "value": <public-or-None>}}}`; secret values never returned.
  - `list_brokers() -> dict` — `{"active": str, "brokers": [{"id","label","modes","configured","fields":[{"name","label","secret","help"}],"status": <broker_status>}]}`.

- [ ] **Step 1: Write the failing test (append to tests/test_credentials_multibroker.py)**

```python
def test_set_broker_and_status_hides_secret(tmp_path):
    c = CredentialStore(str(tmp_path / "creds.json"))
    c.set_broker("alpaca", {"key_id": "KID", "secret_key": "SECRET",
                            "base_url": "https://paper-api.alpaca.markets"})
    st = c.broker_status("alpaca")
    assert st["configured"] is True
    assert st["fields"]["key_id"]["set"] is True
    assert st["fields"]["key_id"]["value"] == "KID"      # public field shown
    assert st["fields"]["secret_key"]["set"] is True
    assert st["fields"]["secret_key"]["value"] is None   # secret never shown
    assert "SECRET" not in str(st)


def test_set_active_validates_and_persists(tmp_path):
    import pytest
    c = CredentialStore(str(tmp_path / "creds.json"))
    with pytest.raises(ValueError):
        c.set_active("nope")
    c.set_active("alpaca")
    assert c.active() == "alpaca"


def test_list_brokers_returns_registry_with_schema(tmp_path):
    c = CredentialStore(str(tmp_path / "creds.json"))
    out = c.list_brokers()
    assert out["active"] == "alpaca"
    ids = [b["id"] for b in out["brokers"]]
    assert "alpaca" in ids
    alpaca = next(b for b in out["brokers"] if b["id"] == "alpaca")
    assert alpaca["configured"] is False
    assert [f["name"] for f in alpaca["fields"]] == ["key_id", "secret_key"]
    assert {f["name"]: f["secret"] for f in alpaca["fields"]}["secret_key"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_credentials_multibroker.py -q`
Expected: FAIL — `AttributeError: 'CredentialStore' object has no attribute 'set_broker'`.

- [ ] **Step 3: Add the methods to `CredentialStore`**

Add this import near the top of `src/swingbot/credentials.py` (after the existing imports):

```python
from swingbot.broker.adapter import BROKER_REGISTRY, get_adapter
```

Append these methods to the `CredentialStore` class:

```python
    # ---- multi-broker management ----
    def set_active(self, broker_id: str) -> None:
        get_adapter(broker_id)                 # raises ValueError if unknown
        doc = self._load()
        doc["active"] = broker_id
        self._save(doc)

    def set_broker(self, broker_id: str, values: dict) -> None:
        adapter = get_adapter(broker_id)
        adapter.validate(values)
        doc = self._load()
        stored = {f.name: values.get(f.name) for f in adapter.fields}
        if "base_url" in values:
            stored["base_url"] = values["base_url"]
        doc["brokers"][broker_id] = stored
        self._save(doc)

    def broker_status(self, broker_id: str) -> dict:
        adapter = get_adapter(broker_id)
        stored = self._load()["brokers"].get(broker_id, {})
        fields = {}
        for f in adapter.fields:
            present = bool(stored.get(f.name))
            fields[f.name] = {"set": present,
                              "value": (stored.get(f.name) if (present and not f.secret)
                                        else None)}
        configured = all(fields[f.name]["set"] for f in adapter.fields)
        return {"broker": broker_id, "configured": configured, "fields": fields}

    def list_brokers(self) -> dict:
        brokers = []
        for bid, adapter in BROKER_REGISTRY.items():
            st = self.broker_status(bid)
            brokers.append({
                "id": bid, "label": adapter.label, "modes": list(adapter.modes),
                "configured": st["configured"],
                "fields": [{"name": f.name, "label": f.label,
                            "secret": f.secret, "help": f.help} for f in adapter.fields],
                "status": st})
        return {"active": self.active(), "brokers": brokers}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_credentials_multibroker.py -q && .venv/bin/ruff check src/`
Expected: PASS, ruff clean.

- [ ] **Step 5: Commit**

```bash
git add src/swingbot/credentials.py tests/test_credentials_multibroker.py
git commit -m "feat(credentials): broker listing, status, set_broker, set_active"
```

---

## Task 4: Adapter-backed client factories on CredentialStore

**Files:**
- Modify: `src/swingbot/credentials.py`
- Test: `tests/test_credentials_multibroker.py` (extend)

**Interfaces:**
- Consumes: `get_adapter` (Task 1).
- Produces:
  - `make_broker(mode: str | None = None)` — builds the active broker's client via its adapter; `None` if unconfigured. `mode` defaults to the stored paper/live setting.
  - `make_data()` — builds the active broker's data client; `None` if unconfigured.
  - `test_broker(broker_id: str, values: dict | None = None, mode: str | None = None) -> dict` — live probe via adapter; if `values` is `None`, uses stored values.

- [ ] **Step 1: Write the failing test (append)**

```python
def test_make_broker_none_when_unconfigured(tmp_path):
    c = CredentialStore(str(tmp_path / "creds.json"))
    assert c.make_broker() is None
    assert c.make_data() is None


def test_make_broker_builds_via_adapter(tmp_path, monkeypatch):
    c = CredentialStore(str(tmp_path / "creds.json"))
    c.set("KID", "SECRET", "https://paper-api.alpaca.markets")
    captured = {}

    class FakeClient:
        def __init__(self, *args, **kw): captured["args"] = args; captured["kw"] = kw

    monkeypatch.setattr("swingbot.broker.alpaca.TradingClient", FakeClient)
    monkeypatch.setattr("swingbot.data.alpaca.CryptoHistoricalDataClient", FakeClient)
    assert c.make_broker() is not None
    assert captured["args"][:2] == ("KID", "SECRET")
    assert c.make_data() is not None


def test_make_broker_mode_override(tmp_path, monkeypatch):
    c = CredentialStore(str(tmp_path / "creds.json"))
    c.set("KID", "SECRET", "https://paper-api.alpaca.markets")
    seen = {}

    class FakeTrading:
        def __init__(self, *a, **kw): seen["paper"] = kw.get("paper")

    monkeypatch.setattr("swingbot.broker.alpaca.TradingClient", FakeTrading)
    c.make_broker(mode="live")
    assert seen["paper"] is False


def test_test_broker_uses_stored_values(tmp_path, monkeypatch):
    c = CredentialStore(str(tmp_path / "creds.json"))
    c.set("KID", "SECRET", "https://paper-api.alpaca.markets")

    class GoodBroker:
        def __init__(self, *a, **k): pass
        def get_account(self): return {"equity": 500.0}

    monkeypatch.setattr("swingbot.broker.adapter.AlpacaBroker", GoodBroker)
    res = c.test_broker("alpaca")
    assert res["ok"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_credentials_multibroker.py -q`
Expected: FAIL — `AttributeError: ... 'make_broker'`.

- [ ] **Step 3: Append factory methods to `CredentialStore`**

```python
    # ---- adapter-backed client factories ----
    def _active_values(self) -> tuple[str, dict] | None:
        bid = self.active()
        stored = self._load()["brokers"].get(bid)
        if not stored:
            return None
        return bid, stored

    def _stored_mode(self, stored: dict) -> str:
        return "paper" if "paper" in stored.get("base_url", "paper") else "live"

    def make_broker(self, mode: str | None = None):
        av = self._active_values()
        if av is None:
            return None
        bid, stored = av
        adapter = get_adapter(bid)
        try:
            return adapter.make_broker(stored, mode or self._stored_mode(stored))
        except ValueError:
            return None

    def make_data(self):
        av = self._active_values()
        if av is None:
            return None
        bid, stored = av
        adapter = get_adapter(bid)
        try:
            return adapter.make_data(stored)
        except ValueError:
            return None

    def test_broker(self, broker_id: str, values: dict | None = None,
                    mode: str | None = None) -> dict:
        adapter = get_adapter(broker_id)
        if values is None:
            values = self._load()["brokers"].get(broker_id, {})
        resolved_mode = mode or self._stored_mode(values)
        return adapter.test_connection(values, resolved_mode)
```

- [ ] **Step 4: Run the full credential suite**

Run: `.venv/bin/python -m pytest tests/test_credentials_multibroker.py tests/test_credentials.py -q && .venv/bin/ruff check src/`
Expected: PASS, ruff clean.

- [ ] **Step 5: Commit**

```bash
git add src/swingbot/credentials.py tests/test_credentials_multibroker.py
git commit -m "feat(credentials): adapter-backed make_broker/make_data/test_broker"
```

---

## Task 5: Supervisor builds via make_broker + hot-reconnect

**Files:**
- Modify: `src/swingbot/supervisor.py` (`build()` at ~line 260; add `reconnect()` near `set_mode` at ~line 980)
- Test: `tests/test_supervisor_reconnect.py`

**Interfaces:**
- Consumes: `creds.make_broker(mode)` (Task 4); existing `_lifecycle_lock`, `_state_lock`, `stop()`, `start()`, `build()`.
- Produces: `PortfolioSupervisor.reconnect() -> tuple[bool, str]` — stop (if running) → invalidate `_broker` → rebuild from the now-current active credentials, preserving armed strategies and running-desired.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_supervisor_reconnect.py
from swingbot.supervisor import PortfolioSupervisor


class _Creds:
    """make_broker returns a fresh sentinel each call; lets us prove reconnect rebuilt."""
    def __init__(self): self.calls = 0
    def get(self):
        return None
    def make_broker(self, mode=None):
        self.calls += 1
        return ("broker", self.calls)


def _sup(tmp_path, creds):
    return PortfolioSupervisor(
        profiles=_Profiles(), creds=creds,
        state_db=str(tmp_path / "s.db"), market=_Market())


class _Profiles:
    def list_armed(self): return []
    def get_portfolio_settings(self): return {}
    def get_rebalance_settings(self): return {}
    def get_rebalance_targets(self): return {}
    def get(self, name): return None


class _Market:
    pass


def test_build_uses_make_broker(tmp_path):
    creds = _Creds()
    sup = _sup(tmp_path, creds)
    sup.build()
    assert sup._broker == ("broker", 1)


def test_reconnect_rebuilds_broker_when_idle(tmp_path):
    creds = _Creds()
    sup = _sup(tmp_path, creds)
    sup.build()
    assert creds.calls == 1
    ok, msg = sup.reconnect()
    assert ok is True
    assert creds.calls == 2          # broker was rebuilt with fresh creds
    assert sup._broker == ("broker", 2)


def test_reconnect_reports_failure_when_unconfigured(tmp_path):
    class _NoCreds(_Creds):
        def make_broker(self, mode=None): return None
    sup = _sup(tmp_path, _NoCreds())
    ok, msg = sup.reconnect()
    assert ok is False
    assert "credentials" in msg.lower() or "reconnect" in msg.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_supervisor_reconnect.py -q`
Expected: FAIL — `test_build_uses_make_broker` fails (build still calls `AlpacaBroker` directly) and `reconnect` is undefined.

- [ ] **Step 3: Update `build()` broker construction**

In `src/swingbot/supervisor.py`, replace the broker-construction block inside `build()` (currently):

```python
        if self._broker is None:
            c = self.creds.get() if self.creds else None
            if c is None:
                raise RuntimeError("Alpaca credentials not set")
            self._broker = AlpacaBroker(c.key_id, c.secret_key, paper=(self.mode == "paper"))
```

with:

```python
        if self._broker is None:
            broker = self.creds.make_broker(mode=self.mode) if self.creds else None
            if broker is None:
                raise RuntimeError("Alpaca credentials not set")
            self._broker = broker
```

- [ ] **Step 4: Add `reconnect()` immediately after `set_mode()`**

```python
    def reconnect(self) -> tuple[bool, str]:
        """Rebuild the broker (and downstream data clients re-read creds on demand)
        from the now-current active credentials. Preserves armed strategies and
        running-desired; restarts the loop if it was running. Mirrors set_mode."""
        with self._lifecycle_lock:
            with self._state_lock:
                was_running = self._running
            if not self.stop():
                return (False, "previous loop thread still alive; not reconnected")
            with self._state_lock:
                self._broker = None
            try:
                if was_running:
                    self.start()
                else:
                    self.build()
            except Exception as e:
                return (False, f"reconnect failed: {e}")
            return (True, "reconnected")
```

- [ ] **Step 5: Run tests + full suite slice**

Run: `.venv/bin/python -m pytest tests/test_supervisor_reconnect.py tests/test_supervisor.py tests/test_supervisor_control.py -q && .venv/bin/ruff check src/`
Expected: PASS, ruff clean.

- [ ] **Step 6: Commit**

```bash
git add src/swingbot/supervisor.py tests/test_supervisor_reconnect.py
git commit -m "feat(supervisor): build via make_broker + hot reconnect()"
```

---

## Task 6: MarketData data client via make_data

**Files:**
- Modify: `src/swingbot/data/market.py` (`_provider()` at ~line 75)
- Test: `tests/test_market_provider.py`

**Interfaces:**
- Consumes: `creds.make_data()` (Task 4).
- Produces: `MarketData._provider()` returns `creds.make_data()` (or `None`), no longer constructs `AlpacaData` directly.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_market_provider.py
from swingbot.data.market import MarketData


class _Store:
    def get(self, *a, **k): return []


class _Creds:
    def __init__(self, provider): self._p = provider; self.calls = 0
    def make_data(self):
        self.calls += 1
        return self._p


def test_provider_delegates_to_make_data():
    sentinel = object()
    creds = _Creds(sentinel)
    md = MarketData(_Store(), creds)
    assert md._provider() is sentinel
    assert creds.calls == 1


def test_provider_none_when_unconfigured():
    creds = _Creds(None)
    md = MarketData(_Store(), creds)
    assert md._provider() is None


def test_provider_none_when_no_creds():
    md = MarketData(_Store(), None)
    assert md._provider() is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_market_provider.py -q`
Expected: FAIL — `_provider` still calls `self.creds.get()` then `AlpacaData(...)`; `_Creds` here has no `get`.

- [ ] **Step 3: Replace `_provider()`**

In `src/swingbot/data/market.py`, replace:

```python
    def _provider(self) -> AlpacaData | None:
        c = self.creds.get() if self.creds else None
        if not c:
            return None
        return AlpacaData(c.key_id, c.secret_key)
```

with:

```python
    def _provider(self):
        if not self.creds:
            return None
        return self.creds.make_data()
```

The `from swingbot.data.alpaca import AlpacaData` import at the top of `market.py` is now unused — remove it (ruff `F401` will flag it otherwise).

- [ ] **Step 4: Run tests + market/data slice**

Run: `.venv/bin/python -m pytest tests/test_market_provider.py -q && .venv/bin/ruff check src/`
Expected: PASS, ruff clean.

- [ ] **Step 5: Commit**

```bash
git add src/swingbot/data/market.py tests/test_market_provider.py
git commit -m "feat(market): build data client via creds.make_data()"
```

---

## Task 7: Broker Connection Manager web endpoints

**Files:**
- Modify: `src/swingbot/web.py` (add endpoints after the existing `# ---- credentials ----` block ~line 324; update `_resolve_universe` ~line 262)
- Test: `tests/test_web_brokers.py`

**Interfaces:**
- Consumes: `creds.list_brokers/set_broker/set_active/test_broker/make_broker` (Tasks 3–4); `controller.reconnect()` (Task 5).
- Produces endpoints:
  - `GET /api/brokers` → `creds.list_brokers()`.
  - `PUT /api/brokers/{broker_id}/credentials` (auth) — body `{"values": dict}` → `creds.set_broker`.
  - `POST /api/brokers/{broker_id}/test` (auth) — body `{"values": dict | null, "mode": str | null}` → `creds.test_broker`.
  - `POST /api/brokers/active` (auth) — body `{"broker_id": str}` → `creds.set_active`.
  - `POST /api/brokers/reconnect` (auth) → `controller.reconnect()` → `{"ok","detail"}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_web_brokers.py
from fastapi.testclient import TestClient
from swingbot.web import create_app
from swingbot.credentials import CredentialStore


class FakeController:
    def __init__(self): self.reconnected = False
    def status(self): return {}
    def reconnect(self): self.reconnected = True; return (True, "reconnected")


def _client(tmp_path, token="tok"):
    creds = CredentialStore(str(tmp_path / "creds.json"))
    ctl = FakeController()
    app = create_app(controller=ctl, profiles=None, creds=creds, token=token)
    return TestClient(app), creds, ctl


def test_list_brokers(tmp_path):
    c, _, _ = _client(tmp_path)
    body = c.get("/api/brokers").json()
    assert body["active"] == "alpaca"
    assert any(b["id"] == "alpaca" for b in body["brokers"])


def test_put_broker_credentials_requires_token(tmp_path):
    c, _, _ = _client(tmp_path)
    r = c.put("/api/brokers/alpaca/credentials",
              json={"values": {"key_id": "K", "secret_key": "S"}})
    assert r.status_code == 401


def test_put_broker_credentials_saves(tmp_path):
    c, creds, _ = _client(tmp_path)
    r = c.put("/api/brokers/alpaca/credentials", headers={"X-Token": "tok"},
              json={"values": {"key_id": "K", "secret_key": "S",
                               "base_url": "https://paper-api.alpaca.markets"}})
    assert r.status_code == 200
    assert creds.broker_status("alpaca")["configured"] is True
    assert "S" not in r.text


def test_set_active_broker(tmp_path):
    c, creds, _ = _client(tmp_path)
    r = c.post("/api/brokers/active", headers={"X-Token": "tok"},
               json={"broker_id": "alpaca"})
    assert r.status_code == 200
    assert creds.active() == "alpaca"
    bad = c.post("/api/brokers/active", headers={"X-Token": "tok"},
                 json={"broker_id": "nope"})
    assert bad.status_code == 400


def test_reconnect_calls_controller(tmp_path):
    c, _, ctl = _client(tmp_path)
    r = c.post("/api/brokers/reconnect", headers={"X-Token": "tok"})
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert ctl.reconnected is True


def test_test_connection_endpoint(tmp_path, monkeypatch):
    c, _, _ = _client(tmp_path)

    class GoodBroker:
        def __init__(self, *a, **k): pass
        def get_account(self): return {"equity": 123.0}

    monkeypatch.setattr("swingbot.broker.adapter.AlpacaBroker", GoodBroker)
    r = c.post("/api/brokers/alpaca/test", headers={"X-Token": "tok"},
               json={"values": {"key_id": "K", "secret_key": "S"}, "mode": "paper"})
    assert r.status_code == 200
    assert r.json()["ok"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_web_brokers.py -q`
Expected: FAIL — 404s (endpoints not defined).

- [ ] **Step 3: Add request models + endpoints to `web.py`**

Add these pydantic models near the other `BaseModel` classes (after `CredBody`):

```python
class BrokerCredBody(BaseModel):
    values: dict


class BrokerTestBody(BaseModel):
    values: dict | None = None
    mode: str | None = None


class ActiveBrokerBody(BaseModel):
    broker_id: str
```

Insert these routes right after the existing `set_creds` route (after the `# ---- credentials ----` block):

```python
    # ---- broker connection manager ----
    @app.get("/api/brokers")
    def list_brokers():
        return creds.list_brokers()

    @app.put("/api/brokers/{broker_id}/credentials")
    def set_broker_credentials(broker_id: str, body: BrokerCredBody,
                               _=Depends(require_token)):
        try:
            creds.set_broker(broker_id, body.values)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"ok": True}

    @app.post("/api/brokers/{broker_id}/test")
    def test_broker(broker_id: str, body: BrokerTestBody, _=Depends(require_token)):
        try:
            return creds.test_broker(broker_id, body.values, body.mode)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.post("/api/brokers/active")
    def set_active_broker(body: ActiveBrokerBody, _=Depends(require_token)):
        try:
            creds.set_active(body.broker_id)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"ok": True, "active": creds.active()}

    @app.post("/api/brokers/reconnect")
    def reconnect_broker(_=Depends(require_token)):
        if not hasattr(controller, "reconnect"):
            raise HTTPException(status_code=503, detail="reconnect not supported")
        ok, detail = controller.reconnect()
        return {"ok": ok, "detail": detail}
```

Then update `_resolve_universe` to use the adapter-backed factory. Replace:

```python
            cr = creds.get() if creds is not None else None
            if cr is not None:
                broker = AlpacaBroker(cr.key_id, cr.secret_key, paper=True)
                live = broker.list_usd_pairs()
```

with:

```python
            broker = creds.make_broker(mode="paper") if creds is not None else None
            if broker is not None and hasattr(broker, "list_usd_pairs"):
                live = broker.list_usd_pairs()
```

The `from swingbot.broker.alpaca import AlpacaBroker` import at the top of `web.py` is now unused — remove it (ruff `F401`).

- [ ] **Step 4: Run tests + existing web credential/universe tests**

Run: `.venv/bin/python -m pytest tests/test_web_brokers.py tests/test_web_credentials.py tests/test_web_universe.py -q && .venv/bin/ruff check src/`
Expected: PASS, ruff clean.

- [ ] **Step 5: Commit**

```bash
git add src/swingbot/web.py tests/test_web_brokers.py
git commit -m "feat(web): broker connection manager endpoints + reconnect"
```

---

## Task 8: Autonomous auth — SWINGBOT_TOKEN env + /api/auth/bootstrap

**Files:**
- Modify: `src/swingbot/webmain.py` (`_ensure_token` ~line 25; `create_app(...)` call ~line 115)
- Modify: `src/swingbot/web.py` (`create_app` signature; add `/api/auth/bootstrap`)
- Modify: `docker-compose.yml`
- Test: `tests/test_auth_bootstrap.py`

**Interfaces:**
- Consumes: `os.environ` (`SWINGBOT_TOKEN`, `SWINGBOT_LOCAL_TRUST`).
- Produces:
  - `_ensure_token(path)` prefers `SWINGBOT_TOKEN` env when set (returns it without generating a file token).
  - `create_app(..., local_trust: bool = False)`.
  - `GET /api/auth/bootstrap` → `{"token": <token>}` when `local_trust` is True, else HTTP 403. **Never** token-gated (it bootstraps the token).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_auth_bootstrap.py
from fastapi.testclient import TestClient
from swingbot.web import create_app
from swingbot.webmain import _ensure_token


class FakeController:
    def status(self): return {}


def _app(tmp_path, local_trust):
    creds = None
    return create_app(controller=FakeController(), profiles=None, creds=_NullCreds(),
                      token="secret-tok", local_trust=local_trust)


class _NullCreds:
    def status(self): return {"key_id": None, "has_secret": False, "paper": True}


def test_bootstrap_returns_token_when_trusted(tmp_path):
    c = TestClient(_app(tmp_path, local_trust=True))
    r = c.get("/api/auth/bootstrap")
    assert r.status_code == 200
    assert r.json()["token"] == "secret-tok"


def test_bootstrap_forbidden_when_untrusted(tmp_path):
    c = TestClient(_app(tmp_path, local_trust=False))
    r = c.get("/api/auth/bootstrap")
    assert r.status_code == 403


def test_ensure_token_prefers_env(tmp_path, monkeypatch):
    monkeypatch.setenv("SWINGBOT_TOKEN", "pinned-token")
    tok = _ensure_token(str(tmp_path / "token"))
    assert tok == "pinned-token"
    assert not (tmp_path / "token").exists()   # env path writes no file


def test_ensure_token_falls_back_to_file(tmp_path, monkeypatch):
    monkeypatch.delenv("SWINGBOT_TOKEN", raising=False)
    tok = _ensure_token(str(tmp_path / "token"))
    assert tok and (tmp_path / "token").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_auth_bootstrap.py -q`
Expected: FAIL — `create_app` has no `local_trust` kwarg; no `/api/auth/bootstrap`.

- [ ] **Step 3: Update `_ensure_token` in `webmain.py`**

Replace:

```python
def _ensure_token(path: str) -> str:
    if os.path.exists(path):
        with open(path) as f:
            return f.read().strip()
    tok = secrets.token_urlsafe(24)
    with open(path, "w") as f:
        f.write(tok)
    os.chmod(path, 0o600)
    return tok
```

with:

```python
def _ensure_token(path: str) -> str:
    env_tok = os.environ.get("SWINGBOT_TOKEN")
    if env_tok:
        return env_tok.strip()
    if os.path.exists(path):
        with open(path) as f:
            return f.read().strip()
    tok = secrets.token_urlsafe(24)
    with open(path, "w") as f:
        f.write(tok)
    os.chmod(path, 0o600)
    return tok
```

- [ ] **Step 4: Add `local_trust` to `create_app` + the bootstrap route in `web.py`**

Change the `create_app` signature to add `local_trust`:

```python
def create_app(controller, profiles, creds, token: str, store=None, market=None,
               backfiller=None, discovery=None, discovery_cache_path=None,
               brain=None, agent_dir=None, poller=None,
               auto_dashboard=None, local_trust: bool = False) -> FastAPI:
```

Add this route just after `require_token` is defined (before the `# ---- read ----` block):

```python
    @app.get("/api/auth/bootstrap")
    def auth_bootstrap():
        # Hands-off token delivery for a trusted single-user localhost deployment.
        # Off by default; enabled only when the operator sets SWINGBOT_LOCAL_TRUST=1.
        if not local_trust:
            raise HTTPException(status_code=403, detail="bootstrap disabled")
        return {"token": token}
```

- [ ] **Step 5: Wire `local_trust` through `webmain.main()`**

In `webmain.py`, change the `create_app(...)` call to pass `local_trust`:

```python
    app = create_app(controller=supervisor, profiles=profiles, creds=creds,
                     token=token, store=store, market=market, backfiller=backfiller,
                     discovery=discovery,
                     discovery_cache_path=os.path.join(DATA_DIR, "discovery.json"),
                     brain=brain, agent_dir=os.path.join(DATA_DIR, "agent"),
                     poller=poller, auto_dashboard=auto_dashboard,
                     local_trust=os.environ.get("SWINGBOT_LOCAL_TRUST") == "1")
```

- [ ] **Step 6: Add env to `docker-compose.yml`**

In the `swingbot.environment` list, add (after `CORE_ENGINE_DATA=/core-engine-data`):

```yaml
      # Autonomous auth: pin a deterministic token and let the localhost frontend
      # self-bootstrap it (single-user trusted host). Change SWINGBOT_TOKEN to rotate.
      - SWINGBOT_TOKEN=${SWINGBOT_TOKEN:-swingbot-local}
      - SWINGBOT_LOCAL_TRUST=1
```

- [ ] **Step 7: Run tests + web auth slice**

Run: `.venv/bin/python -m pytest tests/test_auth_bootstrap.py tests/test_web_control.py tests/test_web_credentials.py -q && .venv/bin/ruff check src/`
Expected: PASS, ruff clean.

- [ ] **Step 8: Commit**

```bash
git add src/swingbot/webmain.py src/swingbot/web.py docker-compose.yml tests/test_auth_bootstrap.py
git commit -m "feat(auth): SWINGBOT_TOKEN env + /api/auth/bootstrap for hands-off localhost auth"
```

---

## Task 9: Frontend API client — broker methods + token auto-bootstrap

**Files:**
- Modify: `frontend/src/api.js`
- Test: manual (frontend build gate); no JS unit harness in this repo.

**Interfaces:**
- Consumes: endpoints from Tasks 7–8.
- Produces `api` methods: `listBrokers`, `setBrokerCreds`, `testBroker`, `setActiveBroker`, `reconnectBroker`, `authBootstrap`; plus `ensureToken()` that self-services `/api/auth/bootstrap` when no token is stored.

- [ ] **Step 1: Add the broker/auth methods**

In `frontend/src/api.js`, add these entries inside the `api` object (e.g. right after the `setCreds` entry):

```javascript
  listBrokers: () => req('GET', '/api/brokers'),
  setBrokerCreds: (broker_id, values) =>
    req('PUT', `/api/brokers/${encodeURIComponent(broker_id)}/credentials`, { values }),
  testBroker: (broker_id, values, mode) =>
    req('POST', `/api/brokers/${encodeURIComponent(broker_id)}/test`, { values, mode }),
  setActiveBroker: (broker_id) => req('POST', '/api/brokers/active', { broker_id }),
  reconnectBroker: () => req('POST', '/api/brokers/reconnect', {}),
  authBootstrap: () => req('GET', '/api/auth/bootstrap'),
```

- [ ] **Step 2: Add `ensureToken()` exported helper**

After the existing `setToken` definition near the top of `frontend/src/api.js`, add:

```javascript
// On a trusted localhost deployment the backend serves the token at
// /api/auth/bootstrap so the user never has to copy it from the console.
// Silently no-ops (keeps manual TokenGate) when the endpoint is 403/unavailable.
export async function ensureToken() {
  if (getToken()) return getToken()
  try {
    const res = await fetch('/api/auth/bootstrap')
    if (!res.ok) return ''
    const { token } = await res.json()
    if (token) setToken(token)
    return token || ''
  } catch {
    return ''
  }
}
```

- [ ] **Step 3: Call `ensureToken()` at app startup**

`frontend/src/main.jsx` currently reads exactly:

```jsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import './theme.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode><App /></React.StrictMode>
)
```

Replace its entire contents with (add the `ensureToken` import; defer render until bootstrap resolves):

```jsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import { ensureToken } from './api.js'
import './theme.css'

ensureToken().finally(() => {
  ReactDOM.createRoot(document.getElementById('root')).render(
    <React.StrictMode><App /></React.StrictMode>
  )
})
```

- [ ] **Step 4: Build the frontend**

Run: `cd frontend && npm run build`
Expected: build succeeds (no unresolved imports).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api.js frontend/src/main.jsx
git commit -m "feat(frontend): broker api methods + token auto-bootstrap on load"
```

---

## Task 10: Schema-driven Broker Connection panel in Settings

**Files:**
- Modify: `frontend/src/pages/Settings.jsx`
- Test: manual (frontend build gate).

**Interfaces:**
- Consumes: `api.listBrokers`, `api.setBrokerCreds`, `api.testBroker`, `api.setActiveBroker`, `api.reconnectBroker` (Task 9).
- Produces: a Broker Connection panel that loads `/api/brokers`, lets the user pick the active broker, renders credential inputs from each broker's field schema (secret fields as password inputs), and offers Test / Save / Reconnect actions. Replaces the hard-coded Alpaca-only block.

- [ ] **Step 1: Replace the credentials panel**

Replace the entire contents of `frontend/src/pages/Settings.jsx` with:

```jsx
import { useEffect, useState } from 'react'
import { api } from '../api.js'
import TokenGate from '../components/TokenGate.jsx'
import Hint from '../components/Hint.jsx'
import RebalancePanel from '../components/RebalancePanel.jsx'

export default function Settings(){
  const [data, setData] = useState(null)       // { active, brokers: [...] }
  const [sel, setSel] = useState('')           // selected broker id
  const [vals, setVals] = useState({})         // field name -> input value
  const [mode, setMode] = useState('paper')
  const [err, setErr] = useState(''); const [msg, setMsg] = useState('')

  const load = async () => {
    const d = await api.listBrokers()
    setData(d)
    setSel(prev => prev || d.active)
  }
  useEffect(() => { load().catch(e => setErr(e.message)) }, [])
  useEffect(() => { setVals({}); setMsg(''); setErr('') }, [sel])

  if (!data) return <div className="wrap"><div className="panel">Loading…</div></div>
  const broker = data.brokers.find(b => b.id === sel) || data.brokers[0]

  const setField = (name, v) => setVals(s => ({ ...s, [name]: v }))

  const valuesPayload = () => {
    const out = { ...vals }
    if (broker.modes.includes('paper'))
      out.base_url = mode === 'paper'
        ? 'https://paper-api.alpaca.markets' : 'https://api.alpaca.markets'
    return out
  }

  const doTest = async () => { setErr(''); setMsg(''); try {
    const r = await api.testBroker(broker.id, valuesPayload(), mode)
    r.ok ? setMsg(`Test OK — ${r.detail}`) : setErr(`Test failed — ${r.detail}`)
  } catch (e) { setErr(e.message) } }

  const doSave = async () => { setErr(''); setMsg(''); try {
    await api.setBrokerCreds(broker.id, valuesPayload())
    if (data.active !== broker.id) await api.setActiveBroker(broker.id)
    setMsg('Saved'); setVals({}); load()
  } catch (e) { setErr(e.message) } }

  const doReconnect = async () => { setErr(''); setMsg(''); try {
    const r = await api.reconnectBroker()
    r.ok ? setMsg(`Reconnected — ${r.detail}`) : setErr(`Reconnect failed — ${r.detail}`)
  } catch (e) { setErr(e.message) } }

  return (
    <div className="wrap">
      <div className="panel">
        <h3>Broker connection
          <Hint text="The brokerage the bot trades through. Pick the active broker, paste its API keys, test the connection, then save. Reconnect applies new keys to the running bot without a restart." />
        </h3>
        {err && <div className="err">{err}</div>}{msg && <div className="pos">{msg}</div>}

        <label>Broker</label>
        <select value={sel} onChange={e => setSel(e.target.value)}>
          {data.brokers.map(b => (
            <option key={b.id} value={b.id}>
              {b.label}{b.id === data.active ? ' (active)' : ''}{b.configured ? ' ✓' : ''}
            </option>
          ))}
        </select>

        <div className="row"><span>Configured</span>
          <span className={broker.configured ? 'pos' : 'neg'}>{String(broker.configured)}</span></div>

        {broker.fields.map(f => (
          <div key={f.name}>
            <label>{f.label}{f.help && <Hint text={f.help} />}
              {broker.status.fields[f.name]?.set && !f.secret
                && <span className="muted"> (current: {broker.status.fields[f.name].value})</span>}
              {broker.status.fields[f.name]?.set && f.secret
                && <span className="pos"> (set)</span>}
            </label>
            <input
              type={f.secret ? 'password' : 'text'}
              value={vals[f.name] || ''}
              placeholder={f.secret ? '••••••••' : ''}
              onChange={e => setField(f.name, e.target.value)} />
          </div>
        ))}

        {broker.modes.includes('paper') && (
          <label><input type="checkbox" style={{ width: 'auto' }}
            checked={mode === 'paper'}
            onChange={e => setMode(e.target.checked ? 'paper' : 'live')} /> Paper endpoint
            <Hint text="Checked = simulated paper trading with your paper keys. Uncheck only to trade real money with live keys." />
          </label>
        )}

        <div style={{ marginTop: 10, display: 'flex', gap: 8 }}>
          <button className="act" onClick={doTest}>Test connection</button>
          <button className="act" onClick={doSave}>Save credentials</button>
          <button className="act" onClick={doReconnect}>Reconnect bot</button>
        </div>
      </div>
      <RebalancePanel />
      <TokenGate onSet={() => load().catch(() => {})} />
    </div>
  )
}
```

- [ ] **Step 2: Build the frontend**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Settings.jsx
git commit -m "feat(frontend): schema-driven broker connection panel with test/save/reconnect"
```

---

## Task 11: Full regression gate, deploy, and roadmap update

**Files:**
- Modify: `docs/ROADMAP_STATUS.md`
- No source changes (verification + deployment task).

- [ ] **Step 1: Full backend gate**

Run: `.venv/bin/python -m pytest -q`
Expected: all prior tests plus the new ones pass — at least **626 passed** (baseline) plus the new tests, **6 skipped**, no failures.

- [ ] **Step 2: Lint gate**

Run: `.venv/bin/ruff check src/`
Expected: clean (no output).

- [ ] **Step 3: Frontend build gate**

Run: `cd frontend && npm run build`
Expected: green.

- [ ] **Step 4: Rebuild + restart the container (standing Docker policy)**

Run: `docker compose build swingbot && docker compose up -d swingbot`
Expected: image builds; `swingbot` container recreated and healthy.

- [ ] **Step 5: Live-verify the new surface**

Run:
```bash
curl -s localhost:8000/api/brokers | head -c 400
curl -s localhost:8000/api/auth/bootstrap | head -c 200
```
Expected: `/api/brokers` returns `{"active":"alpaca","brokers":[{"id":"alpaca",...}]}`; `/api/auth/bootstrap` returns `{"token":"swingbot-local"}` (because compose sets `SWINGBOT_LOCAL_TRUST=1` + `SWINGBOT_TOKEN`). Then confirm a token-gated reconnect responds:
```bash
curl -s -X POST localhost:8000/api/brokers/reconnect -H "X-Token: swingbot-local" | head -c 200
```
Expected: `{"ok":true,"detail":"reconnected"}` (or `{"ok":false,...}` with a truthful reason if no credentials are stored — both are acceptable proof the route is wired).

- [ ] **Step 6: Update `docs/ROADMAP_STATUS.md`**

Add a dated "✅ BROKER CONNECTION MANAGER — COMPLETE & LIVE (2026-06-20)" entry at the top of the NEXT ACTION section summarizing: adapter registry (`broker/adapter.py`, Alpaca registered), versioned multi-broker `CredentialStore` with v1→v2 migration, supervisor `reconnect()`, schema-driven Settings panel, autonomous auth (`SWINGBOT_TOKEN` + `/api/auth/bootstrap`), the final gate numbers, and the live-verification results. Set "Last updated: 2026-06-20".

- [ ] **Step 7: Commit**

```bash
git add docs/ROADMAP_STATUS.md
git commit -m "docs: record Broker Connection Manager completion in roadmap status"
```

- [ ] **Step 8: Update graphify graph (house rule)**

Run: `python3 -m graphify update .`
(If the module is absent on this host, skip — note it in the commit/roadmap as done previously.)

---

## Self-Review Notes (verification this plan was checked against the design)

- **Scope coverage (S180 design):** adapter registry → Task 1; back-compatible credential-store migration → Task 2; API endpoints (`GET /api/brokers`, credentials get/test/put, active) → Tasks 7; hot-reconnect via `supervisor.reconnect()` → Tasks 5 + 7; schema-driven Settings panel rework → Tasks 9–10; single-active-broker model → enforced by `active()`/`set_active` (one active id); TDD throughout.
- **Auth-autonomy fork (user decision):** Task 8 wires `SWINGBOT_TOKEN` through compose and adds `/api/auth/bootstrap` + frontend `ensureToken()` so no manual console copy is needed on the trusted host; safe-by-default (bootstrap 403 unless `SWINGBOT_LOCAL_TRUST=1`).
- **Back-compat:** legacy `set/status/get` preserved (Task 2) — `tests/test_credentials.py` and `tests/test_web_credentials.py` remain green; legacy `PUT /api/credentials` untouched.
- **Type consistency:** `make_broker(mode)`, `make_data()`, `test_broker(broker_id, values, mode)`, `list_brokers()`, `set_broker(broker_id, values)`, `set_active(broker_id)`, `active()`, `broker_status(broker_id)`, `reconnect() -> (bool, str)`, `CredentialField(name,label,secret,help)` — names used identically across Tasks 1–10.
```
