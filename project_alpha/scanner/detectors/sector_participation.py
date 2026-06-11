"""Sector Participation Detector"""

import pandas as pd
from project_alpha.scanner.detectors.base import DetectorInput, DetectorResult, Evidence
from project_alpha.domain.models import Direction
import config

def detect_sector_participation(input_data: DetectorInput, breadth_threshold: float = 50.0) -> DetectorResult:
    sector_df = input_data.sector_candles
    stock_df = input_data.candles
    
    if sector_df is None or sector_df.empty or len(sector_df) < 5 or len(stock_df) < 5:
        return DetectorResult(qualified=False, reason="Insufficient sector data")

    breadth_pct = 50.0
    try:
        sector_name = config.get_sector_for_symbol(input_data.symbol) if hasattr(input_data, 'symbol') else "UNKNOWN"
        if input_data.market_context and hasattr(input_data.market_context, "get_sector_breadth"):
            breadth_pct = input_data.market_context.get_sector_breadth(sector_name)
    except Exception:
        pass

    stock_returns = stock_df["close"].pct_change().dropna()
    sector_returns = sector_df["close"].pct_change().dropna()
    
    if len(stock_returns) < 4 or len(sector_returns) < 4:
        return DetectorResult(qualified=False, reason="Insufficient returns data")
        
    stock_5p_return = (stock_df["close"].iloc[-1] - stock_df["close"].iloc[-5]) / stock_df["close"].iloc[-5] * 100.0
    sector_5p_return = (sector_df["close"].iloc[-1] - sector_df["close"].iloc[-5]) / sector_df["close"].iloc[-5] * 100.0

    is_long_biased = sector_5p_return > 0
    is_leader = False
    
    if is_long_biased and stock_5p_return > sector_5p_return:
        is_leader = True
        direction = Direction.BULLISH
    elif not is_long_biased and stock_5p_return < sector_5p_return:
        is_leader = True
        direction = Direction.BEARISH
    else:
        direction = Direction.BULLISH if stock_5p_return > 0 else Direction.BEARISH

    if breadth_pct != 50.0 and breadth_pct < breadth_threshold and is_long_biased:
        return DetectorResult(qualified=False, reason="Low Sector Breadth for Longs")
    if breadth_pct != 50.0 and breadth_pct > (100.0 - breadth_threshold) and not is_long_biased:
        return DetectorResult(qualified=False, reason="Low Sector Breadth for Shorts")

    confidence = 20.0 if is_leader else 10.0

    evidence = Evidence(
        kind="SECTOR",
        label="Sector Leadership" if is_leader else "Sector Participant",
        value=breadth_pct,
        confidence=confidence,
        metadata={
            "direction": direction.value, 
            "is_leader": is_leader, 
            "stock_5p_return": stock_5p_return, 
            "sector_5p_return": sector_5p_return,
            "true_breadth": breadth_pct != 50.0
        }
    )

    return DetectorResult(
        qualified=True,
        confidence_add=confidence,
        evidence=[evidence],
        data={"direction": direction.value, "breadth_pct": breadth_pct, "is_leader": is_leader, "rs": stock_5p_return - sector_5p_return}
    )
