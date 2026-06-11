"""Sector mapping helpers."""

from __future__ import annotations


def build_flat_sector_map(sector_groups: dict[str, list[str]]) -> dict[str, str]:
    return {
        symbol: sector_name
        for sector_name, symbols in sector_groups.items()
        for symbol in symbols
    }


def get_sector_for_symbol(
    symbol: str,
    sector_groups: dict[str, list[str]],
    default: str = "NIFTY_50",
) -> str:
    return build_flat_sector_map(sector_groups).get(symbol, default)

