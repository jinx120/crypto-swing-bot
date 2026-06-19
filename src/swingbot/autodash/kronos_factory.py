from __future__ import annotations


def pick_device(torch_mod=None) -> str:
    if torch_mod is None:
        try:
            import torch as torch_mod  # noqa: PLC0415
        except Exception:
            return "cpu"
    try:
        return "cuda" if torch_mod.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


def build_kronos_signal(device: str | None = None,
                        model_name: str = "NeoQuasar/Kronos-small"):
    """Build a real Kronos signal on the best device, or None if its heavy
    stack (torch + Kronos repo) is unavailable. Never raises."""
    device = device or pick_device()
    try:
        from swingbot.signals.kronos_forecast import KronosForecastSignal
        sig = KronosForecastSignal(weight=1.0)
        print(f"[autodash] Kronos signal built on device={device} "
              f"(model={model_name})")
        return sig
    except Exception as exc:
        print(f"[autodash] Kronos unavailable ({type(exc).__name__}: {exc}); "
              f"comparison will use kronos=None.")
        return None
