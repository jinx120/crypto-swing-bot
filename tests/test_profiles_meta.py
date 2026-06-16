from swingbot.profiles import ProfileStore


def test_get_meta_missing_returns_none(tmp_path):
    store = ProfileStore(str(tmp_path / "p.db"))
    assert store.get_meta("managed_version") is None


def test_set_then_get_meta_roundtrips_and_persists(tmp_path):
    db = str(tmp_path / "p.db")
    store = ProfileStore(db)
    store.set_meta("managed_version", "1")
    assert store.get_meta("managed_version") == "1"
    assert ProfileStore(db).get_meta("managed_version") == "1"


def test_meta_does_not_collide_with_active_pointer(tmp_path):
    store = ProfileStore(str(tmp_path / "p.db"))
    store.save("u", {"symbol": "BTC/USD"})
    store.set_active("u")
    store.set_meta("managed_version", "2")
    assert store.get_active_name() == "u"
    assert store.get_meta("managed_version") == "2"
