---
name: kanban-deliverables-orchestrator
description: >
  Plan, set up, and monitor a multi-agent deliverables production pipeline backed
  by Hermes Kanban. Use when the user needs a polished deliverable — report, PRD,
  proposal, whitepaper, pitch deck, or combined document + slides — and the work
  warrants decomposition into specialized roles (researcher, writer, deck
  designer, editorial). Performs adaptive scoping, designs the team, generates
  the setup script that creates Hermes profiles + initial kanban tasks, then
  helps monitor execution and intervene when tasks stall.
version: 1.0.0
metadata:
  hermes:
    tags: [deliverables, kanban, multi-agent, orchestration, document, slides, report, pitch-deck]
    required_toolsets: [kanban, file, memory]
    optional_toolsets: [document, deck, web]
    related_skills: [document-studio, deck-studio, visual-qa, kanban-video-orchestrator]
    worker_configs:
      - worker-configs/researcher-worker.yaml
      - worker-configs/writer-worker.yaml
      - worker-configs/deck-worker.yaml
      - worker-configs/editorial-worker.yaml
---

# Kanban Deliverables Orchestrator

Decompose any multi-piece deliverable project into kanban tasks executed by
specialized Hermes worker profiles.

This skill does **not** write documents or slides itself. It is a meta-pipeline that:

1. **Scopes** the request through targeted discovery
2. **Designs** the team (which workers, what tasks)
3. **Generates** a setup script that creates profiles, workspace, and kanban tasks
4. **Monitors** execution and intervenes when tasks stall or fail

---

## When NOT to use this skill

- The deliverable is a single document or deck — just use `document-studio` or `deck-studio` directly.
- The user wants a quick one-shot conversion (e.g. "export this to PDF") — use `document_tool` directly.
- The work fits one specialist cleanly.

---

## Workflow

```
DISCOVER → BRIEF → TEAM DESIGN → SETUP → EXECUTE → MONITOR
```

### Step 1 — Discover

Ask only what's necessary. Start with:

1. **What is the deliverable?** (report, PRD, pitch deck, combo?)
2. **Who is the audience?** (internal / external / investors / technical)
3. **What format(s)?** (PDF, DOCX, PPTX, or combination)
4. **What's the deadline?** (helps scope the depth of research)
5. **Is there existing content** (brief, notes, data) I should start from?

### Step 2 — Brief

Produce a `brief.md` with:

```markdown
# Deliverable Brief

## Objective
One-sentence description of the deliverable and its purpose.

## Audience
Who will read/see this? What do they already know?

## Deliverables
- [ ] Document: <type> (<format>, <length>)
- [ ] Slides: <type> (<N> slides, PPTX)

## Key Messages
Top 3-5 points the deliverable must communicate.

## Content Sources
Existing materials, URLs to research, data files.

## Quality Bar
What "done" looks like (tone, style, brand, accuracy).

## Deadline
When is this needed?
```

Show the brief and get user confirmation before proceeding.

### Step 3 — Team Design

Design the minimum team for the project:

| Role | Worker Config | Responsibilities |
|---|---|---|
| Researcher | `researcher-worker.yaml` | Web research, source gathering |
| Writer | `writer-worker.yaml` | Document drafting + export |
| Deck Designer | `deck-worker.yaml` | Slide creation + PPTX export |
| Editorial | `editorial-worker.yaml` | QA review + final corrections |

For simple projects (no research needed, single format), skip the researcher.
For document-only projects, skip the deck designer.

### Step 4 — Generate Setup Script

Produce a shell script `setup-deliverables.sh` in the project workspace:

```bash
#!/usr/bin/env bash
# Deliverables pipeline setup for: <project name>
set -euo pipefail

PROJECT="<project-slug>"
WORKSPACE="mnt/${PROJECT}"
mkdir -p "${WORKSPACE}"/{research,documents,presentations,qa}

# ── Create Hermes profiles ────────────────────────────────────────────────────

hermes profile create researcher \
  --config worker-configs/researcher-worker.yaml \
  --workspace "dir:${WORKSPACE}"

hermes profile create writer \
  --config worker-configs/writer-worker.yaml \
  --workspace "dir:${WORKSPACE}"

hermes profile create deck-designer \
  --config worker-configs/deck-worker.yaml \
  --workspace "dir:${WORKSPACE}"

hermes profile create editorial \
  --config worker-configs/editorial-worker.yaml \
  --workspace "dir:${WORKSPACE}"

# ── Create initial kanban task ────────────────────────────────────────────────

hermes kanban create \
  --title "Research: <topic>" \
  --assigned researcher \
  --description "$(cat brief.md)" \
  --workspace "dir:${WORKSPACE}"

echo ""
echo "✓ Pipeline ready. Start the researcher profile:"
echo "  hermes --profile researcher"
```

Tailor the script to the actual project (tasks, profiles needed, workspace path).

### Step 5 — Task Graph

Define the full task graph before running. Each kanban task should have:

- `title`: Short action-oriented label
- `assignee`: Which worker profile handles it
- `depends_on`: Tasks that must complete first
- `description`: Full brief for the worker (what to produce, where to save it)

**Example task graph for a report + deck:**

```
[1] Research: <topic>          → researcher
       ↓
[2] Draft: <report name>.html  → writer   (reads research brief)
       ↓
[3] Export PDF + DOCX          → writer   (after draft approved)
       ↓
[4] Build: <deck name> slides  → deck-designer (reads report draft)
       ↓
[5] QA: final review           → editorial (all deliverables)
```

Create tasks 1 and 4 in parallel if research and slide content are independent.

### Step 6 — Monitor

After handing off, periodically run:

```
kanban_show
```

**Intervention triggers:**

| Signal | Action |
|---|---|
| Task `blocked` for > 30 min | Read the blocker note; reassign or provide missing input |
| Task `in_progress` > 2h | Take a progress snapshot; check if the worker is stuck in a loop |
| `deck_check` errors persisting | Directly fix the slides via `deck_modify_slide` |
| Document quality issues | Provide specific correction instructions via kanban comment |

---

## Common patterns

### Report only (no slides)

Team: researcher + writer + editorial  
Tasks: research → draft → export → QA

### Pitch deck only (no document)

Team: researcher (optional) + deck-designer + editorial  
Tasks: research (optional) → deck build → QA

### Full deliverable package (report + deck)

Team: all four workers  
Tasks: research → draft → export → deck build → QA  
(Research and deck design can run in parallel once the brief is confirmed)

---

## Workspace layout

```
mnt/<project>/
  brief.md                    — project brief (created by orchestrator)
  research/                   — researcher output
    <topic>.md
  documents/                  — writer output
    <name>.html               — canonical source
    <name>.pdf
    <name>.docx
  presentations/              — deck-designer output
    slide_00_title.html
    slide_01_...html
    ...
    _theme.css
    <name>.pptx
  qa-report.md                — editorial output
```

---

## Tips

- **Always confirm the brief** before generating the setup script.
- **Keep worker tasks atomic** — one clear output per task.
- **Prefer parallel where possible** — research and deck scaffolding can often run simultaneously.
- **Editorial is not optional** — quality checks before delivery prevent revision loops.
- **Save the task graph** to `mnt/<project>/TASKS.md` for reference during monitoring.
