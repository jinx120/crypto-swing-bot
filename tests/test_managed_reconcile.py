import json
import os

from swingbot import managed_profiles as mp
from swingbot.managed_profiles import reconcile_managed_profiles
from swingbot.profiles import ProfileStore


def _store(tmp_path):
    return ProfileStore(str(tmp_path / "p.db"))


def test_fresh_seed_creates_and_arms_trend_profiles(tmp_path):
    store = _store(tmp_path)
    backup_dir = str(tmp_path / "backups")
    report = reconcile_managed_profiles(
        store, enable_probe=False, mode="paper", backup_dir=backup_dir
    )
    assert set(report.seeded) == {"btc_trend", "eth_trend"}
    assert store.get("btc_trend") is not None
    assert "btc_trend" in store.list_armed()


def test_user_profiles_are_never_deleted_or_overwritten(tmp_path):
    store = _store(tmp_path)
    store.save("my_strategy", {"symbol": "SOL/USD", "entry_threshold": 0.42})
    reconcile_managed_profiles(
        store, enable_probe=True, mode="paper", backup_dir=str(tmp_path / "b")
    )
    assert store.get("my_strategy") == {"symbol": "SOL/USD", "entry_threshold": 0.42}


def test_idempotent_second_run_makes_no_change_and_no_backup(tmp_path):
    store = _store(tmp_path)
    backup_dir = str(tmp_path / "backups")
    reconcile_managed_profiles(store, enable_probe=False, mode="paper", backup_dir=backup_dir)
    second = reconcile_managed_profiles(
        store, enable_probe=False, mode="paper", backup_dir=backup_dir
    )
    assert second.seeded == [] and second.upgraded == [] and second.removed == []
    assert second.backup_path is None


def test_version_bump_backs_up_then_upgrades(tmp_path, monkeypatch):
    store = _store(tmp_path)
    backup_dir = str(tmp_path / "backups")
    reconcile_managed_profiles(store, enable_probe=False, mode="paper", backup_dir=backup_dir)

    original_defs = mp.managed_definitions

    def fake_defs(enable_probe):
        d = original_defs(enable_probe)
        d["btc_trend"]["entry_threshold"] = 0.55
        return d

    monkeypatch.setattr(mp, "MANAGED_VERSION", mp.MANAGED_VERSION + 1)
    monkeypatch.setattr(mp, "managed_definitions", fake_defs)

    report = reconcile_managed_profiles(
        store, enable_probe=False, mode="paper", backup_dir=backup_dir
    )
    assert "btc_trend" in report.upgraded
    assert report.backup_path is not None and os.path.exists(report.backup_path)
    assert store.get("btc_trend")["entry_threshold"] == 0.55
    with open(report.backup_path) as f:
        backup = json.load(f)
    assert backup["profiles"]["btc_trend"]["entry_threshold"] == 0.5
