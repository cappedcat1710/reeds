# SPDX-License-Identifier: Apache-2.0
"""Getting the whole article when a feed only sends a title or a teaser.

`extract(page_html, base_url)` finds the text of the article in a web page, the way a reader mode
does: it parses the page leniently, drops what is plainly not the article (navigation, comments,
share buttons, related links, scripts), scores the page's containers by how much running text they
hold, and returns the best one as clean HTML that `reeds_feeds.article_blocks` can lay out.

Standard library only. Nothing here touches the network; `reeds_feeds.fetch_page` does that.
"""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

MAX_NODES = 80_000
MAX_DEPTH = 220
MIN_WORDS = 80                   # less than this is not an article, so the feed's own text is kept

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
BLOCKS = {"p", "div", "section", "article", "main", "ul", "ol", "li", "dl", "dd", "dt", "blockquote", "pre", "table",
          "tr", "figure", "figcaption", "h1", "h2", "h3", "h4", "h5", "h6", "header", "footer", "aside", "details", "hr"}
DROP = {"script", "style", "noscript", "template", "svg", "form", "button", "nav", "footer", "aside", "iframe", "object",
        "embed", "select", "input", "textarea", "dialog", "canvas", "audio", "video", "map", "head", "link", "meta",
        "label", "menu", "source", "track"}
KEEP_INLINE = {"a": "a", "em": "em", "i": "i", "cite": "em", "strong": "strong", "b": "strong", "code": "code",
               "kbd": "code", "samp": "code", "tt": "code", "sub": "sub", "sup": "sup", "s": "s", "del": "s",
               "strike": "s", "br": "br"}
KEEP_BLOCK = {"p", "ul", "ol", "li", "blockquote", "pre", "h1", "h2", "h3", "h4", "h5", "h6", "figure", "figcaption",
              "hr", "table", "tr", "dl", "dt", "dd"}
PASS_BLOCK = {"div", "section", "article", "main", "header", "details", "summary"}   # kept only as block boundaries

NEGATIVE = re.compile(
    r"(^|[\s_-])(comment|comments|disqus|share|sharing|social|related|recommend|recommended|promo|promoted|advert|advertisement|"
    r"ad|ads|adslot|newsletter|subscribe|subscription|signup|sidebar|cookie|consent|modal|popup|breadcrumb|breadcrumbs|"
    r"sponsor|sponsored|outbrain|taboola|toolbar|masthead|pagination|pager|print|skip|sr-only|visually-hidden|"
    r"read-more|more-stories|trending|most-read|footer|tags|tag-list|author-bio|bio|byline-extra|reactions|"
    r"paywall-prompt|login|register)($|[\s_-])", re.I)
POSITIVE = re.compile(r"(article|articlebody|article-body|post-content|entry-content|story-body|story|content-body|"
                      r"post-body|body-text|main-content|rich-text|text-block|prose)", re.I)
STRONG_POSITIVE = re.compile(r"(articlebody|article-body|post-content|entry-content|story-body|post-body|articletext)", re.I)


class Node:
    __slots__ = ("tag", "attrs", "kids", "parent", "text")

    def __init__(self, tag: str, attrs: dict | None = None, parent: "Node | None" = None, text: str = "") -> None:
        self.tag, self.attrs, self.kids, self.parent, self.text = tag, attrs or {}, [], parent, text


class _Tree(HTMLParser):
    """A forgiving DOM builder: unclosed tags, stray end tags and odd nesting are all fine."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("#root")
        self.cur = self.root
        self.count = 0
        self.depth = 0
        self.full = False

    def _add(self, node: Node) -> None:
        self.cur.kids.append(node)
        self.count += 1
        if self.count > MAX_NODES:
            self.full = True

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if self.full:
            return
        data = {name: (value or "") for name, value in attrs}
        if tag in ("p", "li", "dt", "dd", "tr", "option") and self.cur.tag == tag:
            self._close(tag)
        elif tag in BLOCKS and tag not in ("li",) and self.cur.tag == "p":
            self._close("p")
        node = Node(tag, data, self.cur)
        self._add(node)
        if tag not in VOID and self.depth < MAX_DEPTH:
            self.cur, self.depth = node, self.depth + 1

    def handle_startendtag(self, tag: str, attrs: list) -> None:
        if self.full:
            return
        self._add(Node(tag, {name: (value or "") for name, value in attrs}, self.cur))

    def handle_endtag(self, tag: str) -> None:
        if tag in VOID:
            return
        node = self.cur
        steps = 0
        while node is not self.root and steps < 12:
            if node.tag == tag:
                self._close(tag)
                return
            node, steps = node.parent, steps + 1          # a stray end tag with no match is ignored

    def _close(self, tag: str) -> None:
        while self.cur is not self.root:
            done = self.cur.tag
            self.cur, self.depth = self.cur.parent, max(0, self.depth - 1)
            if done == tag:
                return

    def handle_data(self, data: str) -> None:
        if not self.full and data:
            self._add(Node("#text", parent=self.cur, text=data))


def parse(page: str) -> Node:
    tree = _Tree()
    try:
        tree.feed(page)
        tree.close()
    except Exception:  # a damaged page is read as far as it goes
        pass
    return tree.root


# ── Measuring ───────────────────────────────────────────────────────────────

def walk(node: Node):
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        stack.extend(reversed(current.kids))


def text_of(node: Node) -> str:
    return "".join(n.text for n in walk(node) if n.tag == "#text")


def _hidden(node: Node) -> bool:
    a = node.attrs
    style = a.get("style", "").replace(" ", "").lower()
    return ("hidden" in a or a.get("aria-hidden") == "true" or "display:none" in style or "visibility:hidden" in style)


def _tokens(node: Node) -> str:
    return f"{node.attrs.get('class', '')} {node.attrs.get('id', '')}"


def _junk(node: Node) -> bool:
    if node.tag in DROP or _hidden(node):
        return True
    tokens = _tokens(node)
    return bool(tokens.strip()) and bool(NEGATIVE.search(tokens)) and not STRONG_POSITIVE.search(tokens)


def link_density(node: Node) -> float:
    total = linked = 0
    for n in walk(node):
        if n.tag == "#text":
            size = len(n.text.strip())
            total += size
            parent = n.parent
            while parent is not None and parent is not node.parent:
                if parent.tag == "a":
                    linked += size
                    break
                parent = parent.parent
    return linked / total if total else 0.0


# ── Choosing the article ────────────────────────────────────────────────────

def _score_nodes(root: Node) -> dict[int, tuple[Node, float]]:
    scores: dict[int, tuple[Node, float]] = {}

    def bump(node: Node | None, amount: float) -> None:
        if node is None or node.tag in ("#root", "html"):
            return
        entry = scores.get(id(node))
        if entry is None:
            base = 0.0
            tokens = _tokens(node)
            if STRONG_POSITIVE.search(tokens) or node.attrs.get("itemprop") == "articleBody":
                base += 60
            elif POSITIVE.search(tokens):
                base += 20
            if node.tag == "article":
                base += 30
            if NEGATIVE.search(tokens):
                base -= 40
            entry = (node, base)
        scores[id(node)] = (entry[0], entry[1] + amount)

    for node in walk(root):
        if node.tag not in ("p", "pre", "blockquote", "td", "li") or _junk(node):
            continue
        # skip anything inside a junk ancestor
        parent, dead = node.parent, False
        while parent is not None:
            if _junk(parent):
                dead = True
                break
            parent = parent.parent
        if dead:
            continue
        text = text_of(node).strip()
        if len(text) < 25:
            continue
        points = 1 + text.count(",") + text.count(".") * 0.5 + min(len(text) / 100, 3)
        if node.tag == "li":
            points *= 0.4
        bump(node.parent, points)
        if node.parent is not None:
            bump(node.parent.parent, points / 2)
    return scores


def find_article(root: Node) -> Node | None:
    scores = _score_nodes(root)
    best, best_score = None, 0.0
    for node, score in scores.values():
        if node.tag not in ("div", "section", "article", "main", "td", "body"):
            continue
        adjusted = score * (1 - min(0.95, link_density(node)))
        if adjusted > best_score:
            best, best_score = node, adjusted
    if best is None or best.parent is None:
        return best
    return _with_siblings(best, best_score, scores)


def _with_siblings(best: Node, best_score: float, scores: dict[int, tuple[Node, float]]) -> Node:
    """Many sites cut the article into several blocks side by side (a paragraph group, a picture, another group).
    The best block alone is then only the first part, so the whole run of its siblings is taken: those that
    look like it (same tag and class) or score well themselves, and whatever sits between them."""
    parent = best.parent
    same = best.attrs.get("class", "").strip()

    def qualifies(kid: Node) -> bool:
        if kid is best:
            return True
        if _junk(kid):
            return False
        if same and kid.tag == best.tag and kid.attrs.get("class", "").strip() == same:
            return True
        entry = scores.get(id(kid))
        return entry is not None and entry[1] >= best_score * 0.25

    chosen = [index for index, kid in enumerate(parent.kids) if qualifies(kid)]
    if len(chosen) < 2:
        return best
    merged = Node("div", parent=parent)
    merged.kids = parent.kids[min(chosen):max(chosen) + 1]
    return merged


# ── Writing it out ──────────────────────────────────────────────────────────

def _pick_src(img: Node, base: str) -> str:
    a = img.attrs
    candidates = [a.get("data-src", ""), a.get("data-lazy-src", ""), a.get("data-original", "")]
    srcset = a.get("srcset") or a.get("data-srcset") or ""
    if srcset:
        best, best_w = "", -1
        for part in srcset.split(","):
            bits = part.strip().split()
            if not bits:
                continue
            width = 0
            if len(bits) > 1 and bits[1].endswith("w") and bits[1][:-1].isdigit():
                width = int(bits[1][:-1])
            if width > best_w:
                best, best_w = bits[0], width
        candidates.append(best)
    candidates.append(a.get("src", ""))
    for src in candidates:
        if src and not src.startswith("data:"):
            full = urljoin(base, src)
            if urlparse(full).scheme in ("http", "https"):
                return full
    return ""


def serialize(article: Node, base: str) -> str:
    out: list[str] = []

    def emit(node: Node) -> None:
        tag = node.tag
        if tag == "#text":
            out.append(html.escape(node.text, quote=False))
            return
        if _junk(node):
            return
        if tag == "img":
            width = node.attrs.get("width", "")
            if width.isdigit() and int(width) < 40:
                return
            src = _pick_src(node, base)
            if src:
                out.append(f'<img src="{html.escape(src, quote=True)}" alt="{html.escape(node.attrs.get("alt", ""), quote=True)}">')
            return
        if tag == "picture":
            for kid in node.kids:
                if kid.tag == "img":
                    emit(kid)
                    return
            return
        if tag in ("ul", "ol", "table", "div", "section") and node.kids:
            text = text_of(node).strip()
            if text and link_density(node) > 0.65 and len(text) < 700:
                return                                  # a list of links: related stories, a menu
        if tag == "a":
            href = urljoin(base, node.attrs.get("href", ""))
            if urlparse(href).scheme in ("http", "https", "mailto") and node.kids:
                out.append(f'<a href="{html.escape(href, quote=True)}">')
                for kid in node.kids:
                    emit(kid)
                out.append("</a>")
            else:
                for kid in node.kids:
                    emit(kid)
            return
        if tag in KEEP_INLINE and tag != "br":
            name = KEEP_INLINE[tag]
            out.append(f"<{name}>")
            for kid in node.kids:
                emit(kid)
            out.append(f"</{name}>")
            return
        if tag == "br":
            out.append("<br>")
            return
        if tag == "hr":
            out.append("<hr>")
            return
        if tag in KEEP_BLOCK:
            out.append(f"<{tag}>")
            for kid in node.kids:
                emit(kid)
            out.append(f"</{tag}>")
            return
        if tag in PASS_BLOCK:
            out.append(f"<{tag}>")
            for kid in node.kids:
                emit(kid)
            out.append(f"</{tag}>")
            return
        for kid in node.kids:                           # span, font and the like: just their contents
            emit(kid)

    emit(article)
    return "".join(out)


def words(markup: str) -> int:
    return len(re.sub(r"<[^>]+>", " ", html.unescape(markup)).split())


def extract(page: str, base: str) -> str | None:
    """The article's HTML, or None when the page has no article-sized run of text (a paywall, an app shell)."""
    root = parse(page)
    article = find_article(root)
    if article is None:
        return None
    cleaned = serialize(article, base)
    return cleaned if words(cleaned) >= MIN_WORDS else None


def page_title(page: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", page[:200_000], re.I | re.S)
    return re.sub(r"\s+", " ", html.unescape(match.group(1))).strip() if match else ""


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text)).lower()).strip()


def compose(feed_body: str, extracted: str, host: str) -> str | None:
    """What to show once the page has been read.

    Where the page is the post the feed was excerpting, it replaces the excerpt. Where it is a different
    page (a link post: the feed's text is the author's note, the page is what they linked to), the note
    stays and the page follows under a heading. None when the page adds nothing."""
    feed_words, page_words = words(feed_body), words(extracted)
    if page_words <= feed_words * 1.25 and feed_words >= 30:
        return None
    if feed_words < 30:
        return extracted
    probe = " ".join(_norm(feed_body).split()[:8])
    if probe and probe in _norm(extracted):
        return extracted
    return f"{feed_body}<hr><h3>From {html.escape(host)}</h3>{extracted}"


def wants_full(feed_body: str) -> bool:
    """Whether a feed's own text looks like a teaser, so the page is worth fetching."""
    count = words(feed_body)
    if count >= 160:
        return False
    if count < 8 and "<img" in feed_body.lower():
        return False            # a picture post (a comic, a photo): the picture is the post
    return True
