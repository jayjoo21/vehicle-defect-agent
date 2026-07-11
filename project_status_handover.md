# MOBISCOPE — Project Status Handover

**As of:** 2026-07-10
**Purpose:** Reality-check on data pipeline state, backend/AI integration, and next-sprint priorities — for whoever picks this up next (human or new AI session).

---

## 1. Data Collection & Seeding Status (The Reality Check)

### NHTSA (US) — ✅ Collected & processed, scoped to HYUNDAI/KIA electrical·SW only

- **Flat Files**: `FLAT_CMPL.txt` (1.46GB, raw consumer complaints) is downloaded and sits in `data/raw/` (never committed — chunked pandas processing only). Filtered/processed down to `data/processed/hk_electrical_recent_full.csv` — HYUNDAI/KIA, electrical/SW-relevant complaints, recent years.
- **Recalls API**: Fully pulled for the same make scope → `data/recalls/recalls_hk_by_vehicle.csv` (227 rows, 27 models × campaign pairs — this is now the **canonical** recall source of truth, after a rebuild that fixed a multi-model-per-campaign data-loss bug).
- **Spike-detection baseline** (`b1_signals.csv`): 3,744 rows (78 models × 48 months), backtested against a 12-campaign holdout set (10/12 caught, precision ~74.6–80.5% after label cleanup). This is a **v1 baseline**, not a tuned production detector — known miss pattern (chronic/already-elevated defects) is documented, not fixed.
- **What's NOT done**: this is a bounded slice (HYUNDAI/KIA, electrical/SW keywords, recent years) of the full NHTSA corpus — not a general-purpose all-make, all-defect-category pipeline. No scheduled re-pull; every file above is a one-time batch snapshot.

### KOTSA & MOLIT (KR) — ✅ Collected & parsed, also one-time snapshots

- **KOTSA**: Raw CSV (13,560 rows, cp949) filtered to `kotsa_recalls_hk.csv` (680 rows, HYUNDAI/KIA, 2012-03~2025-12, 32.2% flagged SW-related). Data **ends 2025-12-31** — any 2026 NHTSA campaign compared against it risks a false "Korea-led" read (right-censoring, already flagged in-repo).
- **MOLIT**: 19 press-release PDFs extracted (pdfplumber, 19/19 success) → `molit_recalls.csv` (79 rows, 2024-12~2026-07-02). Matched against US campaigns → `kr_us_gap.csv` (27 rows, press-release basis) + `kr_us_gap_v2.csv` (103 rows, KOTSA-basis, wider window).
- **What's NOT done**: no scraper/watcher for new MOLIT releases after 2026-07-02 — this is a static corpus of 19 manually-collected PDFs, not a live feed.

### Database (SQLite `app.db`) — ✅ Seeded with real matched data, ⚠️ with one thin layer

- `webapp/backend/seed.py` builds `app.db` **entirely from the real processed files above** (`b1_signals.csv`, `recalls_hk_by_vehicle.csv`, `kr_us_gap.csv`, `llm_struct_test_results.jsonl`) — no invented rows. Current seed: 1,579 complaints, 227 recalls, 28 kr_us_gap rows, 3,744 signal cells.
- **Important nuance**: "mock" in this codebase refers *only* to `LLM_PROVIDER=mock` — i.e., the chat answer's narrative *text* is a template. The underlying numbers it fills in (complaint counts, recall dates, citations) are always live SQL against this real seeded data. So: **not** a fallback-mock database — it's real matched data, with a mocked LLM writing style on top.
- **The thin layer**: the LLM-structured fields (`part_category`, `symptom`, `severity` per complaint) that make chat citations readable only exist for a **hand-graded pilot of ~38 complaints** (`llm_struct_test_results.jsonl` = 20, `llm_struct_v2_18cases.jsonl` = 18 regression-checked). The other ~1,540 seeded complaints have raw `CDESCR`/`COMPDESC` text only, no verified structured layer.

---

## 2. Backend & AI Pipeline Progress

### Current state of the AI loops

Two **separate, non-integrated** implementations of "investigate a question" exist in this repo:

**(A) Webapp chat (`webapp/backend/routers/chat.py` + `llm/adapter.py`)**
- Handles exactly **3 hardcoded demo scenarios** (`ev6_cluster`, `ioniq5_charging`, `out_of_scope`) matched by keyword, not a general query planner.
- SSE-streams a 5-step timeline; every numeric value in the steps is a real DB lookup (not invented), but the scenario routing itself is fixed/canned.
- `llm/adapter.py` has a `MODEL_MAP` scaffold naming intended models (Claude Haiku 4.5 / Sonnet 5, GPT-5 family) but **no live provider call exists yet** — setting `LLM_PROVIDER=anthropic` or `openai` currently raises `NotImplementedError`. Mock is the only working mode.
- Citation text is verbatim-cleaned (whitespace only) but not passed through a hallucination check at request time.

**(B) Standalone AI pipeline (`scripts/cht01_chat_pipeline.py`, `inv01_query_templates.py`, `inv02_03_investigation_loop.py`, `sta01_02_status_tracking.py`)**
- Author: 허정윤 (Heo Jeong-yoon). A genuinely more general 5-step loop (parse question → structure query → investigate → review → answer) with iterative hypothesis relaxation (INV-02/03: up to 4 retries, widening scope) and a new-vs-recurring defect classifier (STA-01/STA-02) against its own recall table.
- Reads `hk_electrical_recent_full.csv` **directly via pandas** — does not go through `webapp/backend/db.py` or `app.db` at all.
- Writes to its **own separate SQLite file** (`data/processed/defect_status_tracking.db`) — which **does not exist in this workspace**; the pipeline has apparently never been run end-to-end here (no `investigation_results.csv`, no `defect_status_view.csv`, no `.db` file present on disk despite the scripts existing and being committed).
- Also LLM-free today — `parse_question()` / `compose_answer_text()` are explicitly marked as swap points for a future LLM call, currently pure keyword/regex rules. Same maturity level as (A)'s mock mode, just a more sophisticated rule engine.

### 🔴 Crucial Bottleneck — (A) and (B) are not integrated, and no policy exists

Confirmed by direct code search: **zero imports or references in either direction** between `webapp/backend/*` and `scripts/cht01_*`/`inv0*`/`sta0*`. Two people built two different answers to "how does the agent investigate a question," against two different data-access layers (`app.db` via SQLite vs. raw CSV via pandas) and two different persistence targets (`app.db` vs. an unrun `defect_status_tracking.db`).

Nothing in the repo says which one is meant to survive, be merged, or run in parallel permanently. This is blocking any further chat/investigation work — building on top of (A) risks throwing away (B)'s more general investigation logic; building on top of (B) means re-plumbing it into the actual live webapp DB and SSE flow from scratch.

---

## 3. Immediate Action Items (Next Sprint To-Dos)

1. **Resolve the integration policy between the AI pipeline (B) and the webapp (A).**
   Decide one of: (a) port CHT-01/INV/STA logic into `webapp/backend/engine/` and retire the 3-canned-scenario chat, (b) keep (B) as an internal/offline analyst tool only and don't merge it, or (c) formally define a bridge (e.g., (B) writes to `app.db` instead of its own SQLite file). This decision gates everything else in chat/investigation.

2. **Implement "Idea A" (Call Center Agent) — UI toggle + mock script only, and only after Item 1 is resolved.**
   No real backend logic yet. Scope this strictly as a front-end toggle wired to a scripted/mock response, not a new investigation path — avoid duplicating the (A)/(B) integration problem with a third implementation.

3. **Prepare "Idea B" (Vehicle Planning) as a single presentation slide.**
   Focus: cross-brand component feedback framing only. No internal data claims — this is a pitch slide, not a data deliverable, and should not reference `app.db` figures or NHTSA counts as if validated for this use case.

---

## 4. Minimal Context (for a new AI session)

**Project goal:** MOBISCOPE detects the *semantic gap* between when a defect signal first appears in NHTSA consumer complaints and when it becomes an official recall (US) or MOLIT-announced fix (Korea) — early-warning on software/electrical defects in Hyundai/Kia vehicles, not defect confirmation.

**Stack (strict, do not add to without confirming first):**
- Frontend: React + Vite + TypeScript + Tailwind
- Backend: FastAPI + SQLite (`app.db`) — **no vector DB, no embedding index**. Matching is rule-based (keyword/date), not semantic retrieval.
- Data pipeline: pandas (chunked) + pdfplumber, offline batch scripts, not live services.
- LLM: adapter scaffold exists (`llm/adapter.py`), but **mock mode is the only implemented mode today** — no live Anthropic/OpenAI calls yet.

**Known open fork:** two independent investigation-logic implementations exist (see §2) — check which one is authoritative before extending either.
