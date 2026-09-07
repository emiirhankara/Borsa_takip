"""Uygulama ayarlari."""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CACHE_DIR = BASE_DIR / "cache"
CACHE_DIR.mkdir(exist_ok=True)

DEFAULT_SYMBOL = "AAPL"
DEFAULT_WATCHLIST = [DEFAULT_SYMBOL, "MSFT", "THYAO.IS", "ASELS.IS", "BIMAS.IS"]
REFRESH_SECONDS = 60
NEWS_LIMIT = 12
US_SYMBOLS = ["AAPL", "MSFT", "JNJ", "O", "MAIN", "STAG", "ADC", "PSEC", "LTC", "AGNC"]
BIST_EXAMPLES = ["THYAO.IS", "ASELS.IS", "BIMAS.IS", "TUPRS.IS", "GARAN.IS"]
