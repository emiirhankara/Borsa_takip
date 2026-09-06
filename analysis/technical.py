"""Teknik indikatörler ve basit, aciklanabilir istatistiksel tahmin."""
from dataclasses import dataclass
import numpy as np
import pandas as pd


@dataclass
class Forecast:
    horizon: str
    target_price: float
    change_pct: float
    confidence: str
    signal: str


def indicators(data: pd.DataFrame) -> pd.DataFrame:
    result = data.copy()
    close = result["Close"].astype(float)
    result["SMA20"] = close.rolling(20).mean()
    result["SMA50"] = close.rolling(50).mean()
    result["EMA12"] = close.ewm(span=12, adjust=False).mean()
    result["EMA26"] = close.ewm(span=26, adjust=False).mean()
    result["MACD"] = result["EMA12"] - result["EMA26"]
    result["MACD_Signal"] = result["MACD"].ewm(span=9, adjust=False).mean()
    delta = close.diff()
    gains = delta.clip(lower=0).rolling(14).mean()
    losses = -delta.clip(upper=0).rolling(14).mean()
    result["RSI"] = 100 - (100 / (1 + gains / losses.replace(0, np.nan)))
    return result


def forecast(data: pd.DataFrame) -> list[Forecast]:
    if len(data) < 30:
        raise ValueError("Tahmin icin en az 30 gunluk veri gerekir.")
    frame = indicators(data).dropna()
    close = frame["Close"].astype(float)
    daily_returns = close.pct_change().dropna()
    drift = float(daily_returns.tail(60).mean())
    volatility = float(daily_returns.tail(60).std())
    latest = float(close.iloc[-1])
    rsi = float(frame["RSI"].iloc[-1])
    macd_bias = float(frame["MACD"].iloc[-1] - frame["MACD_Signal"].iloc[-1])
    momentum = np.clip(drift + (0.0004 if macd_bias > 0 else -0.0004), -0.02, 0.02)
    horizons = [("1 Ay", 21), ("3 Ay", 63), ("6 Ay", 126)]
    result = []
    for label, days in horizons:
        target = latest * ((1 + momentum) ** days)
        change = (target / latest - 1) * 100
        confidence = "Dusuk" if volatility > 0.035 else "Orta" if volatility > 0.018 else "Yuksek"
        signal = "Asiri alim" if rsi > 70 else "Asiri satim" if rsi < 30 else ("Pozitif" if momentum > 0 else "Negatif")
        result.append(Forecast(label, target, change, confidence, signal))
    return result
