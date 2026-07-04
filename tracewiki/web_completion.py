from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote_plus, unquote, urlparse, parse_qs

import requests

from .config import Settings
from .ingest import ingest_path
from .models import StagingItem
from .storage import KnowledgeStore
from .system_log import record_event
from .wiki_builder import stable_id, summarize_text


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href = ""
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        attr = dict(attrs)
        href = attr.get("href") or ""
        if href:
            self._href = href
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href:
            text = normalize_text(" ".join(self._text))
            url = normalize_duckduckgo_url(self._href)
            if text and url.startswith("http"):
                self.links.append((text, url))
            self._href = ""
            self._text = []


class TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self._in_title = False
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self.skip_depth += 1
        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self.skip_depth:
            self.skip_depth -= 1
        if tag == "title":
            self._in_title = False
        if tag in {"p", "div", "li", "h1", "h2", "h3", "br"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        if self._in_title:
            self.title += data
        else:
            self.parts.append(data)


def web_search_to_staging(query: str, settings: Settings, store: KnowledgeStore, limit: int = 3) -> list[StagingItem]:
    candidates = search_duckduckgo(query, limit=limit)
    items = []
    for title, url in candidates:
        try:
            page_title, content = fetch_page_text(url)
        except Exception:
            continue
        final_title = page_title or title
        item = StagingItem(
            staging_id=stable_id(url + content[:200]),
            title=final_title[:160],
            url=url,
            summary=summarize_text(content, limit=260),
            content=content[:12000],
        )
        store.add_staging_item(item)
        items.append(item)
    record_event(
        store,
        "web_completion_staged",
        f"Staged {len(items)} web completion candidates",
        {"query": query, "urls": [item.url for item in items]},
    )
    return items


def merge_staging_item(staging_id: str, settings: Settings, store: KnowledgeStore):
    matches = [item for item in store.list_staging_items() if item.staging_id == staging_id]
    if not matches:
        raise ValueError("staging item not found")
    item = matches[0]
    web_dir = settings.raw_dir / "web"
    web_dir.mkdir(parents=True, exist_ok=True)
    path = web_dir / f"{safe_name(item.title)}.md"
    path.write_text(
        "\n".join(
            [
                f"# {item.title}",
                "",
                f"Source URL: {item.url}",
                "",
                item.content,
            ]
        ),
        encoding="utf-8",
    )
    card = ingest_path(path, settings, store)
    store.update_staging_status(staging_id, "merged")
    record_event(
        store,
        "web_completion_merged",
        f"Merged web staging item into Wiki: {item.title}",
        {"staging_id": staging_id, "card_id": card.card_id, "url": item.url},
    )
    return card


def search_duckduckgo(query: str, limit: int) -> list[tuple[str, str]]:
    url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
    response = requests.get(url, headers={"User-Agent": "TraceWiki/0.2"}, timeout=20)
    response.raise_for_status()
    parser = LinkParser()
    parser.feed(response.text)
    seen = set()
    results = []
    for title, href in parser.links:
        if href in seen or "duckduckgo.com" in href:
            continue
        seen.add(href)
        results.append((html.unescape(title), href))
        if len(results) >= limit:
            break
    return results


def fetch_page_text(url: str) -> tuple[str, str]:
    response = requests.get(url, headers={"User-Agent": "TraceWiki/0.2"}, timeout=20)
    response.raise_for_status()
    parser = TextParser()
    parser.feed(response.text)
    title = normalize_text(html.unescape(parser.title))
    content = normalize_text(html.unescape(" ".join(parser.parts)))
    return title, content


def normalize_duckduckgo_url(url: str) -> str:
    if url.startswith("//"):
        url = "https:" + url
    parsed = urlparse(url)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        uddg = parse_qs(parsed.query).get("uddg", [""])[0]
        if uddg:
            return unquote(uddg)
    return url


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def safe_name(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_\-\u4e00-\u9fff]+", "_", value).strip("_")
    return (safe or "web_completion")[:80]
