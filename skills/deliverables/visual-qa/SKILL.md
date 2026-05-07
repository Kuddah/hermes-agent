---
name: visual-qa
description: >
  QA checklist and automated review for slides and documents before final export.
  Use when the user says "review my deck", "check the slides", "QA this document",
  or before any `deck_build_pptx` / document export. Combines automated overflow
  detection (deck_check), visual screenshots, and an AI-driven content review.
version: 1.0.0
metadata:
  hermes:
    tags: [qa, review, slides, document, visual, accessibility, deliverables]
    required_toolsets: [deck, file]
    optional_toolsets: [document, browser]
    related_skills: [deck-studio, document-studio]
---

# Visual QA

Systematic review of slides and documents before final export.

---

## When to use

- Before any `deck_build_pptx` call
- Before exporting a document to PDF or DOCX
- When a user asks for a "review" or "proof" pass
- After a major revision to catch regressions

---

## Slide Deck QA Workflow

### Step 1 — Automated checks

```
deck_check project=<name>
```

Reports:
- **Overflow**: text or elements extending beyond the 1280×720 slide bounds
- **OOB elements**: positioned elements outside the viewport
- **Missing content**: empty slide bodies

Fix every reported issue before proceeding.

### Step 2 — Screenshot all slides

```
deck_screenshot project=<name>
```

Review the PNG screenshots. Call `view_image` (or `browser_view_file`) on each to visually inspect.

### Step 3 — Content review checklist

For each slide, verify:

**Structure**
- [ ] Slide has exactly one clear heading / focal point
- [ ] No more than 6 bullet points per slide
- [ ] Body text ≥ 1rem (16px) — readable in a room
- [ ] No orphaned single words on a line (widow/orphan control)

**Consistency**
- [ ] All headings use the same font and colour (`var(--color-primary)`)
- [ ] Spacing is consistent (same padding across slides of the same type)
- [ ] Theme colours only — no inline `#hex` values that differ from the theme

**Content**
- [ ] No placeholder text (TBD, TODO, Lorem ipsum, "[insert here]")
- [ ] All statistics/claims are sourced or marked as estimates
- [ ] Acronyms are defined on first use
- [ ] CTA or key takeaway is explicit (especially on closing slides)

**Images**
- [ ] All images have `alt` attributes
- [ ] No copyrighted images (use `image_search` results which are royalty-free)
- [ ] Images are sized correctly — not stretched or pixelated

### Step 4 — Accessibility quick check

- [ ] Colour contrast sufficient (primary text on bg at least 4.5:1)
- [ ] No information conveyed by colour alone
- [ ] Headings in logical order (h1 → h2 → h3)

### Step 5 — Final sign-off

If all checks pass:
```
deck_build_pptx project=<name>
```

---

## Document QA Workflow

### Step 1 — View the document

```
document_tool action=view project=<name> filename=<name>.html
```

### Step 2 — Content review checklist

**Structure**
- [ ] Cover/title page with author, date, version
- [ ] Table of contents present for documents > 5 pages
- [ ] Every section heading has substantive content beneath it
- [ ] Logical flow: each section sets up the next

**Writing quality**
- [ ] Executive Summary is self-contained (someone can stop reading after it)
- [ ] Sentences average < 25 words
- [ ] Active voice preferred; passive is fine for methodology sections
- [ ] No unexplained jargon or acronyms

**Formatting**
- [ ] Consistent heading hierarchy (h1 → h2 → h3 — never skip levels)
- [ ] Tables have header rows with `<th>` elements
- [ ] Code blocks use `<pre><code>` (required for clean DOCX rendering)
- [ ] No broken links or placeholder href="#"

**DOCX-specific** (if exporting to `.docx`)
- [ ] No `display:flex` or `position:absolute` in inline styles
- [ ] No CSS pseudo-elements (::before, ::after) in inline styles
- [ ] Images are absolute URLs or base64 `data:` URIs

### Step 3 — Export when clean

```
document_tool action=convert project=<name> filename=<name>.html format=pdf
```

---

## Common issues and fixes

### Overflow in deck_check

Cause: Element with fixed width/height that's too large for the slide.

Fix options:
- Reduce `font-size`
- Add `overflow:hidden` to the containing `div`
- Break content across two slides

### Slide looks correct in screenshot but PPTX has layout issues

Cause: `position:relative/absolute` stacking context not honoured by dom-to-pptx.

Fix: Use flex layout for slide positioning, not absolute positioning.
Reserve `position:absolute` only for decorative overlay elements.

### DOCX has missing images

Cause: Relative image paths (e.g. `./image.png`) are not resolved in DOCX export.

Fix: Use absolute URLs (`https://...`) or convert images to base64 `data:` URIs.
