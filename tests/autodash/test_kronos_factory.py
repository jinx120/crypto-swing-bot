from swingbot.autodash.kronos_factory import pick_device, build_kronos_signal


class _FakeCuda:
    def __init__(self, ok): self._ok = ok
    def is_available(self): return self._ok


class _FakeTorch:
    def __init__(self, ok): self.cuda = _FakeCuda(ok)


def test_pick_device_prefers_cuda_when_available():
    assert pick_device(_FakeTorch(True)) == "cuda"


def test_pick_device_falls_back_to_cpu():
    assert pick_device(_FakeTorch(False)) == "cpu"


def test_build_kronos_signal_never_raises():
    # On a host without torch/Kronos this returns None instead of crashing.
    sig = build_kronos_signal()
    assert sig is None or hasattr(sig, "evaluate")
