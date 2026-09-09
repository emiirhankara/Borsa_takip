"""Uygulama ayarlari."""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CACHE_DIR = BASE_DIR / "cache"
CACHE_DIR.mkdir(exist_ok=True)

DEFAULT_SYMBOL = "THYAO.IS"

BIST_POPULAR = [
    "THYAO.IS", "ASELS.IS", "BIMAS.IS", "TUPRS.IS", "GARAN.IS",
    "AKBNK.IS", "ISCTR.IS", "YKBNK.IS", "KCHOL.IS", "SAHOL.IS",
    "FROTO.IS", "SISE.IS", "EREGL.IS", "PGSUS.IS", "ENKAI.IS",
    "TCELL.IS", "PETKM.IS", "KOZAL.IS", "ARCLK.IS", "TOASO.IS",
]

US_POPULAR = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL",
    "META", "TSLA", "JNJ", "JPM", "V",
    "WMT", "PG", "DIS", "NFLX", "AMD",
    "INTC", "KO", "PEP", "COST", "BRK-B",
]

DEFAULT_WATCHLIST = BIST_POPULAR + US_POPULAR
REFRESH_SECONDS = 60
NEWS_LIMIT = 16
US_SYMBOLS = US_POPULAR
BIST_EXAMPLES = BIST_POPULAR[:5]

# Performance optimization settings
HISTORY_PERIOD = "6mo"  # Changed from hardcoded "1y" - faster download, still sufficient for SMA50
CACHE_TTL_MAP = {
    "quote": 30,          # 30s: fresh price data
    "history": 45,        # 45s: price history with indicators
    "slow": 21600,        # 6 hours: dividends, fundamentals, financials
}
