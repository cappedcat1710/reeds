---
version: alpha
name: "simplyluma.com-design-analysis"
description: >
  Luma is a free, open-source operating system for every screen, and its design language, LumaUI, is calm,
  physical and quiet. Surfaces are real materials: a recessed well, a raised chip, a floating glass action
  bar and one dark "key" for the single primary action. Colour is rare and meaningful (one accent per view,
  plus the content's own colour), type is Figtree throughout, and every part scales from a 360 px phone to a
  TV. The marketing site (simplyluma.com) wraps that in a warm paper canvas with very large rounded cards and
  one orange call to action. Sources: the LumaUI token sheets shipped in org.projectluma.Platform//44
  (/usr/share/luma-appkit) for the OS, and a live crawl of simplyluma.com for the brand.

colors:
  # LumaUI, light treatment (luma-appkit-tokens.css)
  window: "#eceef1"
  island: "#ffffff"
  content: "#ffffff"
  card: "#ffffff"
  chrome: "#f2f3f5"
  menu: "#f6f7f8"
  ink: "#14161a"
  ink-secondary: "#404247"
  muted: "#6c6f73"
  faint: "#96989c"
  hairline: "rgba(17, 24, 39, 0.10)"
  line: "rgba(39, 48, 56, 0.095)"
  fill: "rgba(39, 48, 56, 0.04)"
  hover: "rgba(39, 48, 56, 0.06)"
  pressed: "rgba(39, 48, 56, 0.105)"
  selected: "rgba(39, 48, 56, 0.105)"
  well: "rgba(20, 22, 26, 0.075)"
  well-ring: "rgba(20, 22, 26, 0.06)"
  key: "#33353a"
  key-end: "#191b1e"
  key-ink: "#ffffff"
  accent: "#527fae"
  accent-soft: "alpha(#527fae, 0.14)"
  focus-ring: "#1a609e"
  good: "#2e9e52"
  favourite: "#edb345"
  destructive: "#b75048"
  warning-ink: "#ab5900"
  green: "#3b8967"
  violet: "#865f9f"
  amber: "#a06d34"
  mark-blue: "#60aaf3"
  mark-teal: "#00bcc5"
  mark-green: "#62bb78"
  mark-yellow: "#bea333"
  mark-orange: "#e28d4f"
  mark-red: "#eb827b"
  mark-pink: "#e181b0"
  mark-purple: "#b191ea"
  mark-violet: "#9d98f2"
  # simplyluma.com brand
  brand-paper: "#f4f2ed"
  brand-ink: "#1f2937"
  brand-heading: "#111210"
  brand-surface: "#ffffff"
  brand-muted: "#6b7280"
  brand-line: "#1118271a"
  brand-accent: "#ff654f"
  brand-cta: "#fe6819"
  brand-lime: "#d8ff63"
  brand-blue: "#4878b8"
  brand-dark: "#111210"

colors-dark:
  # LumaUI, dark treatment (luma-appkit-dark-tokens.css). Names match the light set.
  window: "#202124"
  island: "rgba(255, 255, 255, 0.035)"
  content: "#25282d"
  menu: "#252a30"
  ink: "#f2f3f5"
  ink-secondary: "#c2c4c7"
  muted: "#8d8f93"
  faint: "#616367"
  line: "rgba(255, 255, 255, 0.08)"
  fill: "rgba(255, 255, 255, 0.038)"
  hover: "rgba(255, 255, 255, 0.06)"
  pressed: "rgba(255, 255, 255, 0.108)"
  selected: "rgba(255, 255, 255, 0.108)"
  well: "#17191c"
  well-ring: "rgba(0, 0, 0, 0.42)"
  key: "#e7e8ea"
  key-end: "#cecfd2"
  key-ink: "#151619"
  accent: "#80a8d2"
  accent-soft: "alpha(#80a8d2, 0.20)"
  focus-ring: "#97c9fd"
  good: "#61cb7c"
  destructive: "#e97870"
  warning-ink: "#dc932e"
  green: "#65b58c"
  violet: "#b58bd0"
  amber: "#d19447"

typography:
  # LumaUI type roles (TYPE_SCALE). Sizes are px at 1x; the family is Figtree, supplied by the system.
  display:    { fontFamily: "Figtree", fontSize: 72px, fontWeight: 600, lineHeight: 1.1, letterSpacing: -0.035em, numeric: tabular }
  hero:       { fontFamily: "Figtree", fontSize: 30px, fontWeight: 700, lineHeight: 1.45, letterSpacing: -0.03em }
  title-1:    { fontFamily: "Figtree", fontSize: 24px, fontWeight: 650, lineHeight: 1.15, letterSpacing: -0.024em }
  title-2:    { fontFamily: "Figtree", fontSize: 15px, fontWeight: 650, lineHeight: 1.3, letterSpacing: -0.01em }
  lead:       { fontFamily: "Figtree", fontSize: 14px, fontWeight: 500, lineHeight: 1.45, letterSpacing: 0, tone: secondary }
  body:       { fontFamily: "Figtree", fontSize: 13px, fontWeight: 400, lineHeight: 1.45, letterSpacing: -0.006em }
  caption:    { fontFamily: "Figtree", fontSize: 11.5px, fontWeight: 500, lineHeight: 1.35, letterSpacing: 0.01em, tone: muted }
  label:      { fontFamily: "Figtree", fontSize: 11.5px, fontWeight: 600, lineHeight: 1.3, letterSpacing: 0.01em, tone: muted }
  numeric:    { fontFamily: "Figtree", fontSize: 30px, fontWeight: 500, lineHeight: 1.1, letterSpacing: -0.02em, numeric: tabular }
  page-title: { fontFamily: "Figtree", fontSize: 32px, fontWeight: 750, lineHeight: 1.1, letterSpacing: -0.03em }   # ListFirst title on a phone
  # simplyluma.com
  site-h2:    { fontFamily: "Figtree", fontSize: 51.84px, fontWeight: 560, lineHeight: 1.08, letterSpacing: -2.07px }
  site-h3:    { fontFamily: "Figtree", fontSize: 21.6px, fontWeight: 580, lineHeight: 1.25, letterSpacing: -0.65px }
  site-body:  { fontFamily: "Figtree", fontSize: 15.84px, fontWeight: 400, lineHeight: 1.5, letterSpacing: -0.24px }
  site-button: { fontFamily: "Figtree", fontSize: 15px, fontWeight: 600, lineHeight: 1.5 }

rounded:
  # LumaUI
  tooltip: 8px
  chip: 9px
  button: 10px
  key: 12px
  bar: 16px
  card: 16px
  inset-card: 18px
  window: 20px
  inset: 20px
  drawer: 28px
  round: 999px
  # simplyluma.com
  site-card: 24px
  site-card-sm: 20px
  site-card-phone: 22px

spacing:
  window-gutter: 8px
  phone-gutter: 16px
  inset-padding: 8px
  inset-card-padding: 16px
  sidebar-width: 272px
  sidebar-narrow-width: 236px
  details-width: 288px
  title-row: 46px
  touch-target: 44px
  site-section-y: 140px
  site-shell-max: 1440px

components:
  window:
    backgroundColor: "{colors.window}"
    rounded: "{rounded.window}"
    padding: 8px
  island:
    backgroundColor: "{colors.island}"
    rounded: "12px"
  sidebar-row:
    height: 50px
    rounded: "11px"
    padding: 6px 8px
    textColor: "{colors.ink}"
    typography: "{typography.body}"
  sidebar-row-selected:
    backgroundColor: "{colors.selected}"
  action-bar:
    rounded: "{rounded.bar}"
    padding: 4px
  button-plain:
    backgroundColor: "{colors.fill}"
    textColor: "{colors.ink}"
    rounded: "{rounded.button}"
    height: 36px
    padding: 0 12px
  button-key:
    backgroundColor: "{colors.key}"
    textColor: "{colors.key-ink}"
    rounded: "{rounded.key}"
    height: 36px
    padding: 0 14px
  button-danger:
    textColor: "{colors.destructive}"
    rounded: "{rounded.button}"
  icon-button:
    size: 36px
    rounded: "{rounded.button}"
  switch:
    width: 38px
    height: 22px
  inset:
    backgroundColor: "{colors.well}"
    rounded: "{rounded.inset}"
    padding: 8px
  card:
    backgroundColor: "{colors.card}"
    rounded: "{rounded.card}"
    padding: 12px 14px 14px
  toast:
    height: 42px
    rounded: "13px"
  dialog:
    width: 340px
    rounded: "20px"
    padding: 24px 20px 20px
  drawer:
    rounded: "{rounded.drawer}"
  tooltip:
    rounded: "{rounded.tooltip}"
    padding: 4px 9px
  site-cta:
    backgroundColor: "{colors.brand-cta}"
    textColor: "#ffffff"
    rounded: "{rounded.round}"
    typography: "{typography.site-button}"
    padding: 0 26px
  site-card:
    backgroundColor: "{colors.brand-surface}"
    rounded: "{rounded.site-card-sm}"
---

# simplyluma.com design analysis

## Overview

**Luma's look is physical but quiet.** The operating system is made of a few real-feeling materials rather
than decoration. A *window* is a tinted frame (`window`). Inside it, *islands* are rounded content surfaces
that each do one job and never nest. Grouped rows sit in a recessed *well* (`Inset`), with no divider lines.
Anything you press is a raised *chip*. Actions float in a glass *bar* at the foot of the island. The single
primary action is the *key*, a dark button in light mode and a pale one in dark mode. Colour comes from the
content (an album, the sky, a person) or from the one accent, never from decoration.

The marketing site is a warmer, louder cousin. It uses a warm paper canvas (`#f4f2ed`), enormous 20 to 24 px
rounded cards with soft long shadows, a full-bleed photographic hero under a dark glass navigation bar, and
a single orange pill call to action (`#fe6819`). It also has one playful moment, a card with a rainbow
gradient border for Luma Sync. The OS itself is cooler and more neutral than the site, and its accent is a
muted blue (`#527fae`), not the site's orange.

**Key characteristics**
- One typeface, **Figtree**, in weights 400 to 750, with tracking tightened as size grows.
- **Tokens, not values.** Colours are `@luma_*`, sizes and radii are named tokens, type is a role.
- **One accent per view**, for focus, selection and the single main action. Meaning never relies on colour alone.
- **Wells divide, lines don't.** No borders around rows, no stacked cards.
- **Content is the colour.** Screens that belong to something take its hue.
- **Light, dark, Frost, Glass and high contrast are a token change**, never an app change.
- **Width, never device.** Under 560 px is the phone tier, 560 to 900 is compact, over 900 is regular.
- **Plain, calm words.** Sentence case, no exclamation marks, buttons say what they do.

## Colors

### Surfaces (OS)
- **Window** (`#eceef1` light, `#202124` dark): the frame behind every island and the sidebar.
- **Island / Content / Card** (`#ffffff` light; `rgba(255,255,255,0.035)` island and `#25282d` content in dark):
  the surface your content sits on. In dark mode the island is a faint lift on the window, not a new colour.
- **Chrome** (`#f2f3f5`) and **Menu** (`#f6f7f8` light, `#252a30` dark): bars, menus and popovers.
- **Well** (`rgba(20,22,26,0.075)` light, `#17191c` dark) with **Well ring**: the recessed group surface.

### Text
- **Ink** (`#14161a` / `#f2f3f5`), **Ink secondary** (`#404247` / `#c2c4c7`), **Muted** (`#6c6f73` / `#8d8f93`),
  **Faint** (`#96989c` / `#616367`). Body text reaches 4.5:1.

### Interaction
- **Accent** (`#527fae` / `#80a8d2`) with **Accent soft** (14% / 20% alpha) for selected and focused states.
- **Focus ring** (`#1a609e` / `#97c9fd`): 2 px, offset 2 px.
- **Hover / Pressed / Selected / Fill / Line**: translucent greys in light (`rgba(39,48,56,…)`) and translucent
  whites in dark. They sit on any surface, which is why nothing needs per-surface colours.
- **Key** (`#33353a` to `#191b1e` gradient in light; `#e7e8ea` to `#cecfd2` in dark) with **Key ink**: the one
  primary or focused thing.

### Meaning
- **Good** `#2e9e52` / `#61cb7c`, **Destructive** `#b75048` / `#e97870`, **Warning ink** `#ab5900` / `#dc932e`,
  **Favourite** `#edb345`.

### Hues
- Marks and content tints: blue `#60aaf3`, teal `#00bcc5`, green `#62bb78`, yellow `#bea333`, orange `#e28d4f`,
  red `#eb827b`, pink `#e181b0`, purple `#b191ea`, violet `#9d98f2` (the same in light and dark).
- Quiet accents for text and icons: green `#3b8967`, violet `#865f9f`, amber `#a06d34` (lightened in dark).

### Brand (simplyluma.com)
- **Paper** `#f4f2ed` canvas, **Surface** `#ffffff` cards, **Ink** `#1f2937`, headings `#111210`, **Muted** `#6b7280`,
  **Line** `#1118271a`, **Accent** `#ff654f` (coral), **CTA** `#fe6819` (orange), **Lime** `#d8ff63`,
  **Blue** `#4878b8`, **Dark band** `#111210` for the footer.

## Typography

Figtree is the system font, loaded as a variable font (weights 300 to 900 on the site). Sizes below are the
LumaUI roles. Apps use the **role**, never a font size.

| Token | Size | Weight | Line height | Tracking | Use |
| --- | --- | --- | --- | --- | --- |
| display | 72 | 600 | 1.1 | -0.035em | Clock face, large numerals (tabular) |
| hero | 30 | 700 | 1.45 | -0.03em | A person's name, a place |
| title-1 | 24 | 650 | 1.15 | -0.024em | Page and article titles |
| title-2 | 15 | 650 | 1.3 | -0.01em | Section titles |
| lead | 14 | 500 | 1.45 | 0 | Introductory line, secondary tone |
| body | 13 | 400 | 1.45 | -0.006em | Default text |
| caption | 11.5 | 500 | 1.35 | +0.01em | Metadata, muted |
| label | 11.5 | 600 | 1.3 | +0.01em | Section labels, muted |
| numeric | 30 | 500 | 1.1 | -0.02em | Changing numbers (tabular figures) |
| page-title | 32 | 750 | 1.1 | -0.03em | The large title above a phone list |

Principles: weight carries emphasis; numbers that change use tabular figures; sentence case everywhere; the
only all-caps allowed is LumaUI's own section labels. Leave room for text up to 40% longer than English.
The site uses the same family at larger sizes (h2 52 px weight 560, h3 21.6 px weight 580, body 15.8 px) with
the same tight negative tracking.

## Layout

- **Window**: 46 px title row (app icon and name with its menu at left, controls at right), an 8 px gutter,
  a 20 px window radius. The title row never shows a window title.
- **Sidebar**: 272 px (236 px below 900), rows 50 px tall with a 34 px face, 11 px radius, 11 px gap.
  Section headings are 11.5 px weight 600. Its foot holds search, filters and the raised New square.
- **Details pane**: 288 px on the trailing side, a bottom drawer on a phone.
- **Tiers**: phone below 560, compact 560 to 900, regular above 900. Phone gutter 16 px.
- **Phone**: lists come first and pages push in with Back at top left; the action bar holds 48 px icon keys.
- **Site**: 1440 px shell, sections padded 140 px top and bottom, content centred on a paper canvas.

## Elevation & Depth

| Level | Treatment | Use |
| --- | --- | --- |
| Window | Flat `window` colour | The frame |
| Island | `island` fill, soft shadow `rgba(25,27,31,0.07)` (dark `rgba(0,0,0,0.22)`) | Content surfaces |
| Well | Recessed: `well` fill, 1 px ring, inner shade | Grouped rows |
| Chip | Raised, 1 px top light | Pressable controls |
| Bar | Floating glass over the island | Action bar |
| Key | Gradient fill, highlight and ring | The one primary action |
| Toast / tooltip | Short soft shadow (tooltip y 6, blur 16, spread -6) | Transient |
| Site card | `0 1px 2px rgba(13,16,13,0.043), 0 18px 48px rgba(13,16,13,0.067)` | Marketing cards |

Materials, not decoration: no glows, gradients or shadows of your own beyond these.

## Shapes

LumaUI radii: tooltip 8, chip 9, button 10, key 12, bar 16, card 16, inset card 18, window and inset 20,
drawer 28, round 999. Smaller controls nest inside larger radii (a 12 px key in a 16 px bar). The site uses
bigger, friendlier curves: 24 px for cards (49 on the homepage), 20 and 22 px variants, and 999 px pills.
Photography is full-bleed and warm (people and rooms), and app icons are one coloured plate with one lit
object (see the icon guide).

## Components

- **Window** (`AppWindow`): frame, title row, identity and menu, window controls. Never add a header bar.
- **Island**: rounded content surface, one job each, never nested.
- **Sidebar** (`NavigationSidebar`, `SidebarRow`, `SidebarFoot`): places; counts in the trail, unread as a dot;
  filters open upward from the foot; selection is LumaUI's own.
- **Action bar** (`ActionCenter`, `BarAction`): grey chips at rest, one filled key, an icon-only action needs a
  tooltip. It grows a panel, splits, becomes an editor and confirms in place instead of opening dialogs.
- **Corner pill** (`CornerPill`): top right of an island, for the view and the thing itself, in a fixed order.
- **Buttons** (`TextButton`): plain, fill, key, danger, raised; 36 px high (28 small, 46 on touch).
- **Icon button**: 36 px square, 10 px radius, 18 px glyph; the label is its accessible name.
- **Switch**: 38 by 22 px with a 16 px knob. **Checkbox**: 16 px, 5 px radius.
- **Inset**: the recessed well, 20 px radius, 8 px padding; `card` padding is 16 px with an 18 px radius.
- **Toast**: 42 px high, 13 px radius, centred above the bar, a plain past-tense line, 2.4 s (4 s with Undo).
- **Dialog** and **destructive confirm**: 340 px wide, 20 px radius; confirm inside the bar where possible, never
  "Are you sure?".
- **Drawer**: 28 px radius, a 36 by 5 px handle, rising from the bottom-left on a phone.
- **Empty state**: a title that says what is missing, a description that says how to add it, at most two actions.
- **Tab bar** (phone): 56 px high, 20 px radius, three or more places with icons.
- **Site call to action**: orange pill (`#fe6819`), white 15 px weight 600 text, 26 px side padding.
- **Site navigation**: dark glass bar over the hero photograph with a small paper-coloured "Try" pill and an
  orange "Download" pill.

## Do's and Don'ts

**Do**
- Compose LumaUI parts and say *what*, not *how* (`style="key"`, `danger=True`).
- Use `@luma_*` colour tokens, Lucide icon names and type roles.
- Put the view and the thing itself top right, what you do now in the bar, search and filters at the sidebar's foot.
- Group rows in an `Inset` and let the well do the dividing.
- Give one filled key per bar and one accent per view.
- Take the content's colour for screens that belong to something.
- Keep every function on a phone, moving it into the ⋯ menu, a drawer or a sheet.
- Make touch targets at least 44 px and nothing depend on hover.
- Write plain, brief, calm text in sentence case.

**Don't**
- Don't restyle a LumaUI part or select `.lumaui-*` classes.
- Don't write literal hex or `rgba()` colours, or font sizes, in app CSS.
- Don't build your own bars, toasts, switches, sidebars or file pickers.
- Don't draw boxes with borders around rows.
- Don't add glows, gradients or shadows of your own.
- Don't branch on "phone"; branch on width.
- Don't use exclamation marks, jokes in errors, or "OK/Yes/No" buttons.
- Don't carry meaning in colour alone.

## Responsive Behavior

| Tier | Width | What changes |
| --- | --- | --- |
| Phone | under 560 | One app full screen, list first, Back top left, 48 px icon keys in the bar, drawers from the bottom-left |
| Compact | 560 to 900 | Panes side by side, the sidebar becomes a drawer below 900 |
| Regular | over 900 | Sidebar beside the content, details pane on the trailing side |
| TV | 1920 by 1080 base | The same app across the room; a sidebar app becomes a floating island with no TV code |

Window controls hide at 480 px and below. Site breakpoints: shell narrows at 1100 px and again at 760 px, and
the card radius drops from 32 to 22 px.

## Iteration Guide

1. Pick the part first (`AppWindow`, `Island`, `ActionCenter`, `NavigationSidebar`…), then its named variant.
2. In CSS put every rule under your own class prefix and use `@luma_*` tokens and `var(--lumaui-…)` sizes.
3. Use `apply_type(widget, "caption")` and `TypeLabel(text, role="title-1")` instead of sizes.
4. Check 360, 500 and 1024 px, in light and dark, with and without a selection.
5. Link text uses `@luma_accent_ink` (a deeper blue in light, a lighter one in dark, so it keeps its contrast). It parses in GTK CSS.
6. Test light by setting the desktop colour scheme, because the toolkit follows the host's scheme and has no
   per-app override.

## Known Gaps

- **Frost, Glass and high-contrast treatments** exist as separate token sheets and were not tabulated here.
- **Figtree weights**: the site declares weights 300 to 900 but only some faces had loaded when sampled.
- **Icons** are Lucide, restricted to the glyphs LumaUI ships (362 at the time of writing); there is no `rss`.
- **Animation curves** are in `MOTION` (ease `0.3,0.7,0.2,1`, hover 120 ms, press 150 ms, morph 300 ms, drawer
  260 ms, bar grow 320 ms) but easing on the site itself was not sampled.
- **The site is light-only**: it renders identically in both colour schemes, so no site dark palette exists.
- **Hero photography, the Luma Sync gradient border and app-icon artwork** were observed in a screenshot but not
  measured; the screenshot was a 1440 by 9415 px full page.
- **Other OS apps' own CSS** (Weather's gradients, Calendar hues) is content-driven and not a token.
