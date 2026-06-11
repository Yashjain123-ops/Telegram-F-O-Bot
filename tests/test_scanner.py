import asyncio
import unittest
from datetime import datetime

import pandas as pd

import config
from stratergy import MomentumScanner


class ScannerTests(unittest.TestCase):
    def test_sector_synthesis_uses_same_minute_member_candles(self):
        scanner = MomentumScanner()
        ts = config.TIMEZONE.localize(datetime(2026, 6, 8, 9, 20))
        members = config.SECTOR_GROUPS["NIFTY_BANK"][:4]

        async def feed():
            for idx, symbol in enumerate(members):
                await scanner.on_candle(symbol, {
                    "timestamp": ts,
                    "open": 100 + idx,
                    "high": 101 + idx,
                    "low": 99 + idx,
                    "close": 100 + idx,
                    "volume": 100,
                })

        asyncio.run(feed())

        sector_df = scanner.live_data["NIFTY_BANK"]
        self.assertEqual(len(sector_df), 1)
        self.assertEqual(sector_df.iloc[-1]["volume"], 400)

    def test_legacy_autonomous_trade_still_returns_buy_for_current_setup(self):
        scanner = MomentumScanner()
        df = pd.DataFrame([
            {"open": 99, "high": 100, "low": 98, "close": 99, "volume": 100},
            {"open": 99, "high": 100, "low": 98, "close": 99, "volume": 100},
            {"open": 99, "high": 100, "low": 98, "close": 99, "volume": 100},
            {"open": 100, "high": 103, "low": 99, "close": 102, "volume": 100},
            {"open": 102, "high": 112, "low": 101, "close": 110, "volume": 500},
        ])
        sector_df = pd.DataFrame([
            {"open": 1, "high": 2, "low": 1, "close": 1, "volume": 100},
            {"open": 1, "high": 2, "low": 1, "close": 1, "volume": 100},
            {"open": 1, "high": 2, "low": 1, "close": 1, "volume": 100},
            {"open": 1, "high": 2, "low": 1, "close": 1, "volume": 100},
            {"open": 1, "high": 2, "low": 1, "close": 1, "volume": 500},
        ])

        result = scanner.evaluate_autonomous_trade(
            df=df,
            nifty_df=pd.DataFrame(),
            sector_df=sector_df,
            opening_high=100,
            opening_low=98,
            symbol="HDFCBANK",
        )

        self.assertEqual(result["action"], "BUY")
        self.assertGreaterEqual(result["vol_ratio"], 3.0)
        self.assertGreaterEqual(result["rr"], 4.0)


if __name__ == "__main__":
    unittest.main()

