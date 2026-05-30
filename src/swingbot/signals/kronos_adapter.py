from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Protocol

import pandas as pd

logger = logging.getLogger(__name__)


class PredictorProtocol(Protocol):
    def predict(
        self,
        df: pd.DataFrame,
        x_timestamp: pd.Timestamp,
        y_timestamp: pd.Timestamp,
        pred_len: int,
        T: int,
        top_k: int,
        top_p: float,
        sample_count: int,
        verbose: bool,
    ) -> pd.DataFrame: ...


def _load_kronos():
    """Lazy import gate — only called from KronosAdapter.from_profile()."""
    try:
        from kronos.model import Kronos, KronosTokenizer, KronosPredictor  # noqa: F401
        return Kronos, KronosTokenizer, KronosPredictor
    except ImportError as exc:
        raise ImportError(
            "Kronos forecast signal requires torch and the Kronos package. "
            "Install with: pip install -e '.[kronos]'"
        ) from exc


class KronosAdapter:
    """Wraps a PredictorProtocol: column mapping, single-entry cache, timeout."""

    def __init__(
        self,
        predictor: PredictorProtocol,
        pred_len: int = 4,
        timeout_s: float = 30.0,
        T: int = 200,
        top_k: int = 5,
        top_p: float = 1.0,
        sample_count: int = 10,
    ) -> None:
        self._predictor = predictor
        self.pred_len = pred_len
        self._timeout_s = timeout_s
        self._T = T
        self._top_k = top_k
        self._top_p = top_p
        self._sample_count = sample_count
        self._cache_key = None
        self._cache_val: pd.DataFrame | None = None
        self._precomputed: dict | None = None
        self._executor = ThreadPoolExecutor(max_workers=1)

    @classmethod
    def from_profile(cls, params: dict) -> "KronosAdapter":
        """Load real Kronos model. Only call this when torch is installed.

        Verify the exact KronosPredictor constructor against the Kronos README
        (https://github.com/shiyu-coder/Kronos) before using in production.
        """
        _, _, KronosPredictor = _load_kronos()
        predictor = KronosPredictor()  # adjust args per Kronos README
        return cls(
            predictor=predictor,
            pred_len=params.get("pred_len", 4),
            timeout_s=params.get("timeout_s", 30.0),
            T=params.get("T", 200),
            top_k=params.get("top_k", 5),
            top_p=params.get("top_p", 1.0),
            sample_count=params.get("sample_count", 10),
        )

    def set_precomputed(self, cache: dict) -> None:
        """Populate the precomputed forecast cache (used by run_backtest)."""
        self._precomputed = cache

    def forecast(self, candles: pd.DataFrame) -> pd.DataFrame | None:
        """Return forecast DataFrame, or None if inference fails/times out."""
        ts_key = candles["ts"].iloc[-1]
        if self._precomputed is not None:
            return self._precomputed.get(ts_key)
        if ts_key == self._cache_key:
            return self._cache_val
        result = self._run_with_timeout(candles)
        self._cache_key = ts_key
        self._cache_val = result
        return result

    def _run_with_timeout(self, candles: pd.DataFrame) -> pd.DataFrame | None:
        """Execute predictor.predict() in a thread; return None on timeout or error."""
        kronos_df = candles.rename(columns={"ts": "datetime"})
        last_ts = pd.Timestamp(kronos_df["datetime"].iloc[-1])
        bar_dur = kronos_df["datetime"].iloc[-1] - kronos_df["datetime"].iloc[-2]
        future_ts = last_ts + bar_dur * self.pred_len

        def _call() -> pd.DataFrame:
            return self._predictor.predict(
                df=kronos_df,
                x_timestamp=last_ts,
                y_timestamp=future_ts,
                pred_len=self.pred_len,
                T=self._T,
                top_k=self._top_k,
                top_p=self._top_p,
                sample_count=self._sample_count,
                verbose=False,
            )

        try:
            fut = self._executor.submit(_call)
            return fut.result(timeout=self._timeout_s)
        except (FuturesTimeoutError, Exception):
            logger.warning("Kronos inference failed or timed out", exc_info=True)
            return None
