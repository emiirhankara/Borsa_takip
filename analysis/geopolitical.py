"""Haberlerdeki jeopolitik riskten aciklanabilir senaryo skoru uretir."""
from dataclasses import dataclass
import re
from typing import Iterable


@dataclass(frozen=True)
class GeopoliticalAssessment:
    up_probability: int
    down_probability: int
    risk_level: str
    summary: str
    matched_topics: tuple[str, ...]


ESCALATION_TERMS = {
    "war": "savas",
    "conflict": "catisma",
    "invasion": "istila",
    "attack": "saldiri",
    "missile": "fuze",
    "drone": "iha/sihali",
    "airstrike": "hava saldirisi",
    "strike": "saldiri",
    "troops": "asker",
    "military": "askeri",
    "sanctions": "yaptirim",
    "tariff": "gumruk vergisi",
    "blockade": "abluka",
    "ceasefire": "ateskes",
    "peace talks": "baris gorusmesi",
    "de-escalation": "gerilimin azalmasi",
}

NEGATIVE_TERMS = {
    "war", "conflict", "invasion", "attack", "missile", "drone", "airstrike",
    "strike", "troops", "military", "sanctions", "tariff", "blockade",
}
POSITIVE_TERMS = {"ceasefire", "peace talks", "de-escalation", "peace agreement", "truce"}


def assess_news(articles: Iterable[dict[str, str]]) -> GeopoliticalAssessment:
    """Haber basliklarindan yon ve risk olasiligi hesaplar.

    Bu, piyasa tahmini degil; son haberlerdeki jeopolitik ifadelerin basit bir
    siniflandirmasidir. Haber yoksa olasiliklar esit ve risk bilinmiyor olur.
    """
    text = " ".join(
        f"{article.get('title', '')} {article.get('summary', '')}"
        for article in articles
    ).lower()
    if not text.strip():
        return GeopoliticalAssessment(50, 50, "Bilinmiyor", "Jeopolitik haber verisi yok.", ())

    negative_hits = sum(len(re.findall(rf"\b{re.escape(term)}\b", text)) for term in NEGATIVE_TERMS)
    positive_hits = sum(len(re.findall(rf"\b{re.escape(term)}\b", text)) for term in POSITIVE_TERMS)
    matched = tuple(dict.fromkeys(
        label for term, label in ESCALATION_TERMS.items() if re.search(rf"\b{re.escape(term)}\b", text)
    ))
    total_hits = negative_hits + positive_hits
    if not total_hits:
        return GeopoliticalAssessment(50, 50, "Dusuk", "Son haberlerde belirgin bir savas/jeopolitik sinyal bulunmadi.", ())

    net_score = negative_hits - positive_hits
    risk_level = "Yuksek" if total_hits >= 4 else "Orta" if total_hits >= 2 else "Dusuk"
    down_probability = max(15, min(85, 50 + net_score * 8))
    up_probability = 100 - down_probability
    if net_score > 0:
        summary = "Gerilim haberleri agirlikta; dusus riski artiyor."
    elif net_score < 0:
        summary = "Ateskes/baris haberleri agirlikta; toparlanma ihtimali destekleniyor."
    else:
        summary = "Olumlu ve olumsuz jeopolitik haberler dengeli."
    return GeopoliticalAssessment(up_probability, down_probability, risk_level, summary, matched)
