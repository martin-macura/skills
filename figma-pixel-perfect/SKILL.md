---
name: figma-pixel-perfect
description: Implement a Figma design pixel-perfectly and prove it — extract the node's raster + metadata + generated code via the Figma MCP, translate every raw px/hex through the project's tokens and spacing scale, pin mock data to the design's exact values, then converge using an injected difference overlay, pixelmatch, and computed-style audits. Use when the user wants to implement a Figma design/frame/node, match a Figma design exactly, says "pixel perfect", asks to verify a screen against Figma, or says "/figma-pixel-perfect".
---

# figma-pixel-perfect

Take a Figma node to a **verified** pixel-perfect implementation. Three doctrines:

1. **Pixel perfect ≠ raw pixels.** The goal is *visually indistinguishable while staying on the project's design system* — theme tokens, spacing scale, existing components. `w-[313px]` / `bg-[#f4f4f5]` are not fidelity, they're debt (and outright banned in some repos, e.g. siegl's AGENTS.md).
2. **Evidence over inference** ([[figma-matching-workflow]]). Never declare a match from reading code or Figma JSON. Every "matches" claim comes from a rendered screenshot or a computed-style read.
3. **The Figma raster is ground truth; generated code is a hypothesis.** Plugin/MCP codegen is a faithful *draft* at best — never pasted verbatim, always translated.

## Prerequisites

- Figma link with a `node-id` (frame or component level, not a whole page).
- Figma desktop app open on that file with the Dev Mode MCP enabled → `mcp__figma-dev__get_screenshot` / `get_metadata` / `get_design_context` / `get_variable_defs`. Fallbacks: the REST MCP (`mcp__figma__get_figma_data` + `download_figma_images`); when REST 429s, the desktop server answers raw JSON-RPC on `:3845` ([[figma-local-mcp-fallback]]).
- Dev app running (in siegl: [[dev-portless]], DB migrated, logged in).
- Know the project's constraints before drafting: **token source** (siegl: `app/app.css` `@theme` — hex values live there, so Figma hexes reverse-lookup to token names) and **banned raw values** (siegl: no px sizes from Figma, no hardcoded hex).

## 1 · Extract ground truth → translation table

Pull four things from the node:

- `get_screenshot` → the **reference PNG** (note the frame width, e.g. 1440; prefer 2x).
- `get_metadata` → exact box tree (x/y/w/h per layer).
- `get_variable_defs` → which values are design tokens vs. hardcoded in the design.
- `get_design_context` → generated markup (React+Tailwind). Save as *draft input*.

Then build the **translation table** — before any JSX. It doubles as the cleanup spec for generated code:

| Figma value | maps to | how |
| --- | --- | --- |
| hex / variable | theme token class | reverse-lookup the hex in the token source (e.g. `#71717a` → `text-muted-foreground`) |
| px spacing | spacing-scale step | ÷4 (`16px` → `p-4`; `18px` → `gap-4.5` — still on-scale in TW4) |
| font size/weight/leading | `text-*` / `font-*` / `leading-*` | confirm the weight is actually bundled — browsers silently synthesize missing weights |
| recurring cluster | existing component | check the shared UI dir + the feature module before building anything |

**Anything unmappable is a decision, not an improvisation**: nearest token + note it, or raise it with the designer (in siegl: [[clarification-question]]).

## 2 · Draft

Pick the mode per screen:

- **Bespoke layout** (dashboard, tiles, print-like summaries): start from the generated markup → collapse single-child wrapper divs → translate *every* arbitrary value through the table → swap primitive clusters for existing components.
- **Component-composed screen** (typical CRUD: buttons, form fields, tables, dialogs): compose existing components directly; keep the generated markup open as a structure/spacing spec only. Pasting it means re-implementing components the library already has — review will bounce it.

Codegen quality is hostage to the designer's autolayout hygiene: absolutely-positioned output ⇒ discard it and compose by hand from `get_metadata`.

## 3 · Pin the data

Image comparison measures *content* differences unless the data matches. Render exactly the strings/numbers/dates the design shows:

- Full page → seed the dev DB with the design's values.
- Leaf component → a dev-only sandbox route rendering it with hardcoded props.

Match the geometry: **viewport width = frame width, DPR 2 on both sides** (Figma export @2x ↔ `deviceScaleFactor: 2`, which [[dev-hires-screenshot]] already does).

## 4 · Converge — the evidence loop

Iterate largest-first: layout → spacing → typography → color. Four instruments:

**a) Difference overlay in the live page** (scriptable PerfectPixel — no extension needed). Serve the reference PNG (`python3 -m http.server` in its dir works; small files can be a data URI) and inject via the browser MCP `javascript_tool`:

```js
const o = document.createElement('img');
o.src = 'http://localhost:8000/figma-ref.png';   // or data:image/png;base64,…
o.style.cssText = 'position:fixed;top:0;left:0;width:1440px;' + // CSS width = frame width (handles a 2x PNG)
    'mix-blend-mode:difference;pointer-events:none;z-index:99999';
o.id = 'figma-overlay'; document.body.appendChild(o);
// toggle off: document.getElementById('figma-overlay').remove()
```

Matched pixels go black; any drift glows. Screenshot the overlaid page for the record.

**b) pixelmatch for a recordable diff.** Element-vs-node screenshots (Playwright locator screenshot for a component — element-to-node images align, page-to-frame don't), normalize dimensions, then:

```bash
npx pixelmatch ref.png ours.png diff.png 0.1   # or: npx odiff-bin ref.png ours.png diff.png
```

**c) Computed-style audit — the attribution step.** `getComputedStyle` via the browser MCP on the key elements (font-size, line-height, weight, padding, gap, radius, color as rgb) compared against the table. Immune to antialiasing noise, and it names *which* property lies when the overlay shows a 2px drift.

**d) Mechanical sweep for banned survivors** in the changed files:

```bash
git diff --name-only main... | xargs grep -nE '\[#|[0-9]px\]'
```

**Converged when:** the overlay shows only glyph antialiasing, and every computed style matches the table. Text never diffs to zero — Figma's text engine ≠ browser AA — so judge boxes/edges/gaps on the overlay and take typography truth from computed styles.

## 5 · Unpin & record

- Swap back a realistic dataset once — design data is flatteringly short; verify truncate/wrap/`min-w-0` behavior with long strings.
- Produce the paired "design above / ours below" PNG for the PR body (reuse `pair.py` from [[mvp-visual-compare]]).
- List deliberate divergences (off-grid snapping, token substitutions, flexible-width decisions) in the PR description.

## Gotchas

- The table is the only path into the codebase — generated code's values never land directly, even "cleaned up".
- Browser zoom must be 100% and DPR fixed, or every measurement lies.
- States count: enumerate hover/focus/disabled/error/empty from Figma variants — default-state-only is half the job.
- A missing font weight renders as synthesized faux-bold; on the overlay it looks like blurry glyph drift, not a weight error.
