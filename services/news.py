"""RSS tabanli sirket haber servisi."""
from html import unescape
import logging
import re
from urllib.parse import quote

import feedparser


logger = logging.getLogger(__name__)


class NewsService:
    def fetch(self, symbol: str, limit: int = 15) -> list[dict[str, str]]:
        symbol = symbol.strip().upper()
        is_bist = symbol.endswith(".IS")
        clean_symbol = symbol[:-3] if is_bist else symbol

        articles = []

        # 1. Primary source: Google News RSS
        try:
            if is_bist:
                q = quote(f"{clean_symbol} hisse")
                url = f"https://news.google.com/rss/search?q={q}&hl=tr&gl=TR&ceid=TR:tr"
            else:
                q = quote(f"{clean_symbol} stock")
                url = f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"

            parsed = feedparser.parse(url)
            for entry in parsed.entries[:limit]:
                title = unescape(entry.get("title", "Başlık yok"))
                source = "Piyasa Gündemi"
                if entry.get("source") and entry.get("source").get("title"):
                    source = entry.get("source").get("title")
                elif " - " in title:
                    parts = title.rsplit(" - ", 1)
                    title = parts[0].strip()
                    source = parts[1].strip()

                raw_summary = re.sub(r"<[^>]+>", " ", entry.get("summary", ""))
                summary = " ".join(unescape(raw_summary).split())
                if not summary or summary.startswith("http") or len(summary) < 15:
                    summary = f"{clean_symbol} hissesi ile ilgili en son piyasa gelişmeleri, borsa analizleri ve şirket haberleri."

                published = entry.get("published", "")
                if len(published) > 16:
                    published = published[:16]

                articles.append({
                    "title": title,
                    "link": entry.get("link", ""),
                    "published": published or "Güncel",
                    "summary": summary[:300],
                    "source": source,
                })
        except Exception as exc:
            logger.warning("Google News alinamadi: %s - %s", symbol, exc)

        # 2. Fallback for US stocks or if Google News returned empty: Yahoo Finance RSS
        if not articles and not is_bist:
            try:
                yf_url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={quote(symbol)}&region=US&lang=en-US"
                parsed_yf = feedparser.parse(yf_url)
                for entry in parsed_yf.entries[:limit]:
                    summary = re.sub(r"<[^>]+>", " ", entry.get("summary", ""))
                    summary = " ".join(unescape(summary).split())
                    source = entry.get("source", {}).get("title", "Yahoo Finance")
                    articles.append({
                        "title": unescape(entry.get("title", "Başlık yok")),
                        "link": entry.get("link", ""),
                        "published": entry.get("published", "")[:16] or "Güncel",
                        "summary": summary[:300] or f"{symbol} şirketine ait güncel finansal rapor ve gelişmeler.",
                        "source": source,
                    })
            except Exception as exc:
                logger.warning("Yahoo Finance haberleri alinamadi: %s - %s", symbol, exc)

        return articles
