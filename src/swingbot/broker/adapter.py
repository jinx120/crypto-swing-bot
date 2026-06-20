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

    def _redact_secrets(self, detail: str, values: dict) -> str:
        for f in self.fields:
            if f.secret and values.get(f.name):
                detail = detail.replace(str(values[f.name]), "[redacted]")
        return detail

    def test_connection(self, values: dict, mode: str) -> dict:
        try:
            self.validate(values)
            broker = AlpacaBroker(values["key_id"], values["secret_key"],
                                  paper=(mode == "paper"))
            acct = broker.get_account()
            return {"ok": True, "detail": f"connected; equity={acct.get('equity')}"}
        except Exception as exc:  # any SDK/credential failure -> truthful, never raises
            return {"ok": False, "detail": self._redact_secrets(str(exc), values)}


BROKER_REGISTRY: dict[str, BrokerAdapter] = {"alpaca": AlpacaAdapter()}


def get_adapter(broker_id: str) -> BrokerAdapter:
    try:
        return BROKER_REGISTRY[broker_id]
    except KeyError:
        raise ValueError(f"unknown broker {broker_id!r}")
