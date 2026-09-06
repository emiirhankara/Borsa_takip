"""RSS tabanli sirket haber servisi."""
from html import unescape
from urllib.parse import quote

import feedparser


class NewsService:
    def fetch(self, symbol: str, limit: int = 12) -> list[dict[str, str]]:
        url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={quote(symbol)}&region=US&lang=en-US"
        try:
            parsed = feedparser.parse(url)
            return [{"title": unescape(entry.get("title", "Baslik yok")), "link": entry.get("link", ""), "published": entry.get("published", "")} for entry in parsed.entries[:limit]]
        except Exception as exc:
            raise RuntimeError(f"Haber akisi alinamadi: {exc}") from exc
