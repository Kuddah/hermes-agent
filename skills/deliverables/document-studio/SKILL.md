---
name: document-studio
description: >
  Produce polished long-form documents — research reports, PRDs, proposals,
  whitepapers, SOPs, memos, and briefs — as HTML-first, then export to PDF,
  DOCX, Markdown, or TXT. Use when the user needs a multi-page written
  deliverable (anything beyond a quick text answer). The HTML source is always
  the canonical artifact; exports are generated from it.
version: 1.0.0
metadata:
  hermes:
    tags: [document, pdf, docx, report, proposal, prd, whitepaper, sop, deliverables]
    required_toolsets: [document, file]
    optional_toolsets: [web, memory, image_gen]
    related_skills: [deck-studio, visual-qa, research]
---

# Document Studio

Create, iterate, and export professional multi-page documents.

## Core principle

**HTML is the source of truth.** Always author in HTML; convert only when the
user requests a specific format. This lets you iterate on content and layout
without losing fidelity across formats.

---

## Workflow

```
SCOPE → OUTLINE → DRAFT (HTML) → ITERATE → EXPORT
```

### Step 1 — Scope

Clarify (or infer from context):

- **Document type** — report / PRD / proposal / whitepaper / SOP / memo / brief
- **Audience** — internal / external / technical / executive
- **Length** — one-pager / short (2-5p) / long (5-20p) / comprehensive (20p+)
- **Export format(s)** — PDF, DOCX, Markdown, or TXT
- **Project name** — used as the `mnt/<project>/documents/` sandbox

### Step 2 — Outline

Before writing, present a structured outline as a bullet list. Wait for user
approval or adjustments before drafting the full document.

### Step 3 — Draft in HTML

```
document_tool action=create project=<name> filename=<name>.html
```

Use semantic HTML. Guidelines:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <style>
    body { font-family: 'Georgia', serif; max-width: 900px; margin: auto;
           padding: 48px 64px; color: #1a1a1a; line-height: 1.7; }
    h1   { font-size: 2rem; font-weight: 700; border-bottom: 3px solid #0056b3;
           padding-bottom: 8px; margin-bottom: 24px; }
    h2   { font-size: 1.4rem; font-weight: 600; margin-top: 2rem; }
    h3   { font-size: 1.1rem; font-weight: 600; }
    table { border-collapse: collapse; width: 100%; margin: 1.5rem 0; }
    th, td { border: 1px solid #d0d0d0; padding: 8px 12px; text-align: left; }
    th { background: #f0f4f8; font-weight: 600; }
    blockquote { border-left: 4px solid #0056b3; padding-left: 16px; color: #555; }
    code { background: #f4f4f4; padding: 2px 6px; border-radius: 3px; }
    pre  { background: #f4f4f4; padding: 1rem; overflow-x: auto; }
    .cover { text-align: center; padding: 80px 0 60px; }
    .meta  { font-size: 0.9rem; color: #666; margin-top: 8px; }
    .page-break { page-break-before: always; }
  </style>
</head>
<body>
  <!-- document content -->
</body>
</html>
```

### Step 4 — Iterate

- Use `document_tool action=view` to inspect the current state.
- Use `document_tool action=create` to overwrite with an updated version.
- Use `document_tool action=restore` to roll back to any auto-snapshot.

### Step 5 — Export

```
document_tool action=convert project=<name> filename=<name>.html format=pdf
document_tool action=convert project=<name> filename=<name>.html format=docx
document_tool action=convert project=<name> filename=<name>.html format=md
```

---

## Document type patterns

### Research Report

Structure:
1. **Executive Summary** (150-250 words, stand-alone)
2. **Introduction** — context and objectives
3. **Methodology** — sources, scope, analytical approach
4. **Findings** — grouped by theme; use tables/charts
5. **Discussion** — implications, limitations
6. **Recommendations** — numbered, actionable
7. **Appendices** — raw data, citations

### Product Requirements Document (PRD)

Structure:
1. **Overview** — problem statement, success metrics
2. **Personas** — user archetypes with needs/pain points
3. **User Stories** — as `As a <role>, I want <action>, so that <value>`
4. **Functional Requirements** — numbered, "The system MUST…"
5. **Non-Functional Requirements** — performance, security, accessibility
6. **Out of Scope** — explicit boundaries
7. **Open Questions** — tracked issues + owners
8. **Appendices** — wireframe descriptions, API contracts

### Proposal / Business Case

Structure:
1. **Executive Summary**
2. **Problem / Opportunity**
3. **Proposed Solution**
4. **Benefits & ROI**
5. **Risks & Mitigations**
6. **Timeline & Milestones**
7. **Budget & Resources**
8. **Appendices**

### Standard Operating Procedure (SOP)

Structure:
1. **Purpose & Scope**
2. **Roles & Responsibilities** (RACI table)
3. **Prerequisites / Materials**
4. **Procedure Steps** — numbered, each step one action
5. **Quality Checks** — expected outputs per checkpoint
6. **Exception Handling**
7. **References & Related Documents**

---

## Quality checklist (before export)

- [ ] Cover/title section present with author, date, version
- [ ] No orphaned headings (every h2 has content)
- [ ] All tables have a `<th>` header row
- [ ] No placeholder text (Lorem ipsum, TBD, TODO)
- [ ] Executive summary is stand-alone readable
- [ ] Code blocks use `<pre><code>` for correct DOCX/PDF rendering
- [ ] Internal links removed (unsupported in DOCX export)
- [ ] Images are hosted URLs or base64 `data:` URIs (not relative paths)

---

## Tips

- **Long documents**: break into multiple `<section>` blocks with `class="page-break"` for clean PDF pagination.
- **Tables with many columns**: use `font-size: 0.85rem` inside `<table>` to prevent overflow in DOCX.
- **DOCX limitations**: avoid `display:flex`, `position:absolute`, and pseudo-elements; stick to block/table layout.
- **When the user says "send" or "share"**: export to PDF first — it's the most portable format.
