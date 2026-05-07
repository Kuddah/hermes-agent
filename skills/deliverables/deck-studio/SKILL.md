---
name: deck-studio
description: >
  Create polished presentation slide decks as HTML-first, then export to PPTX
  (fully editable PowerPoint). Use when the user needs a slide deck for any
  purpose — pitch, strategy, report, training, demo, or conference talk. Supports
  1280×720 (16:9) slides with custom CSS themes, royalty-free images, and
  one-command PPTX build.
version: 1.0.0
metadata:
  hermes:
    tags: [slides, pptx, presentation, pitch-deck, deck, deliverables]
    required_toolsets: [deck, file]
    optional_toolsets: [web, image_gen, image_search, browser, memory]
    related_skills: [document-studio, visual-qa, research]
---

# Deck Studio

Build, iterate, and export professional slide decks.

## Core principle

**HTML slides are the source of truth.** Each slide is a standalone `.html`
file rendered at 1280×720 px. The PPTX is generated from the rendered HTML by
`dom-to-pptx` + Playwright — every text box, shape, and image in the browser
becomes a native PowerPoint object.

---

## Workflow

```
BRIEF → OUTLINE → CREATE DECK → BUILD SLIDES → QA CHECK → BUILD PPTX
```

### Step 1 — Brief

Clarify (or infer):

- **Purpose** — pitch / strategy / report / training / conference / demo
- **Audience** — investors / executives / technical / all-hands
- **Slide count** — concise (≤10) / standard (10-20) / deep (20-40)
- **Theme** — dark / light / brand colours (provide hex if known)
- **Project name** — used as `mnt/<project>/presentations/` sandbox

### Step 2 — Outline

Present a slide-by-slide outline before building anything. Each line:

```
1. Title — [slide type] — [one-line content summary]
```

Get approval, then proceed.

### Step 3 — Create the deck

```
deck_create project=<name>
```

This creates `mnt/<name>/presentations/` with `_theme.css`, an `assets/` folder,
and a `snapshots/` folder. All subsequent slides reference `_theme.css` automatically.

### Step 4 — Customise the theme (optional)

```
deck_manage_theme project=<name> css_content=':root { --color-bg: #0d1117; ... }'
```

Write the full CSS content for `_theme.css`. Use `:root { }` CSS variables.

Available theme CSS variables:

| Variable | Default | Purpose |
|---|---|---|
| `--color-bg` | `#0d1117` | slide background |
| `--color-surface` | `#161b22` | card/panel background |
| `--color-primary` | `#58a6ff` | accent, headings |
| `--color-secondary` | `#3fb950` | secondary accent |
| `--color-text` | `#e6edf3` | body text |
| `--color-muted` | `#8b949e` | subtext, captions |
| `--font-heading` | `'Inter', sans-serif` | heading font-family |
| `--font-body` | `'Inter', sans-serif` | body font-family |

### Step 5 — Insert slide stubs

```
deck_insert_slides project=<name> titles='["Title Slide", "Problem", "Solution"]' position=1
```

This creates placeholder slides. Then populate each with `deck_modify_slide`.

### Step 6 — Write slide content

```
deck_modify_slide project=<name> slide_name=slide_01_title html_content="<FULL SLIDE HTML>"
```

Slide HTML template (1280×720, uses `_theme.css`):

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=1280,height=720">
  <link rel="stylesheet" href="_theme.css">
  <style>
    /* slide-specific overrides only */
  </style>
</head>
<body class="slide">
<div class="slide-wrapper">

  <!-- CONTENT HERE — see templates below -->

</div>
</body>
</html>
```

### Step 7 — QA check

```
deck_check project=<name> slide_name=slide_01_title   # checks one slide for overflow + OOB
deck_screenshot project=<name> slide_name=slide_01_title  # takes JPEG screenshot of one slide
```

Fix any issues reported by `deck_check` before building the PPTX.

### Step 8 — Build PPTX

```
deck_build_pptx project=<name>
```

Outputs `mnt/<name>/presentations/<name>.pptx` (fully editable in PowerPoint).

---

## Slide layout patterns

All layouts use the `.slide-wrapper` container (100% width/height, positioned relative,
`overflow:hidden`).

### Title Slide

```html
<div class="slide-wrapper" style="
  display:flex; flex-direction:column;
  justify-content:center; align-items:center; text-align:center;
  background: linear-gradient(135deg, var(--color-bg) 0%, var(--color-surface) 100%);
">
  <p style="color:var(--color-primary);font-size:1rem;letter-spacing:3px;text-transform:uppercase;margin:0 0 16px;">
    COMPANY NAME
  </p>
  <h1 style="color:var(--color-text);font-size:3.5rem;font-weight:700;margin:0 0 24px;max-width:900px;line-height:1.15;">
    Deck Title
  </h1>
  <p style="color:var(--color-muted);font-size:1.1rem;margin:0;">
    Presenter · Date · Occasion
  </p>
</div>
```

### Content Slide (heading + bullets)

```html
<div class="slide-wrapper" style="
  display:flex; flex-direction:column; padding:60px 80px;
  background:var(--color-bg);
">
  <h2 style="color:var(--color-primary);font-size:2rem;font-weight:700;margin:0 0 32px;">
    Section Heading
  </h2>
  <ul style="color:var(--color-text);font-size:1.15rem;line-height:1.9;margin:0;padding-left:1.5rem;">
    <li>Key point one with supporting detail</li>
    <li>Key point two — keep each bullet to one sentence</li>
    <li>Key point three — no more than 6 bullets per slide</li>
  </ul>
</div>
```

### Two-Column Slide

```html
<div class="slide-wrapper" style="
  display:flex; flex-direction:column; padding:50px 70px;
  background:var(--color-bg);
">
  <h2 style="color:var(--color-primary);font-size:1.8rem;font-weight:700;margin:0 0 30px;">
    Slide Title
  </h2>
  <div style="display:flex;gap:50px;flex:1;">
    <div style="flex:1;">
      <h3 style="color:var(--color-text);font-size:1.1rem;font-weight:600;margin:0 0 12px;">Left Column</h3>
      <p style="color:var(--color-muted);font-size:1rem;line-height:1.7;margin:0;">
        Content for left column.
      </p>
    </div>
    <div style="flex:1;">
      <h3 style="color:var(--color-text);font-size:1.1rem;font-weight:600;margin:0 0 12px;">Right Column</h3>
      <p style="color:var(--color-muted);font-size:1rem;line-height:1.7;margin:0;">
        Content for right column.
      </p>
    </div>
  </div>
</div>
```

### Stat / Metric Cards

```html
<div class="slide-wrapper" style="
  display:flex; flex-direction:column; padding:50px 70px;
  background:var(--color-bg);
">
  <h2 style="color:var(--color-primary);font-size:1.8rem;font-weight:700;margin:0 0 36px;">Key Metrics</h2>
  <div style="display:flex;gap:30px;flex:1;">
    <!-- Repeat this card 3-4 times -->
    <div style="flex:1;background:var(--color-surface);border-radius:12px;padding:36px;display:flex;flex-direction:column;justify-content:center;">
      <div style="color:var(--color-primary);font-size:3rem;font-weight:700;">$4.2M</div>
      <div style="color:var(--color-muted);font-size:0.95rem;margin-top:8px;">ARR · +142% YoY</div>
    </div>
  </div>
</div>
```

### Closing / CTA Slide

```html
<div class="slide-wrapper" style="
  display:flex; flex-direction:column;
  justify-content:center; align-items:center; text-align:center;
  background: linear-gradient(135deg, var(--color-surface) 0%, var(--color-bg) 100%);
  padding:80px;
">
  <h2 style="color:var(--color-text);font-size:2.8rem;font-weight:700;margin:0 0 24px;">
    Ready to get started?
  </h2>
  <p style="color:var(--color-muted);font-size:1.2rem;max-width:600px;line-height:1.7;margin:0 0 40px;">
    Supporting statement. Keep it punchy.
  </p>
  <a href="#" style="
    background:var(--color-primary);color:#fff;font-size:1.1rem;font-weight:600;
    padding:16px 40px;border-radius:8px;text-decoration:none;
  ">
    Call to Action
  </a>
</div>
```

---

## Tips

- **Slide count**: 1 idea per slide. 6-10 slides for a focused pitch; up to 20 for a full strategy.
- **Font sizes**: heading ≥1.8rem, body ≥1rem, caption ≥0.85rem at 1280px wide.
- **Images**: use `image_search` to find royalty-free images; `ensure_raster` converts SVG→PNG before embedding.
- **Overflow**: `deck_check` catches elements bleeding out of the 1280×720 viewport. Fix before building PPTX.
- **Iterating**: `deck_read_slide` reads a slide's current HTML; `deck_modify_slide` overwrites it.
- **Slide order**: `deck_list_slides` shows the full deck; `deck_delete_slide` then `deck_insert_slides` to reorder.
- **Screenshots**: `deck_screenshot` renders PNG previews — useful to confirm visual fidelity before the full PPTX build.
