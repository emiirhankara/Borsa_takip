"""Yahoo Finance uzerinden guvenli piyasa verisi servisi."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import logging
import re
import threading
import time
from typing import Any

import certifi
import pandas as pd
import yfinance as yf
from curl_cffi import requests
from yfinance import EquityQuery


logger = logging.getLogger(__name__)
MAX_DIVIDEND_ROWS = 500


class MarketDataService:
    _symbol_pattern = re.compile(r"^[A-Z0-9][A-Z0-9.-]{0,14}$")

    def __init__(self, cache_ttl: int = 45):
        self.cache_ttl = cache_ttl
        self._cache: dict[tuple[Any, ...], tuple[float, Any]] = {}
        self._cache_lock = threading.Lock()
        self.session = requests.Session(impersonate="chrome")
        self.session.verify = certifi.where()

    def _clean_symbol(self, symbol: str) -> str:
        cleaned = str(symbol).strip().upper()
        if not self._symbol_pattern.fullmatch(cleaned):
            raise ValueError("Geçersiz hisse sembolü.")
        return cleaned

    def _cached(self, key: tuple[Any, ...], loader):
        with self._cache_lock:
            cached = self._cache.get(key)
            if cached and time.monotonic() - cached[0] < self.cache_ttl:
                return deepcopy(cached[1])
        value = loader()
        with self._cache_lock:
            self._cache[key] = (time.monotonic(), deepcopy(value))
        return value

    @staticmethod
    def _cutoff(index: pd.DatetimeIndex, days: int) -> pd.Timestamp:
        now = pd.Timestamp.now(tz=index.tz) if getattr(index, "tz", None) else pd.Timestamp.now()
        return now - pd.Timedelta(days=days)

    def dividend_universe(self) -> list[dict[str, Any]]:
        """ABD borsalarındaki temettü verimi pozitif hisseleri getirir."""
        query = EquityQuery("and", [
            EquityQuery("is-in", ["exchange", "NMS", "NYQ", "ASE"]),
            EquityQuery("gt", ["dividendyield", 0]),
        ])
        try:
            first = yf.screen(query, offset=0, count=250, sortField="dividendyield", sortAsc=False, session=self.session)
            total = min(int(first.get("total", 0)), MAX_DIVIDEND_ROWS)
            quotes = list(first.get("quotes", []))[:MAX_DIVIDEND_ROWS]
            offset = len(quotes)
            while offset < total and quotes:
                page = yf.screen(query, offset=offset, count=250, sortField="dividendyield", sortAsc=False, session=self.session)
                page_quotes = page.get("quotes", [])
                quotes.extend(page_quotes)
                quotes = quotes[:MAX_DIVIDEND_ROWS]
                offset += len(page_quotes)

            rows = [self._dividend_row(item) for item in quotes if item.get("symbol")]
            with ThreadPoolExecutor(max_workers=6) as executor:
                counts = executor.map(self._payment_count, [row["symbol"] for row in rows])
                for row, count in zip(rows, counts):
                    row["payment_count"] = count
            return rows
        except Exception as exc:
            logger.exception("Temettu listesi alinamadi")
            raise RuntimeError(f"Temettu listesi alinamadi: {exc}") from exc

    def _dividend_row(self, item: dict[str, Any]) -> dict[str, Any]:
        return {
            "symbol": item.get("symbol", ""),
            "name": item.get("shortName") or item.get("longName") or item.get("symbol", ""),
            "exchange": item.get("fullExchangeName") or item.get("exchange", ""),
            "price": float(item.get("regularMarketPrice") or 0),
            "yield_pct": float(item.get("dividendYield") or 0),
            "annual_dividend": float(item.get("trailingAnnualDividendRate") or item.get("dividendRate") or 0),
            "market_cap": float(item.get("marketCap") or 0),
            "payment_count": 0,
        }

    def _payment_count(self, symbol: str) -> int:
        try:
            dividends = yf.Ticker(symbol, session=self.session).dividends
            if dividends.empty:
                return 0
            cutoff = self._cutoff(dividends.index, 365)
            return int((dividends[dividends.index >= cutoff] > 0).sum())
        except Exception:
            return 0

    def history(self, symbol: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
        symbol = self._clean_symbol(symbol)
        if period not in {"5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "max"}:
            raise ValueError("Geçersiz tarih aralığı.")
        if interval not in {"1d", "1h", "1wk", "1mo"}:
            raise ValueError("Geçersiz veri aralığı.")

        def load():
            return self._download_history(symbol, period, interval)

        return self._cached(("history", symbol, period, interval), load)

    def _download_history(self, symbol: str, period: str, interval: str) -> pd.DataFrame:
        last_error = None
        for attempt in range(2):
            try:
                data = yf.download(
                    symbol, period=period, interval=interval, progress=False,
                    auto_adjust=False, session=self.session,
                )
                if data.empty:
                    raise ValueError(f"{symbol} icin veri bulunamadi.")
                if isinstance(data.columns, pd.MultiIndex):
                    data.columns = data.columns.get_level_values(0)
                return data.dropna(subset=["Close"])
            except Exception as exc:
                last_error = exc
                logger.exception("Piyasa verisi denemesi basarisiz: %s", symbol)
                if attempt == 0:
                    time.sleep(0.5)
        raise RuntimeError(f"Piyasa verisi alinamadi: {last_error}") from last_error

    def quote(self, symbol: str) -> dict[str, Any]:
        symbol = self._clean_symbol(symbol)

        def load():
            return self._load_quote(symbol)

        return self._cached(("quote", symbol), load)

    def _load_quote(self, symbol: str) -> dict[str, Any]:
        try:
            ticker = yf.Ticker(symbol, session=self.session)
            info = ticker.fast_info
            history = ticker.history(period="2d", interval="1d")
            if history.empty:
                raise ValueError("Son fiyat yok.")
            close = float(history["Close"].iloc[-1])
            previous = float(history["Close"].iloc[-2]) if len(history) > 1 else close
            return {
                "symbol": symbol.upper(),
                "price": close,
                "change": close - previous,
                "change_pct": ((close / previous) - 1) * 100 if previous else 0,
                "currency": getattr(info, "currency", "USD") or "USD",
            }
        except Exception as exc:
            logger.exception("Fiyat bilgisi alinamadi: %s", symbol)
            raise RuntimeError(f"Fiyat bilgisi alinamadi: {exc}") from exc

    def dividend_info(self, symbol: str) -> dict[str, Any]:
        """Son 12 aydaki gerçek ödemelerden hisse başı temettüyü hesaplar."""
        symbol = self._clean_symbol(symbol)

        def load():
            return self._load_dividend_info(symbol)

        return self._cached(("dividend", symbol), load)

    def _load_dividend_info(self, symbol: str) -> dict[str, Any]:
        try:
            ticker = yf.Ticker(symbol, session=self.session)
            dividends = ticker.dividends
            if dividends.empty:
                return {"annual_per_share": 0.0, "payment_count": 0}
            cutoff = self._cutoff(dividends.index, 365)
            recent = dividends[dividends.index >= cutoff]
            return {
                "annual_per_share": float(recent.sum()),
                "payment_count": int(len(recent)),
            }
        except Exception as exc:
            logger.exception("Temettu bilgisi alinamadi: %s", symbol)
            raise RuntimeError(f"Temettu bilgisi alinamadi: {exc}") from exc

    def fundamentals(self, symbol: str) -> dict[str, Any]:
        symbol = self._clean_symbol(symbol)
        try:
            info = yf.Ticker(symbol, session=self.session).info
            keys = ["longName", "sector", "marketCap", "trailingPE", "forwardPE", "dividendYield", "profitMargins", "returnOnEquity"]
            return {key: info.get(key) for key in keys}
        except Exception as exc:
            logger.exception("Temel veriler alinamadi: %s", symbol)
            raise RuntimeError(f"Temel veriler alinamadi: {exc}") from exc

    def financial_tables(self, symbol: str) -> dict[str, pd.DataFrame]:
        symbol = self._clean_symbol(symbol)
        try:
            ticker = yf.Ticker(symbol, session=self.session)
            return {"Gelir Tablosu": ticker.financials, "Bilanço": ticker.balance_sheet, "Nakit Akışı": ticker.cashflow}
        except Exception as exc:
            logger.exception("Finansal tablolar alinamadi: %s", symbol)
            raise RuntimeError(f"Finansal tablolar alinamadi: {exc}") from exc

    def monthly_dividend_payers(self, symbols: list[str]) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        for symbol in symbols:
            try:
                symbol = self._clean_symbol(symbol)
                ticker = yf.Ticker(symbol, session=self.session)
                dividends = ticker.dividends
                cutoff = self._cutoff(dividends.index, 370)
                recent = dividends[dividends.index >= cutoff]
                months = {stamp.to_period("M") for stamp in recent.index.tz_localize(None) if hasattr(stamp, "to_period")}
                info = ticker.info
                if len(months) >= 12:
                    rows.append({
                        "Sembol": symbol,
                        "Şirket": info.get("longName", symbol),
                        "Temettü Verimi": info.get("dividendYield", 0) or 0,
                        "Ödeme Sayısı": len(recent),
                    })
            except Exception:
                continue
        return pd.DataFrame(rows, columns=["Sembol", "Şirket", "Temettü Verimi", "Ödeme Sayısı"])
