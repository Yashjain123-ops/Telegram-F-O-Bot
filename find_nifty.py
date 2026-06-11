import config
from growwapi import GrowwAPI
import pandas as pd

api = GrowwAPI(config.BROKER_API_KEY)
api._download_and_load_instruments()
df = api.get_all_instruments()

# Search for NIFTY exactly
nifty_exact = df[df['trading_symbol'] == 'NIFTY 50']
print("=== EXACT NIFTY 50 ===")
print(nifty_exact[['exchange_token', 'trading_symbol', 'segment', 'instrument_type']])

# Search for NIFTY spot index (usually under INDICES or similar, or NIFTY in trading_symbol)
nifty_spot = df[df['trading_symbol'].str.contains('NIFTY', na=False) & (df['segment'].isin(['CASH', 'INDICES', 'INDEX', 'OPTIDX']))].head(10)
print("\n=== NIFTY SPOT/OPTIONS HEAD ===")
print(nifty_spot[['exchange_token', 'trading_symbol', 'segment', 'instrument_type']])

# Search for exchange_token = 'NIFTY' or 'NIFTY 50'
token_search = df[df['exchange_token'].isin(['NIFTY', 'NIFTY 50', 'NIFTY50', '256265'])]
print("\n=== TOKEN EXACT MATCH ===")
print(token_search[['exchange_token', 'trading_symbol', 'segment', 'instrument_type']])
