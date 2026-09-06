"""Yahoo Finance uzerinden guvenli piyasa verisi servisi."""
from dataclasses import dataclass
from typing import Any

import pandas as pd
import yfinance as yf


@dataclass
class MarketDataError:
    message: str


class MarketDataService:
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
