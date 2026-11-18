#!/usr/bin/python3
# SPDX-License-Identifier: Apache-2.0
"""Reeds: a feed reader for Luma.

The window is places and content: a sidebar of places and feeds, a list of articles and the
article itself, as List and page (`ListFirst`) so a phone gets the list first and the page
pushed over it. Every visible part is a LumaUI part; what is drawn here is the article's own
text and pictures.

    window     AppWindow, its body the sidebar beside a ListFirst
    sidebar    NavigationSidebar (All articles, Read later, Starred, then feeds by folder),
               SidebarFoot: search, Unread / All, Add feed
    list       NavigationSidebar of SidebarRow, an unread dot on what hasn't been read
    page       Island: the article, a CornerPill (star, read later, open) on a computer
    bar        ActionCenter: Previous / Next and what you do with this article; Refresh and
               Mark all read when nothing is open; a place picker and search on a phone
"""

from __future__ import annotations

import os
import re
import sys
import time
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk, Pango  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))

from luma_appkit import (  # noqa: E402
    ActionCenter, AppWindow, BarAction, BarEntry, Command, CommandGroup, CommandRegistry, DestructiveDialog,
    EmptyState, FileRequest, Inset, Island, ListEmptyState, ListFirst, NavigationSidebar, PanelRow,
    RowLead, ScrollView, SidebarFoot, SidebarRow, SidebarToggle, TextButton, Toast, ToastHost,
    CornerPill, add_style_sheet, apply_type, ask_for_file, attach_context_menu, lumaui_icon, panel_list,
)

import reeds_feeds as feeds_lib  # noqa: E402
from reeds_feeds import FeedError  # noqa: E402
from reeds_store import EntryRow, FeedRow, Library  # noqa: E402

APP_ID = "io.github.cappedcat1710.Reeds"
REFRESH_EVERY = 30 * 60          # seconds between automatic refreshes while the window is open
STALE_AFTER = 15 * 60            # a feed checked more recently than this is skipped on launch
LIST_WIDTH = 340
LIST_WIDTH_NARROW = 296
READING_WIDTH = 680
MAX_IMAGES = 12

# What "Add suggested feeds" adds: a few reliable, well-known feeds, so the first launch isn't an empty page.
SUGGESTED = (
    ("Luma releases", "https://github.com/SimplyLuma/luma/releases.atom", "Luma"),
    ("Hacker News", "https://news.ycombinator.com/rss", "Tech"),
    ("Ars Technica", "https://feeds.arstechnica.com/arstechnica/index", "Tech"),
    ("NASA", "https://www.nasa.gov/feed/", "Science"),
    ("Quanta Magazine", "https://www.quantamagazine.org/feed/", "Science"),
    ("xkcd", "https://xkcd.com/atom.xml", "Fun"),
)

LIGHT_PLACES = (
    ("all", "All articles", "inbox"),
    ("later", "Read later", "bookmark"),
    ("starred", "Starred", "star"),
)


def style_path() -> str:
    here = Path(__file__).resolve().parent / "reeds.css"
    return str(here if here.exists() else Path("/app/share/io.github.cappedcat1710.Reeds/reeds.css"))


def valid_markup(markup: str) -> bool:
    """Whether a label can show this markup. <a> is GTK's own extension, so Pango's parser is shown the rest."""
    try:
        Pango.parse_markup(re.sub(r"</?a\b[^>]*>", "", markup), -1, "\0")
        return True
    except GLib.Error:
        return False


# ── The window ──────────────────────────────────────────────────────────────


class ReedsWindow(AppWindow):
    def __init__(self, application: Adw.Application, library: Library) -> None:
        self.lib = library
        self.place = "all"
        self.unread_only = self.lib.setting("unread_only", "1") == "1"
        self.load_images = self.lib.setting("images", "1") == "1"
        self.query = ""
        self.selected: EntryRow | None = None
        self.keep: set[int] = set()                 # opened this session: they stay in an unread list
        self.shown: list[int] = []                  # entry ids in list order
        self.row_of: dict[int, SidebarRow] = {}
        self.place_rows: dict[str, SidebarRow] = {}
        self.pool = ThreadPoolExecutor(max_workers=4)
        self.refreshing = False
        self._progress: Toast | None = None
        self._pending = 0
        self._new = 0
        self._failed = 0
        self._drawn_tier = "regular"
        self._search_open = False
        self._busy_toast: Toast | None = None
        self.closed = False
        self._focus_list_after_refresh = False
        self.last_open: int | None = None           # the article most recently read: Back returns to its row
        self.article_scroll: ScrollView | None = None
        super().__init__(
            application=application, app_id=APP_ID, title="Reeds", icon_name=APP_ID,
            commands=self._application_commands(),
            default_width=1180, default_height=760, minimum_width=360, minimum_height=420,
        )
        add_style_sheet(style_path())

        sidebar = self._build_sidebar()
        article_list = self._build_list()
        page = self._build_page()
        self.list_first = ListFirst(article_list, page, title="Reeds", on_back=self._back)
        body = Gtk.Box(hexpand=True, vexpand=True)
        body.append(sidebar)
        body.append(self.list_first)
        self.set_body(body)
        self.sidebar_toggle = SidebarToggle(self.sidebar, drawer_below=901)
        self.set_leading(self.sidebar_toggle)
        self._add_breakpoints()
        self.tier_watch.connect("tier-changed", lambda _w, _t: self._tier_check())
        self.connect("close-request", self._closing)
        self._drawn_tier = self.tier

        self._render_all()
        self.list_first.show_list() if self.phone else None
        GLib.idle_add(self._first_refresh)
        GLib.timeout_add(250, self._initial_focus)
        GLib.timeout_add_seconds(REFRESH_EVERY, self._timed_refresh)

    # ── Tiers ───────────────────────────────────────────────────────────────

    @property
    def phone(self) -> bool:
        return self._drawn_tier == "phone"

    def _add_breakpoints(self) -> None:
        narrow = Adw.Breakpoint.new(Adw.BreakpointCondition.parse("max-width: 899px"))
        narrow.add_setter(self.list_host, "width-request", LIST_WIDTH_NARROW)
        self.add_breakpoint(narrow)
        phone = Adw.Breakpoint.new(Adw.BreakpointCondition.parse("max-width: 559px"))
        phone.add_setter(self.list_host, "width-request", -1)
        self.add_breakpoint(phone)
        self.set_phone_bleed(False)

    def _tier_check(self) -> None:
        tier = self.tier
        if tier == self._drawn_tier:
            return
        self._drawn_tier = tier
        self._search_open = False
        self._render_chrome()
        if self.selected is not None:
            self._show_article(self.selected)
        if self.phone:
            self.list_first.show_detail() if self.selected else self.list_first.show_list()

    # ── Commands: the app menu, shortcuts and context menus all run these ───

    def _application_commands(self) -> CommandRegistry:
        has_article = lambda: self.selected is not None  # noqa: E731
        return CommandRegistry((
            CommandGroup("", (
                Command("reeds.add", "Add feed", self.add_feed, "square-pen", shortcut=("Ctrl", "N")),
                Command("reeds.suggested", "Add suggested feeds", self.add_suggested, "sparkles"),
                Command("reeds.refresh", "Refresh feeds", self.refresh, "refresh-cw", shortcut=("Ctrl", "R")),
                Command("reeds.find", "Search articles", self._focus_search, "search", shortcut=("Ctrl", "F")),
                Command("reeds.read-all", "Mark all as read", self.mark_all_read, "check-check",
                        shortcut=("Ctrl", "Shift", "A")),
                Command("reeds.sidebar", "Show or hide sidebar", lambda: self.sidebar_toggle.toggle(), "panel-left",
                        shortcut=("F9",)),
            )),
            CommandGroup("", (
                Command("reeds.go-all", "Go to All articles", lambda: self.go_to("all"), "inbox", shortcut=("Ctrl", "1")),
                Command("reeds.go-later", "Go to Read later", lambda: self.go_to("later"), "bookmark", shortcut=("Ctrl", "2")),
                Command("reeds.go-starred", "Go to Starred", lambda: self.go_to("starred"), "star", shortcut=("Ctrl", "3")),
                Command("reeds.next-pane", "Next pane", lambda: self.cycle_pane(1), "arrow-right", shortcut=("F6",)),
                Command("reeds.previous-pane", "Previous pane", lambda: self.cycle_pane(-1), "arrow-left",
                        shortcut=("Shift", "F6")),
            )),
            CommandGroup("", (
                Command("article.back", "Back to list", self.back_to_list, "corner-up-left", shortcut=("Alt", "Left"),
                        enabled=has_article),
                Command("article.next", "Next article", self.next_article, "arrow-down",
                        shortcut=("Alt", "Down"), enabled=has_article),
                Command("article.previous", "Previous article", self.previous_article, "arrow-up",
                        shortcut=("Alt", "Up"), enabled=has_article),
                Command("article.star", "Star article", self.toggle_star, "star", shortcut=("Ctrl", "D"),
                        enabled=has_article),
                Command("article.later", "Read later", self.toggle_later, "bookmark", shortcut=("Ctrl", "B"),
                        enabled=has_article),
                Command("article.unread", "Mark as unread", self.toggle_read, "eye-off", shortcut=("Ctrl", "U"),
                        enabled=has_article),
                Command("article.open", "Open in browser", self.open_original, "square-arrow-out-up-right",
                        shortcut=("Ctrl", "Shift", "O"), enabled=has_article),
            )),
            CommandGroup("", (
                Command("reeds.import", "Import feeds…", self.import_feeds, "download", shortcut=("Ctrl", "I")),
                Command("reeds.export", "Export feeds…", self.export_feeds, "upload", shortcut=("Ctrl", "E")),
            )),
            CommandGroup("", (
                Command("reeds.quit", "Quit Reeds", self.close, "log-out", shortcut=("Ctrl", "Q")),
            )),
        ))

    # ── Building the three panes ────────────────────────────────────────────

    def _build_sidebar(self) -> Gtk.Widget:
        self.sidebar = NavigationSidebar(variant="destinations")
        self.places = self.sidebar.list
        self.places.connect("row-activated", self._place_activated)
        self.foot = SidebarFoot(
            search="Search articles", on_search=self._search_changed,
            filters=(("unread", "Unread", "circle-dot"), ("all", "All", "inbox")),
            filter="unread" if self.unread_only else "all", on_filter=self._filter_changed,
            add=("Add feed", "square-pen", self.add_feed))
        self.sidebar.append_footer(self.foot)
        return self.sidebar

    def _build_list(self) -> Gtk.Widget:
        self.article_sidebar = NavigationSidebar(variant="resources")
        self.rows = self.article_sidebar.list
        self.rows.connect("row-activated", self._row_activated)
        self.list_empty = ListEmptyState("")
        self.fresh_list = EmptyState(
            "No feeds yet", "Start with a few suggestions, or add a website or feed address.",
            lumaui_icon("radio-tower"), primary=("Add suggested feeds", self.add_suggested),
            secondary=("Add feed", self.add_feed))
        self.list_stack = Gtk.Stack(vexpand=True, hexpand=True)
        self.list_stack.add_named(self.article_sidebar, "list")
        self.list_stack.add_named(self.fresh_list, "fresh")
        self.list_host = ToastHost(self.list_stack)
        self.list_host.set_size_request(LIST_WIDTH, -1)
        self.list_center = ActionCenter().attach(self.list_host)
        return self.list_host

    def _build_page(self) -> Gtk.Widget:
        island = Island()
        island.set_hexpand(True)
        self.corner_slot = Adw.Bin(halign=Gtk.Align.END, valign=Gtk.Align.START)
        self.article_holder = Adw.Bin(vexpand=True, hexpand=True)
        self.page_stack = Gtk.Stack(vexpand=True, hexpand=True)
        self.page_stack.add_named(self.article_holder, "article")
        self.page_stack.add_named(EmptyState(
            "Pick an article", "Choose one from the list to read it here.", lumaui_icon("book-open-text")), "pick")
        self.fresh_page = EmptyState(
            "Read what you follow", "Start with a few suggestions, or add a website or feed address. "
            "Reeds keeps what you’ve read on this device.",
            lumaui_icon("radio-tower"), primary=("Add suggested feeds", self.add_suggested),
            secondary=("Add feed", self.add_feed))
        self.page_stack.add_named(self.fresh_page, "fresh")
        overlay = Gtk.Overlay(child=self.page_stack)
        overlay.add_overlay(self.corner_slot)
        island.append(overlay)
        self.page_host = ToastHost(island)
        self.page_center = ActionCenter().attach(self.page_host)
        return self.page_host

    # ── Rendering ───────────────────────────────────────────────────────────

    def _render_all(self) -> None:
        self._render_sidebar()
        self._render_list()
        self._render_chrome()

    def _render_chrome(self) -> None:
        """What depends on the tier or the selection: the page, the corner and the bars."""
        has_feeds = bool(self.lib.feeds())
        self.list_stack.set_visible_child_name("fresh" if (self.phone and not has_feeds) else "list")
        if not has_feeds:
            self.page_stack.set_visible_child_name("fresh")
        elif self.selected is None:
            self.page_stack.set_visible_child_name("pick")
        else:
            self.page_stack.set_visible_child_name("article")
        self._render_corner()
        self._render_bars()

    def _place_title(self) -> str:
        names = {key: label for key, label, _ in LIGHT_PLACES}
        if self.place in names:
            return names[self.place]
        if self.place.startswith("feed:"):
            feed = self.lib.feed(int(self.place[5:]))
            return feed.title if feed else "Feed"
        if self.place.startswith("folder:"):
            return self.place[7:]
        return "Reeds"

    def _render_sidebar(self) -> None:
        focused = self._focus_key("place")
        self.sidebar.clear()
        self.place_rows = {}
        counts = self.lib.counts()
        for key, label, icon in LIGHT_PLACES:
            number = counts["unread"] if key == "all" else counts[key]
            row = SidebarRow(label, lead=RowLead.icon(icon), trail=number or None, attention=(key == "all" and number > 0))
            row.place = key
            self.sidebar.append_row(row)
            self.place_rows[key] = row
        feeds = self.lib.feeds()
        current_folder: str | None = None
        for feed in feeds:
            if feed.folder != current_folder or current_folder is None:
                current_folder = feed.folder
                if feed.folder:
                    self.sidebar.append_section(feed.folder)
                else:
                    self.sidebar.append_section("Feeds", action=("plus", "Add feed", self.add_feed))
            row = SidebarRow(feed.title or feed.url, lead=RowLead.icon("radio-tower"), trail=feed.unread or None,
                             muted=bool(feed.error), subtitle="Couldn’t refresh" if feed.error else "")
            row.place = f"feed:{feed.id}"
            self._feed_menu(row, feed)
            self.sidebar.append_row(row)
            self.place_rows[row.place] = row
        selected = self.place_rows.get(self.place)
        if selected is not None:
            self.places.select_row(selected)
        self._describe_places(counts, feeds)
        self._restore_focus(focused)

    def _describe_places(self, counts: dict, feeds: list) -> None:
        for key, word in (("all", "unread"), ("later", "saved"), ("starred", "starred")):
            row = self.place_rows.get(key)
            if row is not None:
                number = counts["unread"] if key == "all" else counts[key]
                self._describe(row, f"{number} {word}" if number else "None")
        for feed in feeds:
            row = self.place_rows.get(f"feed:{feed.id}")
            if row is not None:
                self._describe(row, ("Couldn’t refresh. " if feed.error else "") + (f"{feed.unread} unread" if feed.unread else "All read"))

    def _feed_commands(self, feed: FeedRow) -> CommandRegistry:
        return CommandRegistry((CommandGroup("", (
            Command("feed.rename", "Rename feed…", lambda: self.rename_feed(feed), "pen-line"),
            Command("feed.move", "Move to folder…", lambda: self.move_feed(feed), "folder"),
            Command("feed.refresh", "Refresh feed", lambda: self.refresh([feed]), "refresh-cw"),
            Command("feed.remove", "Unsubscribe", lambda: self.ask_unsubscribe(feed), "trash-2", destructive=True),
        )),))

    def _feed_menu(self, row: Gtk.Widget, feed: FeedRow) -> None:
        attach_context_menu(row, self._feed_commands(feed))

    def _render_list(self) -> None:
        focused = self._focus_key("entry")
        entries = self.lib.entries(self.place, unread_only=self.unread_only, query=self.query, keep=self.keep, limit=300)
        holder = self.list_empty.get_parent()
        if isinstance(holder, Gtk.ListBoxRow):
            holder.set_child(None)
        self.article_sidebar.clear()
        self.row_of = {}
        self.shown = [entry.id for entry in entries]
        for entry in entries:
            row = SidebarRow(entry.title, subtitle=entry.feed_title if not self.place.startswith("feed:") else
                             feeds_lib.snippet(entry.summary or entry.content, 90),
                             meta=feeds_lib.relative(entry.published), attention=not entry.read, muted=entry.read)
            row.entry_id = entry.id
            row.meta_text = f"{entry.feed_title}, {feeds_lib.relative(entry.published)}"
            self._describe(row, ("Read, " if entry.read else "Unread, ") + row.meta_text)
            self.article_sidebar.append_row(row)
            self.row_of[entry.id] = row
        if not entries:
            self.list_empty.set_label(self._empty_text())
            self.rows.append(Gtk.ListBoxRow(selectable=False, activatable=False, child=self.list_empty))
        if self.selected is not None and self.selected.id in self.row_of:
            self.rows.select_row(self.row_of[self.selected.id])
        self._restore_focus(focused)

    def _empty_text(self) -> str:
        if self.query.strip():
            return f"No articles match “{self.query.strip()}”."
        if not self.lib.feeds():
            return "No feeds yet."
        if self.place == "later":
            return "Nothing saved for later.\nUse Read later on an article to keep it here."
        if self.place == "starred":
            return "No starred articles."
        if self.unread_only:
            return "You’re all caught up.\nSwitch to All to see what you’ve read."
        return "No articles yet.\nRefresh to check for new ones."

    # ── Choosing places and articles ────────────────────────────────────────

    # ── Keyboard: panes, and keeping focus where the person put it ──────────

    def _pane_of(self, widget: Gtk.Widget | None) -> str | None:
        if widget is None:
            return None
        if widget is self.sidebar or widget.is_ancestor(self.sidebar):
            return "sidebar"
        if widget is self.list_host or widget.is_ancestor(self.list_host):
            return "list"
        if widget is self.page_host or widget.is_ancestor(self.page_host):
            return "article"
        return None

    def _pane_ready(self, pane: str) -> bool:
        if pane == "sidebar":
            return self.sidebar.get_mapped() and bool(self.place_rows)
        if pane == "list":
            return bool(self.row_of) and (not self.phone or self.list_first.showing == "list")
        if pane == "article":
            return self.selected is not None and self.article_scroll is not None and (
                not self.phone or self.list_first.showing == "detail")
        return False

    def focus_pane(self, pane: str) -> bool:
        if not self._pane_ready(pane):
            return False
        if pane == "sidebar":
            row = self.place_rows.get(self.place) or next(iter(self.place_rows.values()))
            return row.grab_focus()
        if pane == "list":
            wanted = self.selected.id if self.selected else self.last_open
            row = self.row_of.get(wanted) if wanted is not None else None
            return (row or next(iter(self.row_of.values()))).grab_focus()
        return self.article_scroll.grab_focus()

    def cycle_pane(self, step: int) -> None:
        order = [pane for pane in ("sidebar", "list", "article") if self._pane_ready(pane)]
        if not order:
            return
        current = self._pane_of(self.get_focus())
        if current in order:
            start = order.index(current)
        else:   # the page's bar with nothing open: it sits after the list
            start = len(order) - 1 if current == "article" else (-1 if step > 0 else 0)
        self.focus_pane(order[(start + step) % len(order)])

    def go_to(self, place: str) -> None:
        """A shortcut to a place: the list is what you want next."""
        self.go(place)
        self.focus_pane("list") or self.focus_pane("sidebar")

    def back_to_list(self) -> None:
        if self.phone:
            self._back()
            self.list_first.show_list()
            GLib.idle_add(lambda: (self.focus_pane("list"), False)[1])
        else:
            self.focus_pane("list")

    def _focus_key(self, kind: str) -> tuple[str, object] | None:
        """Which row of the sidebar ("place") or the list ("entry") has focus, so a redraw can give it back."""
        row = self.get_focus()
        while row is not None and not isinstance(row, Gtk.ListBoxRow):
            row = row.get_parent()
        if row is None:
            return None
        if kind == "place" and getattr(row, "place", None) and row.is_ancestor(self.sidebar):
            return ("place", row.place)
        if kind == "entry" and getattr(row, "entry_id", None) is not None:
            return ("entry", row.entry_id)
        return None

    def _restore_focus(self, key: tuple[str, object] | None) -> None:
        if key is None:
            return
        rows = self.place_rows if key[0] == "place" else self.row_of
        row = rows.get(key[1]) or next(iter(rows.values()), None)
        if row is not None:
            row.grab_focus()

    @staticmethod
    def _describe(row: Gtk.Widget, text: str) -> None:
        """What a screen reader says after the row's title: its state, not just its look."""
        row.update_property([Gtk.AccessibleProperty.DESCRIPTION], [text])

    def go(self, place: str) -> None:
        if place != self.place:
            self.place = place
            self.keep = set()
            self.selected = None
        self._render_sidebar()
        self._render_list()
        self._render_chrome()
        if self.phone:
            self.list_first.show_list()

    def _place_activated(self, _rows: Gtk.ListBox, row: Gtk.ListBoxRow) -> None:
        place = getattr(row, "place", None)
        if place:
            self.go(place)

    def _row_activated(self, _rows: Gtk.ListBox, row: Gtk.ListBoxRow) -> None:
        entry_id = getattr(row, "entry_id", None)
        if entry_id is not None:
            self.open_entry(entry_id)

    def open_entry(self, entry_id: int) -> None:
        entry = self.lib.entry(entry_id)
        if entry is None:
            return
        if not entry.read:
            self.lib.set_flag(entry_id, "read", True)
            entry.read = True
        self.keep.add(entry_id)
        self.selected = entry
        self._row_read(entry_id, True)
        row = self.row_of.get(entry_id)
        if row is not None:
            self.rows.select_row(row)
        self.last_open = entry_id
        self._update_counts()
        self._show_article(entry, focus=True)
        self.list_first.show_detail()
        self._render_chrome()

    def _row_read(self, entry_id: int, read: bool) -> None:
        row = self.row_of.get(entry_id)
        if row is not None:
            row.set_attention(not read)
            self._describe(row, ("Read, " if read else "Unread, ") + getattr(row, "meta_text", ""))

    def _update_counts(self) -> None:
        """Counts beside the places change as things are read, without redrawing the list."""
        counts = self.lib.counts()
        self._describe_places(counts, self.lib.feeds())
        row = self.place_rows.get("all")
        if row is not None:
            row.set_trail(counts["unread"] or None)
            row.set_attention(counts["unread"] > 0)
        for key in ("later", "starred"):
            if key in self.place_rows:
                self.place_rows[key].set_trail(counts[key] or None)
        for feed in self.lib.feeds():
            row = self.place_rows.get(f"feed:{feed.id}")
            if row is not None:
                row.set_trail(feed.unread or None)

    def _back(self) -> None:
        self.selected = None
        self.article_scroll = None
        self.rows.unselect_all()
        self._render_chrome()

    def _step(self, direction: int) -> None:
        if self.selected is None or self.selected.id not in self.shown:
            return
        index = self.shown.index(self.selected.id) + direction
        if 0 <= index < len(self.shown):
            self.open_entry(self.shown[index])
        else:
            Toast.show(self._toast_host(), "No more articles here", kind="done")

    def next_article(self) -> None:
        self._step(1)

    def previous_article(self) -> None:
        self._step(-1)

    # ── The article page ────────────────────────────────────────────────────

    def _label(self, markup: str, role: str = "body", *, muted: bool = False, css: str = "reeds-body") -> Gtk.Label:
        label = Gtk.Label(wrap=True, xalign=0, selectable=True, hexpand=True)
        # Text can be selected with the mouse, but only a paragraph with a link is a tab stop:
        # Tab should reach the buttons, not stop at every paragraph.
        label.set_focusable("<a " in markup)
        label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        if markup and valid_markup(markup):
            label.set_markup(markup)
        else:
            label.set_text(feeds_lib._plain(markup))
        apply_type(label, role, muted=muted)
        label.add_css_class(css)
        label.connect("activate-link", self._link)
        return label

    def _link(self, _label: Gtk.Label, uri: str) -> bool:
        self._launch(uri)
        return True

    def _launch(self, uri: str) -> None:
        try:
            Gtk.UriLauncher.new(uri).launch(self, None, lambda launcher, result: self._launched(launcher, result))
        except Exception:
            Toast.show(self._toast_host(), "Couldn’t open that address", kind="error")

    def _launched(self, launcher: Gtk.UriLauncher, result: Gio.AsyncResult) -> None:
        try:
            launcher.launch_finish(result)
        except GLib.Error as error:
            if not error.matches(Gtk.dialog_error_quark(), Gtk.DialogError.DISMISSED):
                Toast.show(self._toast_host(), "Couldn’t open that address", kind="error")

    def _show_article(self, entry: EntryRow, *, focus: bool = False) -> None:
        column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14, margin_top=78 if self.phone else 34, margin_bottom=140,
                         margin_start=20 if self.phone else 28, margin_end=20 if self.phone else 28)
        column.add_css_class("reeds-article")
        source = self._label(GLib.markup_escape_text(entry.feed_title), "label", muted=True, css="reeds-source")
        column.append(source)
        title = self._label(GLib.markup_escape_text(entry.title), "title-1", css="reeds-title")
        column.append(title)
        body_html = entry.content or entry.summary
        parts = [part for part in (
            entry.author,
            time.strftime("%-d %B %Y", time.localtime(entry.published)) if entry.published else "",
            f"{feeds_lib.reading_minutes(body_html)} min read" if feeds_lib.reading_minutes(body_html) else "") if part]
        if parts:
            column.append(self._label(GLib.markup_escape_text(" · ".join(parts)), "caption", muted=True, css="reeds-meta"))

        blocks = feeds_lib.article_blocks(body_html, entry.link)
        pictures: list[tuple[Gtk.Picture, str]] = []
        has_image = any(block.kind == "img" for block in blocks)
        if entry.image and not has_image and self.load_images:
            picture = self._picture("")
            column.append(picture)
            pictures.append((picture, entry.image))
        used = 0
        for block in blocks:
            widget = self._block(block, pictures)
            if widget is not None:
                column.append(widget)
        if not blocks:
            column.append(self._label("There’s no text in this article. Open it in your browser to read it.", muted=True))
        if entry.link:
            original = TextButton("Open original", icon="square-arrow-out-up-right", style="fill",
                                  on_click=self.open_original)
            original.set_halign(Gtk.Align.START)
            column.append(original)
        clamp = Adw.Clamp(maximum_size=READING_WIDTH, tightening_threshold=READING_WIDTH, child=column)
        scroll = ScrollView(clamp)
        scroll.set_focusable(True)
        # Paragraphs aren't focusable, so Ctrl+C is handled here, for the text selected with the mouse.
        copy = Gtk.ShortcutController()
        copy.set_scope(Gtk.ShortcutScope.LOCAL)
        copy.add_shortcut(Gtk.Shortcut.new(Gtk.ShortcutTrigger.parse_string("<Control>c"),
                                           Gtk.CallbackAction.new(lambda *_: self._copy_selection())))
        scroll.add_controller(copy)
        scroll.update_property([Gtk.AccessibleProperty.LABEL], [f"{entry.title}, from {entry.feed_title}"])
        self.article_scroll = scroll
        self.article_holder.set_child(scroll)
        if focus:
            GLib.idle_add(lambda: (self.focus_pane("article"), False)[1])
        for picture, url in pictures[:MAX_IMAGES]:
            self._load_picture(picture, url, entry.id)

    def _copy_selection(self) -> bool:
        """Copies the text selected in the article. Returns False when nothing is selected."""
        found: list[str] = []

        def walk(widget: Gtk.Widget) -> None:
            child = widget.get_first_child()
            while child is not None:
                if isinstance(child, Gtk.Label) and child.get_selectable():
                    has, start, end = child.get_selection_bounds()
                    if has:
                        found.append(child.get_text()[start:end])
                walk(child)
                child = child.get_next_sibling()

        if self.article_scroll is not None:
            walk(self.article_scroll)
        if not found:
            return False
        self.get_clipboard().set("\n".join(found))
        return True

    def _picture(self, alt: str) -> Gtk.Picture:
        picture = Gtk.Picture(can_shrink=True, content_fit=Gtk.ContentFit.SCALE_DOWN, halign=Gtk.Align.START,
                              alternative_text=alt)
        picture.add_css_class("reeds-image")
        picture.set_visible(False)
        return picture

    def _block(self, block: feeds_lib.Block, pictures: list) -> Gtk.Widget | None:
        if block.kind == "p":
            return self._label(block.text)
        if block.kind in ("h1", "h2", "h3"):
            return self._label(block.text, {"h1": "title-2", "h2": "lead", "h3": "label"}[block.kind], css="reeds-heading")
        if block.kind == "quote":
            return self._label(block.text, muted=True, css="reeds-quote")
        if block.kind == "li":
            row = Gtk.Box(spacing=10, margin_start=6)
            mark = Gtk.Label(xalign=1, yalign=0, width_chars=2)
            # Same size as the text, with tabular figures so a list's numbers line up.
            mark.set_markup(f"<span font_features='tnum'>{block.number}.</span>" if block.number else "•")
            apply_type(mark, "body", muted=True)
            row.append(mark)
            row.append(self._label(block.text))
            return row
        if block.kind == "pre":
            inset = Inset(padding="card")
            code = Gtk.Label(label=block.text, xalign=0, selectable=True)
            code.add_css_class("reeds-code")
            scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
                                          vscrollbar_policy=Gtk.PolicyType.NEVER, propagate_natural_height=True, child=code)
            inset.append(scroller)
            return inset
        if block.kind == "hr":
            return Gtk.Separator()
        if block.kind == "img":
            if not self.load_images or len(pictures) >= MAX_IMAGES:
                return None
            picture = self._picture(block.alt)
            pictures.append((picture, block.src))
            return picture
        return None

    def _load_picture(self, picture: Gtk.Picture, url: str, entry_id: int) -> None:
        def work() -> bytes | None:
            try:
                return feeds_lib.fetch_bytes(url)
            except FeedError:
                return None

        def done(future: Future) -> bool:
            data = future.result()
            if self.closed or not data or self.selected is None or self.selected.id != entry_id or picture.get_root() is None:
                return False
            try:
                picture.set_paintable(Gdk.Texture.new_from_bytes(GLib.Bytes.new(data)))
                picture.set_visible(True)
            except GLib.Error:
                pass
            return False

        self.pool.submit(work).add_done_callback(lambda future: GLib.idle_add(done, future))

    # ── The corner (a computer) and the bars ────────────────────────────────

    def _render_corner(self) -> None:
        entry = self.selected
        if entry is None or self.phone:
            self.corner_slot.set_child(None)
            return
        self.corner_slot.set_child(CornerPill(
            actions=[("square-arrow-out-up-right", "Open in browser", self.open_original)],
            states=[("star", "Star", entry.starred, lambda on: self._set_flag("starred", on)),
                    ("bookmark", "Read later", entry.later, lambda on: self._set_flag("later", on))]))

    def _more_items(self) -> list[BarAction]:
        items: list[BarAction] = []
        if self.selected is not None:
            items.append(BarAction("link", "Copy link", on_activate=self.copy_link))
        items.append(BarAction("refresh-cw", "Refresh feeds", on_activate=self.refresh))
        items.append(BarAction("check-check", "Mark all as read", on_activate=self.mark_all_read))
        if self.place.startswith("feed:") and self.selected is None:
            feed = self.lib.feed(int(self.place[5:]))
            if feed is not None:
                items += [BarAction("pen-line", "Rename feed…", on_activate=lambda: self.rename_feed(feed)),
                          BarAction("folder", "Move to folder…", on_activate=lambda: self.move_feed(feed)),
                          BarAction("trash-2", "Unsubscribe", danger=True, on_activate=lambda: self.ask_unsubscribe(feed))]
        items += [BarAction("download", "Import feeds…", on_activate=self.import_feeds),
                  BarAction("upload", "Export feeds…", on_activate=self.export_feeds),
                  BarAction("image", "Pictures in articles", active=self.load_images, on_activate=self.toggle_images)]
        return items

    def _places_panel(self):
        counts = self.lib.counts()
        rows = [PanelRow(label, icon=icon, current=self.place == key, count=(counts["unread"] if key == "all" else counts[key]) or None,
                         on_activate=lambda key=key: self.go(key)) for key, label, icon in LIGHT_PLACES]
        for feed in self.lib.feeds():
            rows.append(PanelRow(feed.title or feed.url, icon="radio-tower", current=self.place == f"feed:{feed.id}",
                                 count=feed.unread or None, on_activate=lambda key=f"feed:{feed.id}": self.go(key)))
        return panel_list(rows, label="Places")

    def _places_action(self) -> BarAction:
        return BarAction("inbox", self._place_title(), key="places", dropdown=True, panel=self._places_panel)

    def _compact(self) -> bool:
        """Narrower than the sidebar: it is a drawer, and a tablet has no title row to open it from."""
        return self.tier != "regular"

    def _render_bars(self) -> None:
        has_feeds = bool(self.lib.feeds())
        article = self.selected
        # The page's bar: this article's actions, or nothing is open and it holds the list's.
        if not has_feeds:
            self.page_center.show_bar([BarAction("square-pen", tooltip="Add feed", on_activate=self.add_feed),
                                       BarAction("sparkles", "Add suggested feeds", primary=True,
                                                 on_activate=self.add_suggested)],
                                      more=[BarAction("download", "Import feeds…", on_activate=self.import_feeds)])
        elif article is not None:
            direct = [self._places_action()] if self._compact() and not self.phone else []
            if self.phone:
                direct += [BarAction("star", tooltip="Star", active=article.starred, on_activate=self.toggle_star),
                           BarAction("bookmark", tooltip="Read later", active=article.later, on_activate=self.toggle_later),
                           BarAction("square-arrow-out-up-right", tooltip="Open in browser", on_activate=self.open_original)]
            direct += [BarAction("arrow-up", tooltip="Previous article", on_activate=self.previous_article,
                                 sensitive=self._index() > 0),
                       BarAction("eye-off", tooltip="Mark as unread", on_activate=self.toggle_read),
                       BarAction("arrow-down", "Next", primary=True, on_activate=self.next_article,
                                 sensitive=self._index() < len(self.shown) - 1)]
            self.page_center.show_bar(direct, more=self._more_items())
        else:
            self.page_center.show_bar(self._resting_actions(), more=self._more_items())
        # A phone's list has its own bar: the place picker, search, then what you do with the list.
        if self.phone:
            if not has_feeds:
                self.list_center.show_bar([BarAction("square-pen", tooltip="Add feed", on_activate=self.add_feed),
                                           BarAction("sparkles", "Add suggested feeds", primary=True,
                                                     on_activate=self.add_suggested)],
                                          more=[BarAction("download", "Import feeds…", on_activate=self.import_feeds)])
            else:
                self.list_center.show_bar(
                    [self._places_action(),
                     BarAction("search", tooltip="Search articles", on_activate=self._open_phone_search),
                     BarAction("refresh-cw", "Refresh", primary=True, on_activate=self.refresh)],
                    more=self._more_items())

    def _resting_actions(self) -> list[BarAction]:
        picker = [self._places_action()] if self._compact() else []
        return picker + [BarAction("check-check", tooltip="Mark all as read", on_activate=self.mark_all_read),
                BarAction("square-pen", tooltip="Add feed", on_activate=self.add_feed),
                BarAction("refresh-cw", "Refresh", primary=True, on_activate=self.refresh)]

    def _index(self) -> int:
        return self.shown.index(self.selected.id) if self.selected and self.selected.id in self.shown else 0

    def _toast_host(self) -> Gtk.Widget:
        return self.list_host if self.phone and self.selected is None else self.page_host

    def _center(self) -> ActionCenter:
        return self.list_center if self.phone and self.selected is None else self.page_center

    # ── What you do with an article ─────────────────────────────────────────

    def _set_flag(self, flag: str, value: bool) -> None:
        if self.selected is None:
            return
        self.lib.set_flag(self.selected.id, flag, value)
        setattr(self.selected, flag, value)
        if flag == "read":
            self._row_read(self.selected.id, value)
        self._update_counts()
        self._render_corner()
        self._render_bars()

    def toggle_star(self) -> None:
        if self.selected is None:
            return
        on = not self.selected.starred
        self._set_flag("starred", on)
        Toast.show(self._toast_host(), "Starred" if on else "Star removed", kind="favourite" if on else "unfavourite")

    def toggle_later(self) -> None:
        if self.selected is None:
            return
        on = not self.selected.later
        self._set_flag("later", on)
        Toast.show(self._toast_host(), "Saved to read later" if on else "Removed from read later",
                   kind="saved" if on else "undone")

    def toggle_read(self) -> None:
        if self.selected is None:
            return
        self._set_flag("read", not self.selected.read)
        Toast.show(self._toast_host(), "Marked as read" if self.selected.read else "Marked as unread", kind="done")

    def open_original(self) -> None:
        if self.selected is not None and self.selected.link:
            self._launch(self.selected.link)

    def copy_link(self) -> None:
        if self.selected is not None and self.selected.link:
            self.get_clipboard().set(self.selected.link)
            Toast.show(self._toast_host(), "Link copied", kind="copied")

    def mark_all_read(self) -> None:
        ids = self.lib.mark_all_read(self.place)
        if not ids:
            Toast.show(self._toast_host(), "Everything here is already read", kind="done")
            return
        self.keep |= set(ids)
        for entry_id in ids:
            self._row_read(entry_id, True)
        if self.selected is not None:
            self.selected.read = True
        self._update_counts()
        self._render_bars()
        Toast.show(self._toast_host(), f"{len(ids)} marked as read", kind="done", undo=lambda: self._unmark(ids))

    def _unmark(self, ids: list[int]) -> None:
        self.lib.mark_unread(ids)
        self.keep -= set(ids)
        self._render_all()

    def toggle_images(self) -> None:
        self.load_images = not self.load_images
        self.lib.set_setting("images", "1" if self.load_images else "0")
        if self.selected is not None:
            self._show_article(self.selected)
        self._render_bars()
        Toast.show(self._toast_host(), "Pictures shown" if self.load_images else "Pictures hidden", kind="done")

    # ── Search and filters ──────────────────────────────────────────────────

    def _search_changed(self, text: str) -> None:
        text = text.strip()
        if text != self.query:
            self.query = text
            self._render_list()

    def _filter_changed(self, key: str) -> None:
        self.unread_only = key == "unread"
        self.lib.set_setting("unread_only", "1" if self.unread_only else "0")
        self.keep = set()
        self._render_list()

    def _focus_search(self) -> None:
        if self.phone:
            self._open_phone_search()
        else:
            entry = getattr(self.foot, "entry", None)
            if entry is not None:
                entry.grab_focus()

    def _open_phone_search(self) -> None:
        self.list_center.search(self._search_changed, placeholder="Search articles", text=self.query,
                                on_close=self._close_phone_search)

    def _close_phone_search(self) -> None:
        if self.query:
            self.query = ""
            self._render_list()
        self._render_bars()

    # ── Adding, renaming and removing feeds ─────────────────────────────────

    def _ask_text(self, placeholder: str, icon: str, on_submit, text: str = "") -> None:
        center = self._center()
        self._return_to = self.get_focus()
        entry = BarEntry("quick", icon=icon, placeholder=placeholder, text=text,
                         on_submit=lambda value: self._submitted(value, on_submit), on_close=self._ask_closed)
        center.show_bar([BarAction("x", "Cancel", on_activate=self._ask_closed)], entry=entry)
        try:
            entry.widget.text_widget.grab_focus()
        except AttributeError:
            pass

    def _ask_closed(self) -> None:
        """The bar's field is done (Escape, Cancel or Enter): the bar returns and so does focus."""
        self._render_bars()
        GLib.idle_add(self._return_focus)

    def _return_focus(self) -> bool:
        target, self._return_to = getattr(self, "_return_to", None), None
        if target is not None and target.get_mapped() and target.get_root() is self and target.get_sensitive():
            target.grab_focus()
        else:
            self.focus_pane("list") or self.focus_pane("sidebar")
        return False

    def _submitted(self, value: str, handler) -> None:
        self._ask_closed()
        handler(value.strip())

    def add_feed(self) -> None:
        self._ask_text("Feed or website address", "plus", self._add_address)

    def _add_address(self, text: str) -> None:
        if not text:
            return
        try:
            address = feeds_lib.clean_url(text)
        except FeedError as error:
            Toast.show(self._toast_host(), str(error), kind="error")
            return
        known = self.lib.feed_by_url(address)
        if known is not None:
            self.go(f"feed:{known.id}")
            Toast.show(self._toast_host(), f"Already following {known.title or address}", kind="done")
            return
        self._busy_toast = Toast.show(self._toast_host(), "Looking for a feed", busy=True)

        def work() -> tuple[feeds_lib.Feed | None, str]:
            try:
                return feeds_lib.fetch_feed(address), ""
            except FeedError as error:
                return None, str(error)
            except Exception:  # whatever went wrong, the toast must resolve
                return None, "That feed couldn’t be read."

        def done(future: Future) -> bool:
            feed, error = future.result()
            if self.closed:
                return False
            if feed is None:
                Toast.show(self._toast_host(), error, kind="error")
                return False
            existing = self.lib.feed_by_url(feed.url)
            feed_id, _ = (existing.id, False) if existing else self.lib.add_feed(feed.url, feed.title, site_url=feed.site_url)
            self.lib.store(feed_id, feed)
            self.keep = set()
            self.place, self.selected = f"feed:{feed_id}", None
            self._render_all()
            if self.phone:
                self.list_first.show_list()
            Toast.show(self._toast_host(), f"Added {feed.title or feed.url}", kind="added")
            return False

        self.pool.submit(work).add_done_callback(lambda future: GLib.idle_add(done, future))

    def add_suggested(self) -> None:
        """Adds the starter feeds that aren't here yet, then fetches them."""
        added = []
        for title, address, folder in SUGGESTED:
            feed_id, created = self.lib.add_feed(address, title, folder)
            if created:
                added.append(feed_id)
        if not added:
            Toast.show(self._toast_host(), "Those feeds are already here", kind="done")
            return
        self.place, self.selected, self.keep = "all", None, set()
        self._render_all()
        if self.phone:
            self.list_first.show_list()
        self._focus_list_after_refresh = True
        self.refresh([f for f in self.lib.feeds() if f.id in added])

    def rename_feed(self, feed: FeedRow) -> None:
        self._ask_text("Feed name", "pen-line", lambda text: self._renamed(feed, text), text=feed.title)

    def _renamed(self, feed: FeedRow, text: str) -> None:
        if text:
            self.lib.rename_feed(feed.id, text)
            self._render_all()
            Toast.show(self._toast_host(), "Feed renamed", kind="done")

    def move_feed(self, feed: FeedRow) -> None:
        self._ask_text("Folder name, or leave empty for none", "folder", lambda text: self._moved(feed, text), text=feed.folder)

    def _moved(self, feed: FeedRow, text: str) -> None:
        self.lib.move_feed(feed.id, text)
        self._render_sidebar()
        self._render_bars()
        Toast.show(self._toast_host(), f"Moved to {text}" if text else "Removed from its folder", kind="done")

    def ask_unsubscribe(self, feed: FeedRow) -> None:
        DestructiveDialog.in_bar(
            self._center(), title=f"Unsubscribe from {feed.title or 'this feed'}?",
            body="Its articles are removed from Reeds, including any you starred or saved.",
            action="Unsubscribe", on_confirm=lambda: self._unsubscribe(feed), on_cancel=self._render_bars)

    def _unsubscribe(self, feed: FeedRow) -> None:
        address, title, folder, site = feed.url, feed.title, feed.folder, feed.site_url
        self.lib.remove_feed(feed.id)
        if self.place == f"feed:{feed.id}":
            self.place, self.selected = "all", None
        self._render_all()
        if self.phone:
            self.list_first.show_list()
        Toast.show(self._toast_host(), "Unsubscribed", kind="deleted", undo=lambda: self._resubscribe(address, title, folder, site))

    def _resubscribe(self, address: str, title: str, folder: str, site: str) -> None:
        feed_id, _ = self.lib.add_feed(address, title, folder, site)
        self._render_all()
        self.refresh([self.lib.feed(feed_id)])

    # ── Import and export ───────────────────────────────────────────────────

    def import_feeds(self) -> None:
        ask_for_file(self, FileRequest("Import feeds"), self._import_chosen)

    def _import_chosen(self, files: list[Gio.File] | None) -> None:
        if not files:
            return
        try:
            data = files[0].load_contents(None)[1]
            found = feeds_lib.read_opml(bytes(data))
        except (GLib.Error, FeedError) as error:
            Toast.show(self._toast_host(), "That file isn’t a feed list", kind="error")
            return
        added = []
        for title, address, folder in found:
            try:
                address = feeds_lib.clean_url(address)
            except FeedError:
                continue
            feed_id, created = self.lib.add_feed(address, title, folder)
            if created:
                added.append(feed_id)
        self._render_all()
        if not added:
            Toast.show(self._toast_host(), "Those feeds are already here", kind="done")
            return
        Toast.show(self._toast_host(), f"{len(added)} feeds imported", kind="added")
        self.refresh([f for f in self.lib.feeds() if f.id in added])

    def export_feeds(self) -> None:
        ask_for_file(self, FileRequest("Export feeds", mode="save", name="reeds-feeds.opml"), self._export_chosen)

    def _export_chosen(self, files: list[Gio.File] | None) -> None:
        if not files:
            return
        rows = [(f.title, f.url, f.site_url, f.folder) for f in self.lib.feeds()]
        try:
            files[0].replace_contents(feeds_lib.write_opml(rows), None, False, Gio.FileCreateFlags.REPLACE_DESTINATION, None)
        except GLib.Error:
            Toast.show(self._toast_host(), "Couldn’t save the file", kind="error")
            return
        Toast.show(self._toast_host(), "Feeds exported", kind="downloaded")

    # ── Refreshing ──────────────────────────────────────────────────────────

    @staticmethod
    def _find_labelled(root: Gtk.Widget, label: str) -> Gtk.Widget | None:
        child = root.get_first_child()
        while child is not None:
            if getattr(child, "get_label", lambda: None)() == label and child.get_focusable():
                return child
            found = ReedsWindow._find_labelled(child, label)
            if found is not None:
                return found
            child = child.get_next_sibling()
        return None

    def _initial_focus(self) -> bool:
        """Where focus starts. With no feeds, the one thing to do; on a phone, the list (a desktop's
        sidebar already has it). Tries again until the window is on screen."""
        self._initial_tries = getattr(self, "_initial_tries", 0) + 1
        if self.closed or self._initial_tries > 40:
            return False
        if not self.lib.feeds():
            button = self._find_labelled(self.page_stack, "Add suggested feeds")
            return not (button is not None and button.get_mapped() and button.grab_focus())
        if self.phone:
            return not (self.get_mapped() and self.focus_pane("list"))
        return False

    def _first_refresh(self) -> bool:
        if self.closed:
            return False
        stale = [f for f in self.lib.feeds() if time.time() - f.checked > STALE_AFTER]
        if stale:
            self.refresh(stale, quiet=True)
        return False

    def _timed_refresh(self) -> bool:
        if self.closed:
            return False
        self.refresh(quiet=True)
        return True

    def refresh(self, feeds: list[FeedRow] | None = None, quiet: bool = False) -> None:
        feeds = [f for f in (feeds if feeds is not None else self.lib.feeds()) if f is not None]
        if self.refreshing or not feeds:
            if not feeds and not quiet:
                Toast.show(self._toast_host(), "Add a feed to refresh", kind="warning")
            return
        self.refreshing = True
        self._pending, self._new, self._failed, self._total = len(feeds), 0, 0, len(feeds)
        self._progress = None if quiet else Toast.progress(self._toast_host(), "Refreshing feeds", count=f"0 of {len(feeds)}")
        for feed in feeds:
            etag, modified = self.lib.validators(feed.id)
            self.pool.submit(self._fetch_one, feed.id, feed.url, etag, modified).add_done_callback(
                lambda future: GLib.idle_add(self._fetched, future))

    @staticmethod
    def _fetch_one(feed_id: int, url: str, etag: str, modified: str):
        try:
            return feed_id, feeds_lib.fetch_feed(url, etag=etag, modified=modified), ""
        except FeedError as error:
            return feed_id, None, str(error)
        except Exception:  # a feed must never take the window down with it
            return feed_id, None, "That feed couldn’t be read."

    def _fetched(self, future: Future) -> bool:
        feed_id, feed, error = future.result()
        if self.closed:
            return False
        if feed is not None:
            self._new += self.lib.store(feed_id, feed)
        else:
            self._failed += 1
            self.lib.mark_error(feed_id, error)
        self._pending -= 1
        if self._progress is not None:
            self._progress.update("Refreshing feeds", count=f"{self._total - self._pending} of {self._total}")
        if self._pending == 0:
            self._refreshed()
        return False

    def _refreshed(self) -> None:
        self.refreshing = False
        self._render_sidebar()
        if self._new or self._failed:
            self._render_list()
        self._render_bars()
        if self._focus_list_after_refresh:
            self._focus_list_after_refresh = False
            self.focus_pane("list")
        if self._progress is not None:
            if self._failed == self._total:
                self._progress.finish("Couldn’t reach any feed")
            elif self._new:
                self._progress.finish(f"{self._new} new article{'s' if self._new != 1 else ''}")
            else:
                self._progress.finish("Everything is up to date")
            self._progress = None

    def _closing(self, *_args) -> bool:
        self.closed = True
        self.pool.shutdown(wait=False, cancel_futures=True)
        self.lib.close()
        return False


# ── The application ─────────────────────────────────────────────────────────


class ReedsApplication(Adw.Application):
    def __init__(self) -> None:
        super().__init__(application_id=APP_ID)
        self.library: Library | None = None

    def do_activate(self) -> None:
        window = self.props.active_window
        if window is None:
            self.library = Library()
            window = ReedsWindow(self, self.library)
            shot = os.environ.get("APP_SHOT")
            if shot:
                GLib.timeout_add(400, lambda: self._preview(window))
                window.set_default_size(int(os.environ.get("APP_WIDTH", "1024")), int(os.environ.get("APP_HEIGHT", "720")))
                GLib.timeout_add(int(os.environ.get("APP_WAIT", "2500")), lambda: self._screenshot(window, shot))
        window.present()

    @staticmethod
    def _preview(window: ReedsWindow) -> bool:
        """For checking the layout: REEDS_PLACE picks a place and REEDS_OPEN an article by position."""
        place = os.environ.get("REEDS_PLACE")
        if place:
            window.go(place)
        if os.environ.get("REEDS_OPEN") is not None and window.shown:
            window.open_entry(window.shown[int(os.environ["REEDS_OPEN"])])
        return False

    @staticmethod
    def _screenshot(window: Gtk.Window, path: str) -> bool:
        from gi.repository import Graphene
        width, height = window.get_width(), window.get_height()
        scale = float(os.environ.get("APP_SCALE", "1"))        # 2 renders a 2x picture, for the store
        snapshot = Gtk.Snapshot()
        snapshot.scale(scale, scale)
        Gtk.WidgetPaintable.new(window).snapshot(snapshot, width, height)
        texture = window.get_renderer().render_texture(
            snapshot.to_node(), Graphene.Rect().init(0, 0, round(width * scale), round(height * scale)))
        texture.save_to_png(path)
        window.close()
        return False


if __name__ == "__main__":
    raise SystemExit(ReedsApplication().run(sys.argv[:1]))
