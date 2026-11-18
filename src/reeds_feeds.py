# SPDX-License-Identifier: Apache-2.0
"""Fetching and reading feeds: RSS 2.0, RSS 1.0 (RDF) and Atom, with the standard library only.

Everything here is plain data in, plain data out, so it runs in a worker thread and
the window only ever sees finished results.
"""

from __future__ import annotations

import gzip
import html
import http.client
import re
import time
import zlib
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

USER_AGENT = "Reeds/0.1 (feed reader for Luma)"
MAX_FEED_BYTES = 6 * 1024 * 1024
MAX_IMAGE_BYTES = 5 * 1024 * 1024
TIMEOUT = 15


class FeedError(Exception):
    """A feed could not be fetched or read. The message is plain and fit to show."""


@dataclass
class Item:
    guid: str
    title: str
    link: str = ""
    author: str = ""
    published: float = 0.0
    summary: str = ""        # HTML
    content: str = ""        # HTML
    image: str = ""


@dataclass
class Feed:
    url: str
    title: str = ""
    site_url: str = ""
    items: list[Item] = field(default_factory=list)
    etag: str = ""
    modified: str = ""
    not_modified: bool = False


# ── Network ─────────────────────────────────────────────────────────────────


def clean_url(text: str) -> str:
    """What a person typed, made into an address: adds https:// and drops feed: prefixes."""
    text = text.strip()
    if text.startswith("feed://"):
        text = "https://" + text[len("feed://"):]
    elif text.startswith("feed:"):
        text = text[len("feed:"):]
    if text and "://" not in text:
        text = "https://" + text
    parts = urlparse(text)
    host = parts.hostname or ""
    try:
        parts.port  # noqa: B018 (raises ValueError for a port that isn't a number)
        good_port = True
    except ValueError:
        good_port = False
    if (parts.scheme not in ("http", "https") or not host or not good_port or any(c.isspace() for c in text)
            or not re.fullmatch(r"[A-Za-z0-9._~-]+|[0-9A-Fa-f:.]+", host)):
        raise FeedError("That doesn’t look like a web address.")
    return text


def _download(url: str, *, etag: str = "", modified: str = "", limit: int = MAX_FEED_BYTES) -> tuple[bytes, dict]:
    headers = {"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate",
               "Accept": "application/atom+xml, application/rss+xml, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.5"}
    if etag:
        headers["If-None-Match"] = etag
    if modified:
        headers["If-Modified-Since"] = modified
    try:
        with urlopen(Request(url, headers=headers), timeout=TIMEOUT) as response:  # noqa: S310 (http/https only)
            if urlparse(response.geturl()).scheme not in ("http", "https"):
                raise FeedError("The address redirected somewhere that isn’t a web page.")
            raw = response.read(limit + 1)
            info = {"etag": response.headers.get("ETag", ""), "modified": response.headers.get("Last-Modified", ""),
                    "url": response.geturl(), "type": response.headers.get("Content-Type", "")}
            encoding = (response.headers.get("Content-Encoding") or "").lower()
    except HTTPError as error:
        if error.code == 304:
            return b"", {"not_modified": True}
        raise FeedError(f"The site answered with an error ({error.code}).") from error
    except (URLError, TimeoutError, OSError, ValueError, http.client.HTTPException) as error:
        raise FeedError("Couldn’t reach that address. Check it and your connection.") from error
    if len(raw) > limit:
        raise FeedError("That file is too large to read.")
    try:
        if encoding == "gzip" or raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        elif encoding == "deflate":
            raw = zlib.decompress(raw)
    except (OSError, zlib.error) as error:
        raise FeedError("The feed arrived damaged.") from error
    if len(raw) > limit * 4:
        raise FeedError("That file is too large to read.")
    return raw, info


def fetch_bytes(url: str, limit: int = MAX_IMAGE_BYTES) -> bytes:
    """A picture or other small file. Raises FeedError."""
    data, _ = _download(url, limit=limit)
    return data


def fetch_feed(url: str, *, etag: str = "", modified: str = "") -> Feed:
    """Fetch and read a feed. If `url` is a web page that points to one, follow the pointer."""
    raw, info = _download(url, etag=etag, modified=modified)
    if info.get("not_modified"):
        return Feed(url=url, not_modified=True, etag=etag, modified=modified)
    feed = parse_feed(raw, info.get("url") or url)
    if feed is None:
        found = discover_feeds(raw, info.get("url") or url)
        if not found:
            raise FeedError("There’s no feed at that address.")
        raw, info = _download(found[0])
        feed = parse_feed(raw, info.get("url") or found[0])
        if feed is None:
            raise FeedError("There’s no feed at that address.")
    feed.etag = info.get("etag", "")
    feed.modified = info.get("modified", "")
    return feed


# ── Finding a feed in a web page ────────────────────────────────────────────


class _LinkFinder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.found: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag != "link":
            return
        data = {name: (value or "") for name, value in attrs}
        kinds = data.get("type", "").lower()
        if "alternate" in data.get("rel", "").lower().split() and ("rss" in kinds or "atom" in kinds):
            if data.get("href"):
                self.found.append(data["href"])


def discover_feeds(page: bytes, base: str) -> list[str]:
    finder = _LinkFinder()
    try:
        finder.feed(page.decode("utf-8", "replace"))
    except Exception:  # a broken page is just a page without feeds
        return []
    return [urljoin(base, href) for href in finder.found if urlparse(urljoin(base, href)).scheme in ("http", "https")]


# ── Reading the XML ─────────────────────────────────────────────────────────


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _kids(node: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in node if _local(child.tag) == name]


def _first(node: ET.Element, *names: str) -> ET.Element | None:
    for name in names:
        for child in node:
            if _local(child.tag) == name:
                return child
    return None


def _text(node: ET.Element | None) -> str:
    if node is None:
        return ""
    if len(node) and _local(node.tag) in ("content", "summary", "title"):  # Atom xhtml
        return (node.text or "") + "".join(ET.tostring(child, encoding="unicode") for child in node)
    return (node.text or "").strip()


def _date(text: str) -> float:
    text = (text or "").strip()
    if not text:
        return 0.0
    try:
        return parsedate_to_datetime(text).timestamp()
    except (TypeError, ValueError, IndexError):
        pass
    match = re.match(r"(\d{4})-(\d\d)-(\d\d)(?:[T ](\d\d):(\d\d)(?::(\d\d))?(?:\.\d+)?)?\s*(Z|[+-]\d\d:?\d\d)?", text)
    if not match:
        return 0.0
    year, month, day, hour, minute, second, zone = match.groups()
    import calendar
    stamp = calendar.timegm((int(year), int(month), int(day), int(hour or 0), int(minute or 0), int(second or 0)))
    if zone and zone != "Z":
        sign = -1 if zone[0] == "-" else 1
        digits = zone[1:].replace(":", "")
        stamp -= sign * (int(digits[:2]) * 3600 + int(digits[2:]) * 60)
    return float(stamp)


def _plain(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text or ""))).strip()


def parse_feed(raw: bytes, url: str) -> Feed | None:
    """Read RSS, RDF or Atom. Returns None when the bytes are not a feed (so the caller can look for one)."""
    head = raw[:4096].lstrip().lower()
    if b"<!entity" in raw[:20000].lower():
        raise FeedError("That feed uses a feature that isn’t safe to read.")
    if not (head.startswith(b"<?xml") or head.startswith(b"<rss") or head.startswith(b"<feed") or head.startswith(b"<rdf")):
        return None
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return None
    kind = _local(root.tag).lower()
    if kind == "rss":
        channel = _first(root, "channel")
        if channel is None:
            return None
        return _read_rss(channel, channel, url)
    if kind == "rdf":
        channel = _first(root, "channel")
        return _read_rss(root, channel if channel is not None else root, url)
    if kind == "feed":
        return _read_atom(root, url)
    return None


def _image_in(node: ET.Element, body: str) -> str:
    for child in node:
        name = _local(child.tag)
        if name in ("thumbnail", "content") and child.get("url") and (
                child.get("medium") == "image" or "image" in (child.get("type") or "") or name == "thumbnail"):
            return child.get("url") or ""
        if name == "enclosure" and "image" in (child.get("type") or "") and child.get("url"):
            return child.get("url") or ""
    match = re.search(r"<img[^>]+src=[\"']([^\"']+)", body or "", re.I)
    return match.group(1) if match else ""


def _read_rss(items_parent: ET.Element, channel: ET.Element, url: str) -> Feed:
    feed = Feed(url=url, title=_plain(_text(_first(channel, "title"))), site_url=_text(_first(channel, "link")))
    for node in _kids(items_parent, "item"):
        link = _text(_first(node, "link"))
        guid = _text(_first(node, "guid")) or link or _text(_first(node, "title"))
        if not guid:
            continue
        body = _text(_first(node, "encoded")) or ""
        summary = _text(_first(node, "description"))
        author = _plain(_text(_first(node, "creator")) or _text(_first(node, "author")))
        feed.items.append(Item(
            guid=guid, title=_plain(_text(_first(node, "title"))) or "Untitled", link=link, author=author,
            published=_date(_text(_first(node, "pubDate")) or _text(_first(node, "date")) or _text(_first(node, "published"))),
            summary=summary, content=body, image=_image_in(node, body or summary)))
    return feed


def _atom_link(node: ET.Element, *, rel: str = "alternate") -> str:
    best = ""
    for link in _kids(node, "link"):
        kind = link.get("rel") or "alternate"
        if kind == rel and link.get("href"):
            return link.get("href") or ""
        if not best and link.get("href") and rel == "alternate" and not link.get("rel"):
            best = link.get("href") or ""
    return best


def _read_atom(root: ET.Element, url: str) -> Feed:
    feed = Feed(url=url, title=_plain(_text(_first(root, "title"))), site_url=_atom_link(root))
    base = feed.site_url or url
    for node in _kids(root, "entry"):
        link = urljoin(base, _atom_link(node))
        guid = _text(_first(node, "id")) or link or _text(_first(node, "title"))
        if not guid:
            continue
        author_node = _first(node, "author")
        author = _plain(_text(_first(author_node, "name")) if author_node is not None else "")
        body = _text(_first(node, "content"))
        summary = _text(_first(node, "summary"))
        feed.items.append(Item(
            guid=guid, title=_plain(_text(_first(node, "title"))) or "Untitled", link=link, author=author,
            published=_date(_text(_first(node, "published")) or _text(_first(node, "updated"))),
            summary=summary, content=body, image=_image_in(node, body or summary)))
    return feed


# ── OPML ────────────────────────────────────────────────────────────────────


def read_opml(raw: bytes) -> list[tuple[str, str, str]]:
    """(title, feed address, folder) for every feed in an OPML file."""
    if b"<!entity" in raw[:20000].lower():
        raise FeedError("That file uses a feature that isn’t safe to read.")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as error:
        raise FeedError("That file isn’t a feed list.") from error
    found: list[tuple[str, str, str]] = []

    def walk(node: ET.Element, folder: str) -> None:
        for child in node:
            if _local(child.tag) != "outline":
                continue
            address = child.get("xmlUrl") or child.get("xmlurl") or ""
            title = child.get("title") or child.get("text") or ""
            if address:
                found.append((title, address, folder))
            else:
                walk(child, title or folder)

    body = _first(root, "body")
    if body is None:
        raise FeedError("That file isn’t a feed list.")
    walk(body, "")
    return found


def write_opml(feeds: list[tuple[str, str, str, str]]) -> bytes:
    """(title, feed address, site address, folder) in, an OPML file out."""
    esc = lambda text: html.escape(text or "", quote=True)  # noqa: E731
    folders: dict[str, list[str]] = {}
    for title, address, site, folder in feeds:
        folders.setdefault(folder or "", []).append(
            f'<outline type="rss" text="{esc(title)}" title="{esc(title)}" xmlUrl="{esc(address)}" htmlUrl="{esc(site)}"/>')
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<opml version="2.0">', "<head><title>Reeds feeds</title></head>", "<body>"]
    for folder, rows in folders.items():
        if folder:
            lines.append(f'<outline text="{esc(folder)}" title="{esc(folder)}">')
            lines.extend(rows)
            lines.append("</outline>")
        else:
            lines.extend(rows)
    lines += ["</body>", "</opml>"]
    return "\n".join(lines).encode("utf-8")


# ── Turning article HTML into blocks the window can lay out ─────────────────

_BLOCK = {"p", "div", "section", "article", "header", "footer", "figure", "figcaption", "main", "aside", "table",
          "tr", "ul", "ol", "dl", "dd", "dt", "details", "summary"}
_SKIP = {"script", "style", "noscript", "iframe", "svg", "form", "button", "head", "template", "object", "embed"}


@dataclass
class Block:
    kind: str                # p, h1, h2, h3, quote, pre, li, img, hr
    text: str = ""           # Pango markup for text blocks
    src: str = ""            # image address
    alt: str = ""
    number: int = 0          # list item: 0 for a bullet, else its place in an ordered list


class _Reader(HTMLParser):
    def __init__(self, base: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base = base
        self.blocks: list[Block] = []
        self.buffer: list[str] = []
        self.kind = "p"
        self.skip = 0
        self.pre = 0
        self.lists: list[list[int]] = []   # [ordered, counter]
        self.quote = 0
        self.links: list[str] = []
        self.number = 0

    # text is kept as Pango markup so bold, italics, code and links survive
    def _flush(self) -> None:
        text = "".join(self.buffer)
        self.buffer = []
        if self.kind == "pre":
            text = text.strip("\n")
            if text.strip():
                self.blocks.append(Block("pre", text))
        else:
            text = re.sub(r"[ \t\r\n]+", " ", text).strip()
            text = re.sub(r"(<[^/>][^>]*>)\s+", r"\1", text)
            if _plain(text):
                kind = "quote" if self.quote and self.kind == "p" else self.kind
                self.blocks.append(Block(kind, text, number=self.number))
        self.kind = "p"
        self.number = 0

    def _start(self, kind: str = "p") -> None:
        self._flush()
        self.kind = kind

    def handle_starttag(self, tag: str, attrs: list) -> None:
        data = {name: (value or "") for name, value in attrs}
        if tag in _SKIP:
            self.skip += 1
            return
        if self.skip:
            return
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._start("h1" if tag == "h1" else "h2" if tag in ("h2", "h3") else "h3")
        elif tag == "br":
            self.buffer.append("\n" if self.pre else " ")
            if not self.pre:
                self._start(self.kind)
        elif tag == "blockquote":
            self._start("p")
            self.quote += 1
        elif tag == "pre":
            self._start("pre")
            self.pre += 1
        elif tag in ("ul", "ol"):
            self._start("p")
            self.lists.append([1 if tag == "ol" else 0, 0])
        elif tag == "li":
            self._start("li")
            if self.lists:
                self.lists[-1][1] += 1
                self.number = self.lists[-1][1] if self.lists[-1][0] else 0
        elif tag == "hr":
            self._start("p")
            self.blocks.append(Block("hr"))
        elif tag == "img":
            self._start("p")
            src = data.get("src") or data.get("data-src") or ""
            if src and not src.startswith("data:"):
                width = data.get("width", "")
                if not (width.isdigit() and int(width) < 24):     # tracking pixels and icons
                    self.blocks.append(Block("img", src=urljoin(self.base, src), alt=_plain(data.get("alt", ""))))
        elif tag in ("b", "strong"):
            self.buffer.append("<b>")
        elif tag in ("i", "em", "cite"):
            self.buffer.append("<i>")
        elif tag in ("code", "kbd", "samp", "tt") and not self.pre:
            self.buffer.append("<tt>")
        elif tag == "sub":
            self.buffer.append("<sub>")
        elif tag == "sup":
            self.buffer.append("<sup>")
        elif tag in ("s", "strike", "del"):
            self.buffer.append("<s>")
        elif tag == "a":
            href = urljoin(self.base, data.get("href", ""))
            if urlparse(href).scheme in ("http", "https", "mailto"):
                self.buffer.append(f'<a href="{html.escape(href, quote=True)}">')
                self.links.append("a")
            else:
                self.links.append("")
        elif tag in _BLOCK:
            self._start("p")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6", "li", "pre"):
            self._flush()
            if tag == "pre":
                self.pre = max(0, self.pre - 1)
        elif tag == "blockquote":
            self._flush()
            self.quote = max(0, self.quote - 1)
        elif tag in ("ul", "ol"):
            self._flush()
            if self.lists:
                self.lists.pop()
        elif tag in ("b", "strong"):
            self.buffer.append("</b>")
        elif tag in ("i", "em", "cite"):
            self.buffer.append("</i>")
        elif tag in ("code", "kbd", "samp", "tt") and not self.pre:
            self.buffer.append("</tt>")
        elif tag == "sub":
            self.buffer.append("</sub>")
        elif tag == "sup":
            self.buffer.append("</sup>")
        elif tag in ("s", "strike", "del"):
            self.buffer.append("</s>")
        elif tag == "a":
            if self.links and self.links.pop():
                self.buffer.append("</a>")
        elif tag in _BLOCK:
            self._flush()

    def handle_data(self, data: str) -> None:
        if self.skip:
            return
        self.buffer.append(html.escape(data, quote=False))

    def close(self) -> None:  # noqa: D401
        super().close()
        self._flush()


def article_blocks(body: str, base: str = "") -> list[Block]:
    """Article HTML as a short list of blocks. Unclosed tags and odd markup are fine."""
    reader = _Reader(base)
    try:
        reader.feed(body or "")
        reader.close()
    except Exception:  # damaged markup: show what was read
        reader._flush()
    # Pango markup must balance: close anything a block left open.
    for block in reader.blocks:
        if block.text:
            block.text = _balanced(block.text)
    return reader.blocks


def _balanced(markup: str) -> str:
    stack: list[str] = []
    out: list[str] = []
    for part in re.split(r"(<[^>]+>)", markup):
        if part.startswith("</"):
            name = part[2:-1].strip()
            if name in stack:
                while stack and stack[-1] != name:
                    out.append(f"</{stack.pop()}>")
                stack.pop()
                out.append(part)
        elif part.startswith("<"):
            name = part[1:-1].split()[0]
            stack.append(name)
            out.append(part)
        else:
            out.append(part)
    while stack:
        out.append(f"</{stack.pop()}>")
    return "".join(out)


def snippet(item_html: str, limit: int = 140) -> str:
    text = _plain(item_html)
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "…"


def reading_minutes(item_html: str) -> int:
    words = len(_plain(item_html).split())
    return max(1, round(words / 230)) if words else 0


def relative(stamp: float, now: float | None = None) -> str:
    """"5 min", "3 h", "Yesterday", "12 Nov": short enough for a list row."""
    if not stamp:
        return ""
    now = now or time.time()
    delta = now - stamp
    if delta < 60:
        return "Now"
    if delta < 3600:
        return f"{int(delta // 60)} min"
    if delta < 86400:
        return f"{int(delta // 3600)} h"
    then, today = time.localtime(stamp), time.localtime(now)
    midnight = time.mktime((today.tm_year, today.tm_mon, today.tm_mday, 0, 0, 0, 0, 0, -1))
    if midnight - 86400 <= stamp < midnight:
        return "Yesterday"
    if delta < 6 * 86400:
        return time.strftime("%a", then)
    return time.strftime("%-d %b" if then.tm_year == today.tm_year else "%-d %b %Y", then)
