import os
import pytz
from datetime import time
import logging

log = logging.getLogger("Config")

# ==============================================================================
# 🔐 CREDENTIALS
# Loaded from the .env file. Do not hardcode values here.
# ==============================================================================
from dotenv import load_dotenv

# Load variables from .env file into the environment
load_dotenv()

# --- TELEGRAM AND BROKER APIs ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID")
BROKER_API_KEY     = os.environ.get("GROWW_API_KEY")
BROKER_API_SECRET  = os.environ.get("GROWW_API_SECRET")

if not TELEGRAM_BOT_TOKEN:
    log.warning("⚠️  TELEGRAM_BOT_TOKEN not set in environment or .env file.")
if not BROKER_API_KEY:
    log.warning("⚠️  GROWW_API_KEY not set in environment or .env file.")


# ==============================================================================
# 📊 STATIC F&O WATCHLIST
# High-liquidity, high-beta NSE F&O stocks for momentum strategies.
# ==============================================================================
UNIVERSE = [
    '360ONE', 'ABB', 'ABCAPITAL', 'ADANIENSOL', 'ADANIENT', 'ADANIGREEN',
    'ADANIPORTS', 'ADANIPOWER', 'ALKEM', 'AMBER', 'AMBUJACEM', 'ANGELONE',
    'APLAPOLLO', 'APOLLOHOSP', 'ASHOKLEY', 'ASIANPAINT', 'ASTRAL', 'AUBANK',
    'AUROPHARMA', 'AXISBANK', 'BAJAJ-AUTO', 'BAJAJFINSV', 'BAJAJHLDNG',
    'BAJFINANCE', 'BANDHANBNK', 'BANKBARODA', 'BDL', 'BEL', 'BHARATFORG',
    'BHARTIARTL', 'BHEL', 'BIOCON', 'BLUESTARCO', 'BOSCHLTD', 'BPCL',
    'BRITANNIA', 'BSE', 'CAMS', 'CANBK', 'CDSL', 'CHOLAFIN', 'CIPLA',
    'COALINDIA', 'COCHINSHIP', 'COFORGE', 'COLPAL', 'CONCOR', 'CROMPTON',
    'CUMMINSIND', 'DABUR', 'DALBHARAT', 'DELHIVERY', 'DIVISLAB', 'DIXON',
    'DLF', 'DMART', 'DRREDDY', 'EICHERMOT', 'ETERNAL', 'EXIDEIND',
    'FEDERALBNK', 'FORCEMOT', 'FORTIS', 'GAIL', 'GLENMARK', 'GMRAIRPORT',
    'GODFRYPHLP', 'GODREJCP', 'GODREJPROP', 'GRASIM', 'HAL', 'HAVELLS',
    'HCLTECH', 'HDFCAMC', 'HDFCBANK', 'HDFCLIFE', 'HEROMOTOCO', 'HINDALCO',
    'HINDPETRO', 'HINDUNILVR', 'HINDZINC', 'HUDCO', 'HYUNDAI', 'ICICIBANK',
    'ICICIGI', 'ICICIPRULI', 'IDEA', 'IDFCFIRSTB', 'IEX', 'INDHOTEL',
    'INDIANB', 'INDIGO', 'INDUSINDBK', 'INDUSTOWER', 'INFY', 'INOXWIND',
    'IOC', 'IREDA', 'IRFC', 'ITC', 'JINDALSTEL', 'JIOFIN', 'JSWENERGY',
    'JSWSTEEL', 'JUBLFOOD', 'KALYANKJIL', 'KAYNES', 'KEI', 'KFINTECH',
    'KOTAKBANK', 'KPITTECH', 'LAURUSLABS', 'LICHSGFIN', 'LICI', 'LODHA',
    'LT', 'LTF', 'LTM', 'LUPIN', 'M&M', 'MANAPPURAM', 'MANKIND', 'MARICO',
    'MARUTI', 'MAXHEALTH', 'MAZDOCK', 'MCX', 'MFSL', 'MOTHERSON',
    'MOTILALOFS', 'MPHASIS', 'MUTHOOTFIN', 'NAM-INDIA', 'NATIONALUM',
    'NAUKRI', 'NBCC', 'NESTLEIND', 'NHPC', 'NMDC', 'NTPC', 'NUVAMA',
    'NYKAA', 'OBEROIRLTY', 'OFSS', 'OIL', 'ONGC', 'PAGEIND', 'PATANJALI',
    'PAYTM', 'PERSISTENT', 'PETRONET', 'PFC', 'PGEL', 'PHOENIXLTD',
    'PIDILITIND', 'PIIND', 'PNB', 'PNBHOUSING', 'POLICYBZR', 'POLYCAB',
    'POWERGRID', 'POWERINDIA', 'PPLPHARMA', 'PREMIERENE', 'PRESTIGE',
    'RBLBANK', 'RECLTD', 'RVNL', 'SAIL', 'SAMMAANCAP', 'SBICARD',
    'SBILIFE', 'SBIN', 'SHREECEM', 'SHRIRAMFIN', 'SIEMENS', 'SOLARINDS',
    'SONACOMS', 'SRF', 'SUNPHARMA', 'SUPREMEIND', 'SUZLON', 'SWIGGY',
    'TATACONSUM', 'TATAELXSI', 'TATAPOWER', 'TATASTEEL', 'TATATECH',
    'TCS', 'TECHM', 'TIINDIA', 'TMPV', 'TITAN', 'TORNTPHARM',
    'TORNTPOWER', 'TRENT', 'TVSMOTOR', 'ULTRACEMCO', 'UNIONBANK',
    'UNITDSPR', 'UNOMINDA', 'UPL', 'VBL', 'VEDL', 'VMM', 'VOLTAS',
    'WAAREEENER', 'WIPRO', 'YESBANK', 'ZYDUSLIFE'
]

log.info(f"Loaded static watchlist with {len(UNIVERSE)} F&O stocks.")


# ==============================================================================
# ⏰ TIME & SCHEDULE PARAMETERS
# ==============================================================================
TIMEZONE     = pytz.timezone("Asia/Kolkata")
MARKET_OPEN  = time(9, 15)
ORB_END      = time(9, 30)   # 15-minute Opening Range — no signals before this
MARKET_CLOSE = time(15, 30)

# Number of 1-minute candles required before the engine evaluates a stock.
# 15 candles = 15 minutes of data (aligns with ORB window).
MIN_CANDLES_REQUIRED = 15

# Time to run morning data fetch (before market opens)
MORNING_FETCH_TIME = "09:00"
# How often (in seconds) to refresh options chain + news during market hours
INTRADAY_REFRESH_SECONDS = 1800   # 30 minutes


# ==============================================================================
# 🏛️ FII / DII SENTIMENT THRESHOLDS  (in ₹ Crore)
# Positive = buying, Negative = selling
# ==============================================================================
FII_BULLISH_THRESHOLD = 2000.0    # FII buying > ₹2000cr = institutional accumulation
FII_BEARISH_THRESHOLD = -2000.0   # FII selling > ₹2000cr = institutional distribution
FII_CONFIDENCE_BOOST  = 0.10      # Confidence added when FII aligns with trade direction


# ==============================================================================
# 📊 OPTIONS CHAIN — PCR THRESHOLDS
# PCR = Total Put OI / Total Call OI
# High PCR (>1.2) = market expects support = bullish
# Low PCR  (<0.8) = market expects resistance = bearish
# ==============================================================================
PCR_BULLISH_THRESHOLD = 1.20
PCR_BEARISH_THRESHOLD = 0.80
PCR_CONFIDENCE_BOOST  = 0.05


# ==============================================================================
# 📰 NEWS RSS FEED
# ==============================================================================
NEWS_RSS_URL = "https://economictimes.indiatimes.com/markets/stocks/rss.cms"


# ==============================================================================
# 📈 CHART SETTINGS
# ==============================================================================
CHART_CANDLES = 30    # Number of 1-minute candles to show in the chart image


# ==============================================================================
# ⚙️ VOLATILITY & ATR PARAMETERS
# ==============================================================================
ATR_PERIOD         = 14    # EWM span for True Range smoothing
ATR_MULTIPLIER_SL  = 1.5   # Stop-loss distance = 1.5 × ATR below entry
ATR_MULTIPLIER_TP  = 3.0   # Used only as fallback; primary target uses R:R gate

# Minimum ATR-to-price ratio to trade a stock at all.
# Filters flat/illiquid stocks that cannot produce meaningful moves.
# 0.5% minimum means a ₹1000 stock must have ATR > ₹5.
MIN_ATR_PRICE_RATIO = 0.005


# ==============================================================================
# 🏛️ INSTITUTIONAL VOLUME THRESHOLDS
# These are the core intelligence filters. Do not lower them.
# ==============================================================================
# Volume spike multiplier to classify institutional accumulation:
#   3.0x = Smart money entering (Trend Day floor)
#   5.0x = Campaign-level institutional activity (Sniper grade)
INSTITUTIONAL_VOL_SPIKE = 3.0   # Minimum for a Trend Day Candidate
SNIPER_VOL_SPIKE        = 5.0   # Confirms a full institutional campaign

# Sector index volume threshold for "sector tailwind" confirmation.
# If the sector index itself is printing 3.5x volume, the move is broad-based.
SECTOR_VOL_SPIKE        = 3.5

# Lookback window (in candles) for computing "average volume" baseline.
# 20 candles = 20 minutes — captures the morning's liquidity character.
AVG_VOLUME_LOOKBACK     = 20


# ==============================================================================
# 🎯 SNIPER ENTRY — VWAP PULLBACK PARAMETERS
# ==============================================================================
# Price must be within this % of VWAP to be in the sniper entry zone.
# 0.2% means on a ₹1000 stock, price must be within ₹2 of VWAP.
VWAP_PROXIMITY_BAND = 0.002   # 0.2% of VWAP price

# Pullback volume must drop to this fraction of the breakout volume.
# If breakout vol = 500K and pullback vol > 350K, retail is still selling — skip.
# If pullback vol < 300K (60%), institutions paused — that's your entry window.
PULLBACK_VOL_RATIO  = 0.60

# Rejection candle must close in the top % of its range (bullish) or bottom % (bearish).
# 0.60 = candle must close in the top 40% of its range to confirm demand.
REJECTION_CLOSE_LOC = 0.60

# Pullback candle count window. If price has been at VWAP for too long, trend is dead.
PULLBACK_MIN_CANDLES = 2
PULLBACK_MAX_CANDLES = 5


# ==============================================================================
# 📐 RISK-TO-REWARD PARAMETERS
# Three-tier target system based on institutional volume strength:
#
#   TIER 1 — Normal institutional day (3x–4.9x volume)
#             Standard setup. Target = 1:4 R:R.
#
#   TIER 2 — Strong institutional day (5x–7.9x volume)
#             Campaign mode. Target = 1:6 R:R.
#             Example: TCS June 2 type day.
#
#   TIER 3 — Full institutional campaign (8x+ volume)
#             Rare. Once or twice a month.
#             Maximum aggression. Target = 1:8 R:R.
#             Example: Budget day, RBI policy, major earnings.
# ==============================================================================
MIN_RR_RATIO             = 4.0   # Absolute minimum — no trade below 1:4
STANDARD_RR_MULT         = 4.0   # Tier 1: 3x–4.9x volume  → 1:4 target
TREND_DAY_RR_MULT        = 6.0   # Tier 2: 5x–7.9x volume  → 1:6 target
CAMPAIGN_DAY_RR_MULT     = 8.0   # Tier 3: 8x+ volume      → 1:8 target
CAMPAIGN_VOL_SPIKE       = 8.0   # Volume threshold for Tier 3


# ==============================================================================
# ✅ CONFIDENCE SCORING GATE
# The score is a weighted sum of confirmed factors.
# Weights: Breakout=0.30, Volume=0.25, Sector=0.25, VWAP Pullback=0.20
# A perfect setup scores 1.0. Minimum to fire Stage 1 alert = 0.55.
# Minimum to fire Stage 2 (Trigger) alert = 0.75.
# ==============================================================================
CONFIDENCE_WATCH_THRESHOLD   = 0.55   # Stage 1: "WARZONE FOUND — Watch"
CONFIDENCE_TRIGGER_THRESHOLD = 0.75   # Stage 2: "SNIPER SETUP — Entry Trigger"


# ==============================================================================
# 🔇 FAKEOUT FILTER
# A breakout candle with >40% of its range as a wick in the breakout direction
# is a fakeout candle — institutions rejected the move.
# ==============================================================================
MAX_WICK_PERCENT = 0.40   # More than 40% wick = fakeout, skip


# ==============================================================================
# 🔕 SIGNAL DEDUPLICATION
# Once a signal fires for a symbol, suppress re-alerts for this many seconds.
# 900 seconds = 15 minutes. Prevents Telegram spam on the same setup.
# ==============================================================================
SIGNAL_COOLDOWN_SECONDS = 900


# ==============================================================================
# 📊 SECTOR GROUPS (for sector tailwind analysis)
# ==============================================================================
SECTOR_GROUPS = {
    "NIFTY_FIN_SERVICE": [
        "360ONE", "ABCAPITAL", "ANGELONE", "BAJAJFINSV", "BAJAJHLDNG", "BAJFINANCE",
        "BSE", "CAMS", "CDSL", "CHOLAFIN", "HDFCAMC", "HDFCLIFE", "HUDCO", "ICICIGI",
        "ICICIPRULI", "IEX", "IREDA", "IRFC", "JIOFIN", "KFINTECH", "LICHSGFIN", "LICI",
        "LTF", "MANAPPURAM", "MCX", "MFSL", "MOTILALOFS", "MUTHOOTFIN", "NAM-INDIA",
        "NUVAMA", "PAYTM", "PFC", "PNBHOUSING", "POLICYBZR", "RECLTD", "SAMMAANCAP",
        "SBICARD", "SBILIFE", "SHRIRAMFIN"
    ],
    "NIFTY_INFRA": [
        "ABB", "ADANIENT", "ADANIPORTS", "AMBUJACEM", "ASTRAL", "BDL", "BEL",
        "BHARTIARTL", "COCHINSHIP", "CONCOR", "CUMMINSIND", "DALBHARAT", "DELHIVERY",
        "GMRAIRPORT", "HAL", "IDEA", "INDIGO", "INDUSTOWER", "KAYNES", "KEI", "LT", "MAZDOCK",
        "NBCC", "POLYCAB", "POWERINDIA", "RVNL", "SHREECEM", "SIEMENS", "SOLARINDS",
        "SRF", "SUPREMEIND", "ULTRACEMCO", "UPL", "VMM"
    ],
    "NIFTY_ENERGY": [
        "ADANIENSOL", "ADANIGREEN", "ADANIPOWER", "BHEL", "BPCL", "COALINDIA",
        "GAIL", "HINDPETRO", "INOXWIND", "IOC", "JSWENERGY", "NHPC", "NTPC",
        "OIL", "ONGC", "PETRONET", "POWERGRID", "PREMIERENE", "SUZLON",
        "TATAPOWER", "TORNTPOWER", "WAAREEENER"
    ],
    "NIFTY_FMCG": [
        "BRITANNIA", "COLPAL", "DABUR", "DMART", "GODFRYPHLP", "GODREJCP",
        "GRASIM", "HINDUNILVR", "ITC", "JUBLFOOD", "MARICO", "NESTLEIND", "NYKAA",
        "PAGEIND", "PATANJALI", "PIDILITIND", "PIIND", "SWIGGY", "TATACONSUM",
        "TRENT", "UNITDSPR", "VBL"
    ],
    "NIFTY_PHARMA": [
        "ALKEM", "APOLLOHOSP", "AUROPHARMA", "BIOCON", "CIPLA", "DIVISLAB",
        "DRREDDY", "FORTIS", "GLENMARK", "LAURUSLABS", "LUPIN", "MANKIND",
        "MAXHEALTH", "PPLPHARMA", "SUNPHARMA", "TORNTPHARM", "ZYDUSLIFE"
    ],
    "NIFTY_AUTO": [
        "ASHOKLEY", "BAJAJ-AUTO", "BHARATFORG", "BOSCHLTD", "EICHERMOT", "EXIDEIND",
        "FORCEMOT", "HEROMOTOCO", "HYUNDAI", "M&M", "MARUTI", "MOTHERSON",
        "SONACOMS", "TIINDIA", "TMPV", "TVSMOTOR", "UNOMINDA"
    ],
    "NIFTY_BANK": [
        "AUBANK", "AXISBANK", "BANDHANBNK", "BANKBARODA", "CANBK", "FEDERALBNK",
        "HDFCBANK", "ICICIBANK", "IDFCFIRSTB", "INDIANB", "INDUSINDBK", "KOTAKBANK",
        "PNB", "RBLBANK", "SBIN", "UNIONBANK", "YESBANK"
    ],
    "NIFTY_IT": [
        "COFORGE", "HCLTECH", "INFY", "KPITTECH", "LTM", "MPHASIS", "NAUKRI",
        "OFSS", "PERSISTENT", "TATAELXSI", "TATATECH", "TCS", "TECHM", "WIPRO"
    ],
    "NIFTY_CONSUMER_DURABLES": [
        "AMBER", "ASIANPAINT", "BLUESTARCO", "CROMPTON", "DIXON", "ETERNAL",
        "HAVELLS", "INDHOTEL", "KALYANKJIL", "PGEL", "TITAN", "VOLTAS"
    ],
    "NIFTY_METAL": [
        "APLAPOLLO", "HINDALCO", "HINDZINC", "JINDALSTEL", "JSWSTEEL",
        "NATIONALUM", "NMDC", "SAIL", "TATASTEEL", "VEDL"
    ],
    "NIFTY_REALTY": [
        "DLF", "GODREJPROP", "LODHA", "OBEROIRLTY", "PHOENIXLTD", "PRESTIGE"
    ]
}