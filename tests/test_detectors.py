import unittest

import pandas as pd

from project_alpha.scanner.detectors import (
    calculate_institutional_rr,
    detect_opening_range,
    detect_trend_day,
    detect_vwap_pullback,
    is_fakeout_candle,
)


def sample_df():
    return pd.DataFrame([
        {"open": 99, "high": 100, "low": 98, "close": 99, "volume": 100, "atr": 1, "vwap": 99},
        {"open": 99, "high": 100, "low": 98, "close": 99, "volume": 100, "atr": 1, "vwap": 99},
        {"open": 99, "high": 100, "low": 98, "close": 99, "volume": 100, "atr": 1, "vwap": 99},
        {"open": 100, "high": 101, "low": 99, "close": 100, "volume": 100, "atr": 1, "vwap": 99.5},
        {"open": 102, "high": 112, "low": 101, "close": 110, "volume": 500, "atr": 5, "vwap": 103},
    ])


class DetectorTests(unittest.TestCase):
    def test_opening_range_detects_bullish_breakout(self):
        result = detect_opening_range(sample_df())
        self.assertTrue(result.qualified)
        self.assertEqual(result.data["direction"], "BULLISH")
        self.assertEqual(result.confidence_add, 0.30)

    def test_fakeout_filter_detects_large_upper_wick(self):
        candle = pd.Series({"open": 100, "high": 120, "low": 99, "close": 101})
        self.assertTrue(is_fakeout_candle(candle, "BULLISH"))

    def test_trend_day_requires_volume_range_and_sector_tailwind(self):
        df = sample_df()
        sector_df = pd.DataFrame([
            {"open": 1, "high": 2, "low": 1, "close": 1, "volume": 100},
            {"open": 1, "high": 2, "low": 1, "close": 1, "volume": 100},
            {"open": 1, "high": 2, "low": 1, "close": 1, "volume": 100},
            {"open": 1, "high": 2, "low": 1, "close": 1, "volume": 100},
            {"open": 1, "high": 2, "low": 1, "close": 1, "volume": 500},
        ])
        result = detect_trend_day(df, sector_df)
        self.assertTrue(result.qualified)
        self.assertGreaterEqual(result.data["vol_ratio"], 3.0)
        self.assertTrue(result.data["sector_tailwind"])

    def test_vwap_pullback_returns_legacy_keys(self):
        df = pd.DataFrame([
            {"open": 100, "high": 101, "low": 99, "close": 100, "volume": 500, "atr": 2, "vwap": 100},
            {"open": 101, "high": 102, "low": 100, "close": 101, "volume": 500, "atr": 2, "vwap": 100},
            {"open": 102, "high": 103, "low": 101, "close": 102, "volume": 500, "atr": 2, "vwap": 100},
            {"open": 103, "high": 104, "low": 102, "close": 103, "volume": 500, "atr": 2, "vwap": 100},
            {"open": 104, "high": 105, "low": 103, "close": 104, "volume": 500, "atr": 2, "vwap": 100},
            {"open": 100.0, "high": 100.3, "low": 99.8, "close": 100.19, "volume": 100, "atr": 2, "vwap": 100},
            {"open": 100.1, "high": 100.3, "low": 99.8, "close": 100.19, "volume": 100, "atr": 2, "vwap": 100},
            {"open": 100.0, "high": 100.3, "low": 99.8, "close": 100.19, "volume": 100, "atr": 2, "vwap": 100},
        ])
        result = detect_vwap_pullback(df, "BULLISH")
        payload = result.to_legacy_dict()
        self.assertTrue(payload["setup_confirmed"])
        self.assertIn("entry_zone", payload)
        self.assertEqual(payload["confidence_add"], 0.20)

    def test_risk_reward_filter_is_viable_for_standard_setup(self):
        result = calculate_institutional_rr(100, 99, 3.0)
        self.assertTrue(result.data["viable"])
        self.assertEqual(result.data["rr_ratio"], 4.0)


if __name__ == "__main__":
    unittest.main()
