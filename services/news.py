"""RSS tabanli sirket haber servisi."""
from html import unescape
import logging
import re
from urllib.parse import quote

import feedparser


logger = logging.getLogger(__name__)


class NewsService:
    def fetch(self, symbol: str, limit: int = 12) -> list[dict[str, str]]:
        url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={quote(symbol)}&region=US&lang=en-US"
        try:
            parsed = feedparser.parse(url)
            articles = []
            for entry in parsed.entries[:limit]:
                summary = re.sub(r"<[^>]+>", " ", entry.get("summary", ""))
                summary = " ".join(unescape(summary).split())
                source = entry.get("source", {}).get("title", "Yahoo Finance")
                articles.append({
                    "title": unescape(entry.get("title", "Baslik yok")),
                    "link": entry.get("link", ""),
                    "published": entry.get("published", ""),
                    "summary": summary[:320] or "Bu haber için kısa özet bulunamadı.",
                    "source": source,
                })
            return articles
        except Exception as exc:
            logger.exception("Haber akisi alinamadi: %s", symbol)
            raise RuntimeError(f"Haber akisi alinamadi: {exc}") from exc
