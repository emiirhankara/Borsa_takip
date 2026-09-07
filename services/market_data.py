"""Yahoo Finance uzerinden guvenli piyasa verisi servisi."""
from dataclasses import dataclass
from typing import Any

import pandas as pd
import yfinance as yf
from yfinance import EquityQuery


@dataclass
class MarketDataError:
    message: str


class MarketDataService:
    def screener_quotes(self, market: str) -> list[dict[str, Any]]:
        """Yahoo Finance tarayıcısından piyasanın güncel hisse listesini getirir."""
        exchanges = ["IST"] if market == "BIST" else ["NMS", "NYQ", "ASE"]
        query = EquityQuery("is-in", ["exchange", *exchanges])
        try:
            first = yf.screen(query, offset=0, count=250, sortField="intradaymarketcap", sortAsc=False)
            total = int(first.get("total", 0))
            quotes = list(first.get("quotes", []))
            offset = len(quotes)
            while offset < total and quotes:
                page = yf.screen(query, offset=offset, count=250, sortField="intradaymarketcap", sortAsc=False)
                page_quotes = page.get("quotes", [])
                quotes.extend(page_quotes)
                offset += len(page_quotes)
            return [
                {
                    "symbol": item.get("symbol", ""),
                    "name": item.get("shortName") or item.get("longName") or item.get("symbol", ""),
                    "price": float(item.get("regularMarketPrice") or 0),
                    "change_pct": float(item.get("regularMarketChangePercent") or 0),
                    "volume": int(item.get("regularMarketVolume") or 0),
                    "market_cap": float(item.get("marketCap") or 0),
                    "currency": item.get("currency", "USD"),
                }
                for item in quotes
                if item.get("symbol")
            ]
        except Exception as exc:
            raise RuntimeError(f"{market} hisse listesi alinamadi: {exc}") from exc

    def history(self, symbol: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
        symbol = symbol.strip().upper()
        if not symbol:
            raise ValueError("Hisse sembolu bos olamaz.")
        try:
            data = yf.download(symbol, period=period, interval=interval, progress=False, auto_adjust=False)
            if data.empty:
                raise ValueError(f"{symbol} icin veri bulunamadi.")
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.get_level_values(0)
            return data.dropna(subset=["Close"])
        except Exception as exc:
            raise RuntimeError(f"Piyasa verisi alinamadi: {exc}") from exc

    def quote(self, symbol: str) -> dict[str, Any]:
        try:
            ticker = yf.Ticker(symbol.strip().upper())
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
            raise RuntimeError(f"Fiyat bilgisi alinamadi: {exc}") from exc

    def dividend_info(self, symbol: str) -> dict[str, Any]:
        """Son 12 aydaki gerçek ödemelerden hisse başı temettüyü hesaplar."""
        try:
            ticker = yf.Ticker(symbol.strip().upper())
            dividends = ticker.dividends
            if dividends.empty:
                return {"annual_per_share": 0.0, "payment_count": 0}
            cutoff = pd.Timestamp.now(tz=dividends.index.tz) - pd.Timedelta(days=365) if getattr(dividends.index, "tz", None) else pd.Timestamp.now() - pd.Timedelta(days=365)
            recent = dividends[dividends.index >= cutoff]
            return {
                "annual_per_share": float(recent.sum()),
                "payment_count": int(len(recent)),
            }
        except Exception as exc:
            raise RuntimeError(f"Temettu bilgisi alinamadi: {exc}") from exc

    def fundamentals(self, symbol: str) -> dict[str, Any]:
        try:
            info = yf.Ticker(symbol.strip().upper()).info
            keys = ["longName", "sector", "marketCap", "trailingPE", "forwardPE", "dividendYield", "profitMargins", "returnOnEquity"]
            return {key: info.get(key) for key in keys}
        except Exception as exc:
            raise RuntimeError(f"Temel veriler alinamadi: {exc}") from exc

    def financial_tables(self, symbol: str) -> dict[str, pd.DataFrame]:
        try:
            ticker = yf.Ticker(symbol.strip().upper())
            return {"Gelir Tablosu": ticker.financials, "Bilanço": ticker.balance_sheet, "Nakit Akışı": ticker.cashflow}
        except Exception as exc:
            raise RuntimeError(f"Finansal tablolar alinamadi: {exc}") from exc

    def monthly_dividend_payers(self, symbols: list[str]) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        for symbol in symbols:
            try:
                ticker = yf.Ticker(symbol)
                dividends = ticker.dividends
                cutoff = pd.Timestamp.now(tz=dividends.index.tz) - pd.Timedelta(days=370) if getattr(dividends.index, "tz", None) else pd.Timestamp.now() - pd.Timedelta(days=370)
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
