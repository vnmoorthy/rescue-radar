# Rescue Radar theme: "Sunrise"

Inspired by the visual language of prometheus.ai (warm near-black, Work Sans, a wide-tracked uppercase wordmark, a
cinematic sunrise light streak on the horizon). This is our own theme in that spirit: we do not use Prometheus' logo,
wordmark or imagery. Every surface (console, static site, web deck, PowerPoint, README art) uses these tokens.

## Behavior
- Two themes, light and dark. Default follows the OS (`prefers-color-scheme`). A visible toggle in the header switches
  them; the choice persists in `localStorage` (key `rr-theme`) and is applied as `data-theme="light|dark"` on `<html>`
  by an inline script in `<head>` before first paint (no flash).
- `color-scheme` matches the theme so form controls and scrollbars follow.
- Charts, the map basemap and any canvas redraw on a `rr:themechange` event dispatched on `window` after a switch.
- Map basemap: Esri `World_Dark_Gray_Base` + `World_Dark_Gray_Reference` in dark, `World_Light_Gray_Base` +
  `World_Light_Gray_Reference` in light (`https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/<name>/MapServer/tile/{z}/{y}/{x}`),
  attribution kept.

## Type
- UI and body: **Work Sans** 400/500/600 (Google Fonts), fallback `system-ui, -apple-system, Segoe UI, sans-serif`.
- Wordmark and section eyebrows: Work Sans 600, uppercase, letter-spacing 0.28em (wordmark) / 0.14em (eyebrows).
- Data, numbers, timestamps, code: **JetBrains Mono** 400/500, `font-variant-numeric: tabular-nums`.
- Scale: 12 / 13 / 14 / 16 / 20 / 28 / 40 px. Headings use weight 500-600, never 700+.

## Color tokens

| Token | Dark | Light | Use |
| --- | --- | --- | --- |
| `--bg` | `#11120F` | `#F6F5F1` | page background |
| `--bg-elev` | `#161713` | `#FBFAF7` | header, rails |
| `--panel` | `#1B1C18` | `#FFFFFF` | cards and panels |
| `--panel-2` | `#23241F` | `#F0EEE8` | inputs, hover, nested |
| `--line` | `rgba(244,241,234,0.09)` | `rgba(17,18,15,0.10)` | 1px dividers |
| `--line-strong` | `rgba(244,241,234,0.18)` | `rgba(17,18,15,0.20)` | focused borders |
| `--text` | `#F4F1EA` | `#11120F` | primary text |
| `--text-2` | `#B8B5AB` | `#46463F` | secondary text |
| `--text-3` | `#8C8A81` | `#6B6A62` | captions, axis labels |
| `--accent` | `#F2A93B` | `#A85F00` | sunrise amber: primary buttons, active tab, focus ring |
| `--accent-2` | `#FFD27A` | `#D98A1C` | streak highlight, hover |
| `--accent-ink` | `#11120F` | `#FFFFFF` | text on an accent fill |
| `--critical` | `#FF5B3A` | `#C4321A` | rescue-critical (ember) |
| `--critical-soft` | `rgba(255,91,58,0.14)` | `rgba(196,50,26,0.10)` | critical row/chip background |
| `--ok` | `#7BC79A` | `#2E7D4F` | success, "measured" |
| `--info` | `#8FB4D8` | `#2F5F8A` | links, neutral highlights |

Category colors (10 HumAID labels). Rescue-critical are the ember family; everything else is calm and desaturated.

| Label | Dark | Light |
| --- | --- | --- |
| requests_or_urgent_needs | `#FF5B3A` | `#C4321A` |
| injured_or_dead_people | `#FF8A4C` | `#B4501F` |
| missing_or_found_people | `#FFB089` | `#9C3D2A` |
| displaced_people_and_evacuations | `#C9A86A` | `#7A6326` |
| infrastructure_and_utility_damage | `#A9A5D6` | `#4F4A8C` |
| caution_and_advice | `#8FB4D8` | `#2F5F8A` |
| rescue_volunteering_or_donation_effort | `#7BC79A` | `#2E7D4F` |
| sympathy_and_support | `#C79FBF` | `#7A4570` |
| other_relevant_information | `#9E9C93` | `#5E5D56` |
| not_humanitarian | `#6F6D66` | `#8A8981` |

## Motif
- **Sunrise streak:** a 1px horizontal line under the header and above the deck footer:
  `linear-gradient(90deg, transparent 0%, var(--accent) 30%, var(--accent-2) 50%, var(--accent) 70%, transparent 100%)`
  at 70% opacity. Optional soft horizon glow on hero areas:
  `radial-gradient(120% 60% at 50% 100%, color-mix(in srgb, var(--accent) 22%, transparent), transparent 70%)`.
- Corners: 10px panels, 8px controls, 999px chips. Shadows: none in dark; `0 1px 2px rgba(17,18,15,0.06)` in light.
- Motion: 160-240ms ease-out; respect `prefers-reduced-motion`.

## Contrast
Body text and small labels meet WCAG AA (4.5:1) against `--bg` and `--panel` in both themes; accent text on panels
uses `--accent` only at 14px+ semibold or as fills with `--accent-ink` text.
