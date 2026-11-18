# SPDX-License-Identifier: Apache-2.0
"""Reeds' library: feeds and their articles in one small SQLite file in the app's data folder."""

from __future__ import annotations

import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from reeds_feeds import Feed

KEEP_PER_FEED = 400          # newest articles kept per feed; starred and saved ones are never trimmed

SCHEMA = """
create table if not exists feeds (
    id integer primary key,
    url text not null unique,
    title text not null default '',
    site_url text not null default '',
    folder text not null default '',
    etag text not null default '',
    modified text not null default '',
    checked real not null default 0,
    error text not null default ''
);
create table if not exists entries (
    id integer primary key,
    feed_id integer not null references feeds(id) on delete cascade,
    guid text not null,
    title text not null,
    link text not null default '',
    author text not null default '',
    published real not null default 0,
    added real not null default 0,
    summary text not null default '',
    content text not null default '',
    image text not null default '',
    read integer not null default 0,
    starred integer not null default 0,
    later integer not null default 0,
    unique (feed_id, guid)
);
create index if not exists entries_feed on entries (feed_id, published desc);
create table if not exists settings (key text primary key, value text not null);
"""


@dataclass
class FeedRow:
    id: int
    url: str
    title: str
    site_url: str
    folder: str
    checked: float
    error: str
    unread: int = 0


@dataclass
class EntryRow:
    id: int
    feed_id: int
    feed_title: str
    title: str
    link: str
    author: str
    published: float
    summary: str
    content: str
    image: str
    read: bool
    starred: bool
    later: bool

    @property
    def when(self) -> float:
        return self.published


def data_path() -> Path:
    override = os.environ.get("REEDS_DATA")
    if override:
        return Path(override)
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "io.github.cappedcat1710.Reeds" / "library.db"


class Library:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or data_path()
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.path))
        self.db.row_factory = sqlite3.Row
        self.db.execute("pragma foreign_keys = on")
        self.db.executescript(SCHEMA)
        self.db.commit()

    # ── Settings ────────────────────────────────────────────────────────────

    def setting(self, key: str, default: str = "") -> str:
        row = self.db.execute("select value from settings where key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        self.db.execute("insert into settings (key, value) values (?, ?) on conflict(key) do update set value = excluded.value",
                        (key, value))
        self.db.commit()

    # ── Feeds ───────────────────────────────────────────────────────────────

    def feeds(self) -> list[FeedRow]:
        rows = self.db.execute(
            "select f.*, (select count(*) from entries e where e.feed_id = f.id and e.read = 0) as unread "
            "from feeds f order by lower(f.folder), lower(f.title)").fetchall()
        return [FeedRow(r["id"], r["url"], r["title"], r["site_url"], r["folder"], r["checked"], r["error"], r["unread"])
                for r in rows]

    def feed(self, feed_id: int) -> FeedRow | None:
        return next((f for f in self.feeds() if f.id == feed_id), None)

    def feed_by_url(self, url: str) -> FeedRow | None:
        return next((f for f in self.feeds() if f.url == url), None)

    def add_feed(self, url: str, title: str = "", folder: str = "", site_url: str = "") -> tuple[int, bool]:
        """(id, created). An address already in the library is not added twice."""
        row = self.db.execute("select id from feeds where url = ?", (url,)).fetchone()
        if row:
            return row["id"], False
        cursor = self.db.execute("insert into feeds (url, title, folder, site_url) values (?, ?, ?, ?)",
                                 (url, title, folder, site_url))
        self.db.commit()
        return int(cursor.lastrowid or 0), True

    def rename_feed(self, feed_id: int, title: str) -> None:
        self.db.execute("update feeds set title = ? where id = ?", (title, feed_id))
        self.db.commit()

    def move_feed(self, feed_id: int, folder: str) -> None:
        self.db.execute("update feeds set folder = ? where id = ?", (folder.strip(), feed_id))
        self.db.commit()

    def remove_feed(self, feed_id: int) -> None:
        self.db.execute("delete from feeds where id = ?", (feed_id,))
        self.db.commit()

    def folders(self) -> list[str]:
        return [r["folder"] for r in self.db.execute(
            "select distinct folder from feeds where folder != '' order by lower(folder)")]

    def store(self, feed_id: int, feed: Feed) -> int:
        """Keep what a fetch found. Returns how many articles were new."""
        now = time.time()
        if feed.not_modified:
            self.db.execute("update feeds set checked = ?, error = '' where id = ?", (now, feed_id))
            self.db.commit()
            return 0
        current = self.db.execute("select title, site_url from feeds where id = ?", (feed_id,)).fetchone()
        self.db.execute(
            "update feeds set title = ?, site_url = ?, etag = ?, modified = ?, checked = ?, error = '' where id = ?",
            (current["title"] or feed.title or feed.url, feed.site_url or current["site_url"], feed.etag, feed.modified,
             now, feed_id))
        new = 0
        for item in feed.items:
            cursor = self.db.execute(
                "insert or ignore into entries (feed_id, guid, title, link, author, published, added, summary, content, image) "
                "values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (feed_id, item.guid, item.title, item.link, item.author, item.published or now, now,
                 item.summary, item.content, item.image))
            new += cursor.rowcount
        self.db.execute(
            "delete from entries where feed_id = ? and starred = 0 and later = 0 and id not in "
            "(select id from entries where feed_id = ? order by published desc limit ?)",
            (feed_id, feed_id, KEEP_PER_FEED))
        self.db.commit()
        return new

    def mark_error(self, feed_id: int, message: str) -> None:
        self.db.execute("update feeds set error = ?, checked = ? where id = ?", (message, time.time(), feed_id))
        self.db.commit()

    def validators(self, feed_id: int) -> tuple[str, str]:
        row = self.db.execute("select etag, modified from feeds where id = ?", (feed_id,)).fetchone()
        return (row["etag"], row["modified"]) if row else ("", "")

    # ── Articles ────────────────────────────────────────────────────────────

    _ENTRY = ("select e.*, f.title as feed_title from entries e join feeds f on f.id = e.feed_id ")

    def _entry(self, r: sqlite3.Row) -> EntryRow:
        return EntryRow(r["id"], r["feed_id"], r["feed_title"], r["title"], r["link"], r["author"], r["published"],
                        r["summary"], r["content"], r["image"], bool(r["read"]), bool(r["starred"]), bool(r["later"]))

    def entries(self, place: str, *, unread_only: bool = False, query: str = "", limit: int = 500,
                keep: set[int] | frozenset[int] = frozenset()) -> list[EntryRow]:
        """`place` is "all", "later", "starred", "feed:<id>" or "folder:<name>"."""
        where, args = [], []
        if place == "later":
            where.append("e.later = 1")
        elif place == "starred":
            where.append("e.starred = 1")
        elif place.startswith("feed:"):
            where.append("e.feed_id = ?")
            args.append(int(place[5:]))
        elif place.startswith("folder:"):
            where.append("f.folder = ?")
            args.append(place[7:])
        if unread_only and place not in ("later", "starred"):
            # Articles opened in this session stay put, so the list doesn't shift under the reader.
            held = ",".join(str(int(i)) for i in keep)
            where.append(f"(e.read = 0 or e.id in ({held}))" if held else "e.read = 0")
        if query.strip():
            like = "%" + query.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            where.append("(e.title like ? escape '\\' or e.summary like ? escape '\\' or e.content like ? escape '\\' "
                         "or e.author like ? escape '\\' or f.title like ? escape '\\')")
            args += [like] * 5
        sql = self._ENTRY + (" where " + " and ".join(where) if where else "") + " order by e.published desc, e.id desc limit ?"
        return [self._entry(r) for r in self.db.execute(sql, (*args, limit)).fetchall()]

    def entry(self, entry_id: int) -> EntryRow | None:
        row = self.db.execute(self._ENTRY + "where e.id = ?", (entry_id,)).fetchone()
        return self._entry(row) if row else None

    def set_flag(self, entry_id: int, flag: str, value: bool) -> None:
        if flag not in ("read", "starred", "later"):
            raise ValueError(flag)
        self.db.execute(f"update entries set {flag} = ? where id = ?", (int(value), entry_id))
        self.db.commit()

    def mark_all_read(self, place: str) -> list[int]:
        """Marks what `place` holds as read, and returns the ids it changed so it can be undone."""
        ids = [e.id for e in self.entries(place, unread_only=True, limit=100000)]
        if ids:
            self.db.executemany("update entries set read = 1 where id = ?", [(i,) for i in ids])
            self.db.commit()
        return ids

    def mark_unread(self, ids: list[int]) -> None:
        self.db.executemany("update entries set read = 0 where id = ?", [(i,) for i in ids])
        self.db.commit()

    def counts(self) -> dict[str, int]:
        one = lambda sql: self.db.execute(sql).fetchone()[0]  # noqa: E731
        return {"unread": one("select count(*) from entries where read = 0"),
                "later": one("select count(*) from entries where later = 1"),
                "starred": one("select count(*) from entries where starred = 1")}

    def close(self) -> None:
        self.db.close()
