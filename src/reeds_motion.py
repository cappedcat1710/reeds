# SPDX-License-Identifier: Apache-2.0
"""Reeds' motion: what happens on screen when you do something.

Everything here follows Luma's own motion rules:

* durations come from LumaUI's tokens (`luma_appkit.lumaui.duration`), never from numbers of ours;
* the curves are LumaUI's (`MOTION["ease"]`, and `MOTION["spring"]` for a small overshoot);
* with Reduce Motion on, nothing moves: movement becomes a short fade, and with animations off
  it is skipped and the end state appears at once.

The effects are drawn on one transparent layer over the window (`Motion.layer`), so they never
touch a LumaUI part. Each one is decoration for something that has already happened: the data
changes first, the animation only shows it.
"""

from __future__ import annotations

import math
from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gsk", "4.0")
gi.require_version("Graphene", "1.0")
from gi.repository import Adw, GLib, Graphene, Gsk, Gtk  # noqa: E402

from luma_appkit import lumaui, lumaui_icon  # noqa: E402
from luma_appkit.lumaui_tokens import MOTION  # noqa: E402

Point = tuple[float, float]


def bezier(x1: float, y1: float, x2: float, y2: float) -> Callable[[float], float]:
    """A CSS cubic-bezier as a function of progress. y may leave 0..1, which is how a spring overshoots."""
    def at(progress: float) -> float:
        if progress <= 0:
            return 0.0
        if progress >= 1:
            return 1.0
        low, high = 0.0, 1.0
        for _ in range(24):
            t = (low + high) / 2
            x = 3 * (1 - t) ** 2 * t * x1 + 3 * (1 - t) * t ** 2 * x2 + t ** 3
            low, high = (t, high) if x < progress else (low, t)
        t = (low + high) / 2
        return 3 * (1 - t) ** 2 * t * y1 + 3 * (1 - t) * t ** 2 * y2 + t ** 3
    return at


EASE = bezier(*MOTION["ease"])          # LumaUI's standard curve
SPRING = bezier(*MOTION["spring"])      # LumaUI's curve with a small overshoot
GATHER = bezier(0.45, 0, 0.2, 1)        # slow, quick, soft: something being carried away


def _quiet(widget: Gtk.Widget) -> Gtk.Widget:
    """Effects are decoration: they take no clicks and are skipped by screen readers."""
    widget.set_can_target(False)
    widget.set_can_focus(False)
    try:
        widget.set_accessible_role(Gtk.AccessibleRole.PRESENTATION)
    except (AttributeError, TypeError):
        pass
    return widget


class Motion:
    def __init__(self, host: Gtk.Widget) -> None:
        self.host = host                      # the window: what animations are timed against
        self.closed = False
        self.layer = Gtk.Fixed(hexpand=True, vexpand=True)
        _quiet(self.layer)
        self._live: set[Adw.Animation] = set()

    # ── What is allowed right now ───────────────────────────────────────────

    @staticmethod
    def reduced() -> bool:
        return bool(lumaui.reduced_motion())

    @staticmethod
    def ms(name: str, factor: float = 1.0) -> int:
        """A LumaUI motion token in milliseconds, 0 when animations are off, short under Reduce Motion."""
        return round(lumaui.duration(name) * factor)

    def fades(self) -> bool:
        return not self.closed and self.ms("fade") > 0

    def moves(self) -> bool:
        """Things may travel only when Reduce Motion is off."""
        return self.fades() and not self.reduced()

    # ── The one clock ───────────────────────────────────────────────────────

    def run(self, ms: int, tick: Callable[[float], None], done: Callable[[], None] | None = None, *,
            ease: Callable[[float], float] = EASE, delay: int = 0) -> None:
        """Calls tick(p) with eased progress for `ms`, then done(). With no motion it jumps to the end."""
        def finish() -> None:
            tick(ease(1.0))
            if done is not None:
                done()

        if self.closed:                  # the window is going: nothing more should happen, least of all `done`
            return
        if ms <= 0 or not self.fades():
            finish()
            return

        def start() -> bool:
            if self.closed:
                return False
            animation = Adw.TimedAnimation.new(
                self.host, 0.0, 1.0, ms, Adw.CallbackAnimationTarget.new(lambda value: tick(ease(value))))
            animation.set_easing(Adw.Easing.LINEAR)
            self._live.add(animation)

            def ended(_animation: Adw.Animation) -> None:
                self._live.discard(animation)
                if not self.closed:
                    finish()

            animation.connect("done", ended)
            animation.play()
            return False

        if delay > 0:
            GLib.timeout_add(delay, start)
        else:
            start()

    def stagger(self, items: list, fn: Callable, step: int, limit: int = 30) -> None:
        """fn(item) for each item, `step` ms apart; items past `limit` happen with the last one."""
        if self.closed:
            return
        if not self.fades() or step <= 0:
            for item in items:
                fn(item)
            return
        for index, item in enumerate(items):
            delay = min(index, limit) * step
            if delay == 0:
                fn(item)
            else:
                GLib.timeout_add(delay, lambda item=item: (None if self.closed else fn(item), False)[1])

    # ── Geometry ────────────────────────────────────────────────────────────

    def center_of(self, where: Gtk.Widget | Point | None) -> Point | None:
        if where is None:
            return None
        if isinstance(where, tuple):
            return where
        width, height = where.get_width(), where.get_height()
        if width <= 0 or height <= 0 or not where.get_mapped():
            return None
        ok, point = where.compute_point(self.layer, Graphene.Point().init(width / 2, height / 2))
        return (point.x, point.y) if ok else None

    def _place(self, child: Gtk.Widget, at: Point, size: Point, *, scale: float = 1.0, sx: float | None = None,
               sy: float | None = None, rotate: float = 0.0, opacity: float = 1.0) -> None:
        """Puts `child` with its centre at `at`, scaled and turned about its centre."""
        transform = Gsk.Transform.new().translate(Graphene.Point().init(at[0], at[1]))
        if rotate:
            transform = transform.rotate(rotate)
        transform = transform.scale(sx if sx is not None else scale, sy if sy is not None else scale)
        transform = transform.translate(Graphene.Point().init(-size[0] / 2, -size[1] / 2))
        self.layer.set_child_transform(child, transform)
        child.set_opacity(max(0.0, min(1.0, opacity)))

    @staticmethod
    def _arc(a: Point, b: Point, p: float, lift: float) -> Point:
        """A point `p` of the way along a curve from a to b that rises by `lift` in the middle."""
        control = ((a[0] + b[0]) / 2, min(a[1], b[1]) - lift)
        q = 1 - p
        return (q * q * a[0] + 2 * q * p * control[0] + p * p * b[0],
                q * q * a[1] + 2 * q * p * control[1] + p * p * b[1])

    def _ghost(self, widget: Gtk.Widget) -> Gtk.Widget | None:
        """A picture of `widget` as it looks now, as vectors, so it stays sharp on any screen."""
        width, height = widget.get_width(), widget.get_height()
        if width <= 0 or height <= 0 or not widget.get_mapped():
            return None
        snapshot = Gtk.Snapshot()
        Gtk.WidgetPaintable.new(widget).snapshot(snapshot, width, height)
        paintable = snapshot.to_paintable(Graphene.Size().init(width, height))
        if paintable is None:
            return None
        picture = Gtk.Picture.new_for_paintable(paintable)
        picture.set_can_shrink(False)
        picture.set_size_request(width, height)
        return _quiet(picture)

    # ── Appearing ───────────────────────────────────────────────────────────

    def fade_in(self, widget: Gtk.Widget, delay: int = 0, ms: int | None = None) -> None:
        if not self.fades():
            return
        widget.set_opacity(0)
        self.run(ms or self.ms("fade"), lambda p: widget.set_opacity(max(0.0, min(1.0, p))), delay=delay)

    def fade_out(self, widget: Gtk.Widget, done: Callable[[], None] | None = None) -> None:
        if self.closed:
            return
        if not self.fades():
            widget.set_opacity(0)
            if done:
                done()
            return
        self.run(self.ms("fade"), lambda p: widget.set_opacity(1 - max(0.0, min(1.0, p))), done)

    # ── A small pop at something, or something carried to somewhere ─────────

    def burst(self, icon: str, origin: Gtk.Widget | Point | None, *, to: Gtk.Widget | Point | None = None,
              css: str = "reeds-fx-pop", drift: Point = (0, -30), size: int = 22) -> None:
        """An icon pops at `origin` and rises away, or (with `to`) is carried there and lands."""
        if not self.moves():
            return
        start = self.center_of(origin)
        if start is None:
            return
        picture = _quiet(Gtk.Image.new_from_icon_name(lumaui_icon(icon)))
        picture.set_pixel_size(size)
        picture.add_css_class(css)
        self.layer.put(picture, 0, 0)
        box = (float(size), float(size))
        end = self.center_of(to)

        def remove() -> None:
            if picture.get_parent() is self.layer:
                self.layer.remove(picture)

        if end is None:
            def pop(p: float) -> None:
                self._place(picture, (start[0] + drift[0] * p, start[1] + drift[1] * p), box,
                            scale=0.55 + 0.85 * SPRING(min(1.0, p * 1.6)), opacity=1 - max(0.0, (p - 0.45) / 0.55))
            self.run(self.ms("morph", 1.4), pop, remove, ease=lambda p: p)
            return

        def carry(p: float) -> None:
            self._place(picture, self._arc(start, end, p, 70), box, scale=1 + 0.35 * math.sin(math.pi * min(1.0, p * 1.4))
                        - 0.55 * p, opacity=1 - max(0.0, (p - 0.78) / 0.22))

        def landed() -> None:
            remove()
            self.burst(icon, end, css=css, drift=(0, -10), size=size)

        self.run(self.ms("morph", 1.6), carry, landed, ease=GATHER)

    # ── Unsubscribing: the thing is picked up, carried to a bin and tipped in ─

    def _bin(self) -> Gtk.Widget:
        box = _quiet(Gtk.Box(halign=Gtk.Align.START, valign=Gtk.Align.START))
        box.add_css_class("reeds-fx-bin")
        glyph = _quiet(Gtk.Image.new_from_icon_name(lumaui_icon("trash-2")))
        glyph.set_pixel_size(26)
        box.append(glyph)
        return box

    def trash_dump(self, source: Gtk.Widget, done: Callable[[], None], *, bin_at: Point | None = None) -> None:
        """Shows `source` being carried into a bin that pops up, and tipped in. `done` runs as the bin sinks.

        `source` is hidden while the picture of it travels; the caller redraws in `done`, which
        also gives `source` its opacity back."""
        def finish() -> None:
            done()
            source.set_opacity(1)

        if not self.moves():                                   # Reduce Motion: it just fades away
            self.fade_out(source, finish)
            return
        ghost, start = self._ghost(source), self.center_of(source)
        if ghost is None or start is None:
            finish()
            return
        width, height = float(source.get_width()), float(source.get_height())
        layer_w, layer_h = float(self.layer.get_width()), float(self.layer.get_height())
        target = bin_at or (layer_w / 2, layer_h - 170)
        bin_widget = self._bin()
        self.layer.put(ghost, 0, 0)
        self.layer.put(bin_widget, 0, 0)
        bin_size = bin_widget.get_preferred_size()[1]
        bw, bh = float(max(bin_size.width, 1)), float(max(bin_size.height, 1))
        bin_widget.set_opacity(0)
        source.set_opacity(0)                                   # it has been picked up
        side = 1.0 if target[0] >= start[0] else -1.0
        end_scale = max(0.05, 30.0 / max(width, height))
        mouth = (target[0], target[1] - bh * 0.28)              # where things go in

        def bin_at_rest(p_pop: float = 1.0, *, tilt: float = 0.0, sx: float = 1.0, sy: float = 1.0) -> None:
            self._place(bin_widget, (target[0], target[1] + 16 * (1 - p_pop)), (bw, bh), sx=sx * (0.55 + 0.45 * p_pop),
                        sy=sy * (0.55 + 0.45 * p_pop), rotate=tilt, opacity=min(1.0, p_pop * 1.5))

        def cleanup() -> None:
            for widget in (ghost, bin_widget):
                if widget.get_parent() is self.layer:
                    self.layer.remove(widget)

        # 1. The bin pops up while the thing is lifted a little.
        def lift(p: float) -> None:
            bin_at_rest(p)
            self._place(ghost, (start[0], start[1] - 5 * p), (width, height), scale=1 + 0.04 * p)

        # 2. It is carried over in an arc, turning a little, and shrinks into the bin's mouth.
        def carry(p: float) -> None:
            point = self._arc((start[0], start[1] - 5), mouth, p, 90 + abs(target[0] - start[0]) * 0.12)
            shrink = 1.04 + (end_scale - 1.04) * p ** 2.4        # it stays whole in the air and narrows into the mouth
            fade = 1 - max(0.0, (p - 0.88) / 0.12)
            self._place(ghost, point, (width, height), scale=shrink, rotate=side * 20 * p, opacity=fade)
            bin_at_rest(tilt=-9 * p * side)

        # 3. It lands: the bin squashes, wobbles and settles.
        def land(p: float) -> None:
            wobble = math.sin(p * math.pi * 2.5) * (1 - p) * 0.17
            bin_at_rest(tilt=-9 * (1 - p) * side + math.sin(p * math.pi * 3) * (1 - p) * 5, sx=1 + wobble, sy=1 - wobble)

        # 4. The bin sinks away.
        def sink(p: float) -> None:
            self._place(bin_widget, (target[0], target[1] + 10 * p), (bw, bh), scale=1 - 0.2 * p, opacity=1 - p)

        def sink_away() -> None:
            finish()        # what was thrown away is gone from the list as the bin sinks, not after
            self.run(self.ms("fade", 0.9), sink, cleanup, delay=self.ms("fade", 0.1))

        def after_carry() -> None:
            ghost.set_opacity(0)
            self.run(self.ms("morph", 0.8), land, sink_away, ease=lambda p: p)

        self.run(self.ms("morph", 0.6), lift,
                 lambda: self.run(self.ms("morph", 1.9), carry, after_carry, ease=GATHER), ease=SPRING)
