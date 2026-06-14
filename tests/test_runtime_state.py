from concurrent.futures import ThreadPoolExecutor

from swingbot.runtime_state import RuntimeStateStore


def test_running_desired_defaults_false(tmp_path):
    rs = RuntimeStateStore(str(tmp_path / "rt.db"))
    assert rs.get_running_desired() is False


def test_set_running_desired_true_survives_reopen(tmp_path):
    db = str(tmp_path / "rt.db")
    RuntimeStateStore(db).set_running_desired(True)
    # A second instance simulates a process/container restart on the same file.
    assert RuntimeStateStore(db).get_running_desired() is True


def test_set_running_desired_false_clears(tmp_path):
    db = str(tmp_path / "rt.db")
    rs = RuntimeStateStore(db)
    rs.set_running_desired(True)
    rs.set_running_desired(False)
    assert RuntimeStateStore(db).get_running_desired() is False


def test_runtime_state_store_serializes_concurrent_access(tmp_path):
    rs = RuntimeStateStore(str(tmp_path / "rt.db"))

    def write_then_read(desired):
        rs.set_running_desired(desired)
        return rs.get_running_desired()

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(write_then_read, [True, False] * 50))

    assert len(results) == 100
    assert isinstance(rs.get_running_desired(), bool)
