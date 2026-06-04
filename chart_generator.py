# chart_generator.py
"""
chart_generator.py — Institutional Candlestick Chart Generator

Generates a professional candlestick chart image from live candle data.
The chart is sent as a photo attachment to the Telegram SNIPER TRIGGER alert.

What the chart shows:
  - Last N candles of 1-minute OHLCV data (dark theme)
  - VWAP line (cyan) — the institutional anchor
  - Entry price (green dashed) — sniper entry zone
  - Stop-Loss (red dashed) — invalidation level
  - Target (blue dashed) — profit objective
  - Volume bars at the bottom

Output: PNG image as bytes (in-memory, no temp files on disk)
"""

import io
import logging
import numpy as np
import pandas as pd
import mplfinance as mpf
import matplotlib
matplotlib.use("Agg")   # Non-interactive backend — no GUI window opens
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import config

log = logging.getLogger("ChartGen")


def generate_signal_chart(
    symbol:    str,
    df:        pd.DataFrame,
    entry:     float,
    sl:        float,
    target:    float,
    direction: str,
    vwap_col:  str = "vwap",
) -> bytes | None:
    """
    Generates a 1-minute candlestick chart with VWAP and trade levels.

    Args:
        symbol:    Stock symbol (e.g. "HDFCBANK")
        df:        DataFrame with columns open/high/low/close/volume and optionally vwap/atr
                   Must have at least 10 rows.
        entry:     Entry price (green line)
        sl:        Stop-loss price (red line)
        target:    Target price (blue line)
        direction: "BULLISH" or "BEARISH"
        vwap_col:  Column name for VWAP (default "vwap")

    Returns:
        PNG image as bytes, or None if generation failed.
    """
    try:
        # ── Prepare data ──────────────────────────────────────────────────────
        # Use last N candles for clarity
        n_candles = min(config.CHART_CANDLES, len(df))
        plot_df   = df.tail(n_candles).copy()

        if len(plot_df) < 5:
            log.warning(f"Not enough candles to generate chart for {symbol}")
            return None

        # mplfinance requires DatetimeIndex with capital OHLCV columns
        # We generate synthetic timestamps starting from 09:15 IST
        from datetime import datetime, timedelta
        import pytz
        base_time = datetime.now(pytz.timezone("Asia/Kolkata")).replace(
            hour=9, minute=15, second=0, microsecond=0
        )
        timestamps = [base_time + timedelta(minutes=i) for i in range(len(plot_df))]
        plot_df.index = pd.DatetimeIndex(timestamps)

        # Rename columns to mplfinance format (capital letters)
        plot_df = plot_df.rename(columns={
            "open": "Open", "high": "High",
            "low": "Low", "close": "Close", "volume": "Volume"
        })

        # ── Additional plots ──────────────────────────────────────────────────
        addplots = []

        # VWAP line (cyan)
        if vwap_col in df.columns:
            vwap_series = df[vwap_col].tail(n_candles).values
            vwap_series = pd.Series(vwap_series, index=plot_df.index)
            addplots.append(
                mpf.make_addplot(vwap_series, color="#00FFFF", width=1.8,
                                 label="VWAP", linestyle="-")
            )

        # ── Horizontal lines: Entry / SL / Target ─────────────────────────────
        hline_values  = [entry, sl, target]
        hline_colors  = ["#00FF88", "#FF4444", "#4488FF"]

        # ── Chart style (dark institutional theme) ────────────────────────────
        mc = mpf.make_marketcolors(
            up     = "#26a65b",   # Green candles
            down   = "#e74c3c",   # Red candles
            edge   = "inherit",
            wick   = "inherit",
            volume = {"up": "#26a65b55", "down": "#e74c3c55"}
        )
        style = mpf.make_mpf_style(
            marketcolors   = mc,
            facecolor      = "#0d1117",   # Dark background
            edgecolor      = "#21262d",
            figcolor       = "#0d1117",
            gridcolor      = "#21262d",
            gridstyle      = "--",
            gridaxis       = "both",
            y_on_right     = False,
            rc             = {
                "axes.labelcolor":  "#c9d1d9",
                "xtick.color":      "#c9d1d9",
                "ytick.color":      "#c9d1d9",
                "font.family":      "monospace",
            }
        )

        # ── Render to buffer ──────────────────────────────────────────────────
        buf = io.BytesIO()
        arrow = "▲" if direction == "BULLISH" else "▼"

        fig, axes = mpf.plot(
            plot_df,
            type        = "candle",
            style       = style,
            title       = f"\n  {symbol} — {direction} {arrow}  |  Sniper Setup  |  1-Min Chart",
            addplot     = addplots if addplots else None,
            hlines      = dict(hlines=hline_values, colors=hline_colors,
                               linestyle="--", linewidths=[1.2, 1.2, 1.2]),
            volume      = True,
            figsize     = (14, 7),
            returnfig   = True,
            warn_too_much_data = 1000,
        )

        # ── Legend ────────────────────────────────────────────────────────────
        legend_patches = [
            mpatches.Patch(color="#00FF88", label=f"Entry  ₹{entry}"),
            mpatches.Patch(color="#FF4444", label=f"SL      ₹{sl}"),
            mpatches.Patch(color="#4488FF", label=f"Target ₹{target}"),
        ]
        if addplots:
            legend_patches.insert(0, mpatches.Patch(color="#00FFFF", label="VWAP"))

        axes[0].legend(
            handles    = legend_patches,
            loc        = "upper left",
            framealpha = 0.3,
            facecolor  = "#161b22",
            edgecolor  = "#30363d",
            labelcolor = "#c9d1d9",
            fontsize   = 9,
        )

        fig.savefig(buf, format="png", dpi=130, bbox_inches="tight",
                    facecolor="#0d1117")
        plt.close(fig)
        buf.seek(0)

        log.debug(f"Chart generated for {symbol} ({len(plot_df)} candles)")
        return buf.getvalue()

    except Exception as e:
        log.warning(f"Chart generation failed for {symbol}: {e}")
        return None
