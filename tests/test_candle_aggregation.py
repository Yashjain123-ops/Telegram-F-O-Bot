import unittest
from datetime import datetime, timedelta

from project_alpha.candles import CandleAggregator


class CandleAggregationTests(unittest.TestCase):
    def test_aggregates_and_closes_one_minute_candle(self):
        agg = CandleAggregator()
        start = datetime(2026, 6, 8, 9, 15)

        self.assertIsNone(agg.aggregate_tick("ABC", 100, 10, start))
        self.assertIsNone(agg.aggregate_tick("ABC", 102, 5, start.replace(second=30)))
        candle = agg.aggregate_tick("ABC", 101, 7, start + timedelta(minutes=1))

        self.assertEqual(candle.symbol, "ABC")
        self.assertEqual(candle.open, 100)
        self.assertEqual(candle.high, 102)
        self.assertEqual(candle.low, 100)
        self.assertEqual(candle.close, 102)
        self.assertEqual(candle.volume, 15)


if __name__ == "__main__":
    unittest.main()

