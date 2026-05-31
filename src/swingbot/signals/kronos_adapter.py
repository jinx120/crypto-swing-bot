from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Protocol

import pandas as pd

logger = logging.getLogger(__name__)


class PredictorProtocol(Protocol):
    """Matches the real KronosPredictor.predict() signature."""

    def predict(
        self,
        df: pd.DataFrame,
        x_timestamp: pd.Series,
        y_timestamp: pd.Series,
        pred_len: int,
        T: float,
        top_p: float,
        sample_count: int,
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
    """Wraps a PredictorProtocol: column extraction, Series timestamps, cache, timeout.

    Real Kronos API (NeoQuasar/Kronos-small):
      - x_timestamp: pd.Series of historical bar timestamps
      - y_timestamp: pd.Series of future bar timestamps
      - df: DataFrame with open/high/low/close/volume (no ts column)
      - T: temperature (float, default 1.0)
      - top_p: nucleus sampling (float, default 0.9)
      - sample_count: forecast paths to average (int, default 1)
    """

    def __init__(
        self,
        predictor: PredictorProtocol,
        pred_len: int = 4,
        timeout_s: float = 30.0,
        T: float = 1.0,
        top_p: float = 0.9,
        sample_count: int = 1,
    ) -> None:
        self._predictor = predictor
        self.pred_len = pred_len
        self._timeout_s = timeout_s
        self._T = T
        self._top_p = top_p
        self._sample_count = sample_count
        self._cache_key = None
        self._cache_val: pd.DataFrame | None = None
        self._precomputed: dict | None = None
        self._executor = ThreadPoolExecutor(max_workers=1)

    @classmethod
    def from_profile(cls, params: dict) -> "KronosAdapter":
        """Load real Kronos model from HuggingFace Hub.

        Recommended models for RTX 3050 (8 GB VRAM):
          - NeoQuasar/Kronos-small  (24.7M params, fast)   ← default
          - NeoQuasar/Kronos-base   (102.3M params, more accurate)
        """
        Kronos, KronosTokenizer, KronosPredictor = _load_kronos()
        model_name = params.get("model_name", "NeoQuasar/Kronos-small")
        tokenizer_name = params.get("tokenizer_name", "NeoQuasar/Kronos-Tokenizer-base")
        tokenizer = KronosTokenizer.from_pretrained(tokenizer_name)
        model = Kronos.from_pretrained(model_name)
        predictor = KronosPredictor(model, tokenizer, max_context=512)
        return cls(
            predictor=predictor,
            pred_len=params.get("pred_len", 4),
            timeout_s=params.get("timeout_s", 30.0),
            T=params.get("T", 1.0),
            top_p=params.get("top_p", 0.9),
            sample_count=params.get("sample_count", 1),
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
        x_timestamp = candles["ts"].reset_index(drop=True)
        kronos_df = candles[["open", "high", "low", "close", "volume"]].reset_index(drop=True)

        last_ts = candles["ts"].iloc[-1]
        bar_dur = candles["ts"].iloc[-1] - candles["ts"].iloc[-2]
        y_timestamp = pd.date_range(
            start=last_ts + bar_dur,
            periods=self.pred_len,
            freq=bar_dur,
            tz=last_ts.tzinfo,
        ).to_series().reset_index(drop=True)

        def _call() -> pd.DataFrame:
            return self._predictor.predict(
                df=kronos_df,
                x_timestamp=x_timestamp,
                y_timestamp=y_timestamp,
                pred_len=self.pred_len,
                T=self._T,
                top_p=self._top_p,
                sample_count=self._sample_count,
            )

        try:
            fut = self._executor.submit(_call)
            return fut.result(timeout=self._timeout_s)
        except (FuturesTimeoutError, Exception):
            logger.warning("Kronos inference failed or timed out", exc_info=True)
            return None
