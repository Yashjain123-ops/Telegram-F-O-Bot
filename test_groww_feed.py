import nest_asyncio
nest_asyncio.apply()

import os
from dotenv import load_dotenv
import asyncio
from growwapi import GrowwAPI, GrowwFeed

load_dotenv("c:/Telegram-F&O-Bot/.env")

KEY = os.environ.get("GROWW_API_KEY")

class Diagnostics:
    def __init__(self):
        self.client = GrowwAPI(KEY)
        self.feed = GrowwFeed(self.client)
        self.tick_count = 0
        self.nifty_count = 0
        self.first_tick = None
        self.first_nifty = None

    def on_tick(self, meta=None):
        self.tick_count += 1
        data = self.feed.get_ltp()
        if self.first_tick is None:
            self.first_tick = data

    def on_nifty_tick(self, meta=None):
        self.nifty_count += 1
        data = self.feed.get_ltp()
        if self.first_nifty is None:
            self.first_nifty = data

async def run():
    print("Starting diagnostics...")
    d = Diagnostics()
    
    universe = [{"exchange": "NSE", "segment": "CASH", "exchange_token": "ABB"}]
    nifty = [{"exchange": "NSE", "segment": "CASH", "exchange_token": "NIFTY"}]
    
    print("Subscribing UNIVERSE...")
    d.feed.subscribe_ltp(universe, on_data_received=d.on_tick)
    print("Subscribing NIFTY...")
    d.feed.subscribe_ltp(nifty, on_data_received=d.on_nifty_tick)
    
    print("Waiting 15 seconds for ticks...")
    await asyncio.sleep(15)
    
    print("\n=== RESULTS ===")
    print(f"Total Universe Ticks: {d.tick_count}")
    print(f"Total Nifty Ticks: {d.nifty_count}")
    print(f"First Tick Payload: {d.first_tick}")
    print(f"First Nifty Payload: {d.first_nifty}")
    
    import sys
    sys.exit(0)

if __name__ == "__main__":
    asyncio.run(run())
