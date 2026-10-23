# Instant Mechanic: AI car diagnosis platform

## Product
AI car diagnosis chatbot and mechanic assistance platform for Instant Mechanic (instantmechanic.online), a car care company in Delhi NCR, India. Users pick their car, describe a problem, answer one follow-up question at a time, and get ranked likely causes, steps, repair advice, costs and an option to request a mechanic.

## Architecture
- apps/web: Next.js (App Router) + TypeScript + Tailwind + shadcn/ui (customer site)
- apps/admin: Next.js admin app (from Phase 4)
- backend: FastAPI + SQLAlchemy 2 + Alembic + Pydantic v2, Python managed with uv
- backend/engine: diagnosis engine as plain Python with no web framework imports
- PostgreSQL 16 with pgvector, run with docker compose
- data/raw: original datasets, never modified. data/schema: canonical schema, manifest.yaml, taxonomy.yaml. data/eval: golden test cases.

## Datasets
18 Excel files in data/raw/, profiled in docs/dataset-profile.md (read it before touching data code):
- 972 fault rows, 41 categories. Every file's first sheet uses the same 34-column template (EV file has 8 extra columns). The header is on row 1, 3 or 4 and names vary slightly, so map columns by alias.
- Each row = one fault: ID'S, CATEGORY, SUB-CATEGORY, DESCRIPTION, CUSTOMER ON AI (Hinglish phrases), symptoms, causes, diagnosis, likely fault, resolution, road-repairable (Yes/Limited/No), repair location, advice, safety, towing conditions, mechanic task, mechanic repair steps, costs for Budget / Mid-range / Premium car segments, repair time, minimum cost, internal notes, pictures, CUSTOMER PROBLEM IN STAGES (question flow as text).
- Split mixed files by the CATEGORY column (file 9 by ID prefix AP / NS).
- IDs clash across files (ST in files 3, 7, 13; SU in 14 and 17): the unique key is file number + original ID, e.g. F03-ST-01.
- Extra sheets in files 9, 12, 14, 18 (and some others): AI_DIAGNOSIS_RULES, SAFETY_AND_TOWING_RULES, PARTS_PRICE_SOURCES, LABOUR_PRICE_RESEARCH, PARTS_IMAGE_INDEX, QUALITY_AUDIT, CATEGORY_CROSS_REFERENCES, plus waterlogging, accident and towing-charge sheets in file 18.
Categories are grouped into user-facing problem tiles in data/schema/taxonomy.yaml. Each category has a kind: diagnose, fast_track (roadside help) or inspect. Question flows are structured offline from the stages text and must be human-approved before use.

## Non-negotiable rules
- Facts (part compatibility, prices, labour rates, safety rules) come only from the database. Never let an LLM invent them.
- Every diagnosis result shows a coverage level: part_fit_verified, segment_estimate or general_guidance.
- Costs come from the car's price segment (budget below 10 lakh, mid 10-25 lakh, premium above 25 lakh), shown with their approx label and check date.
- MECHANIC TASK, HOW TO REPAIR BY MECHANIC and SUGGESTIONS-AARAV are internal: never show them to customers.
- Safety red-flag rules must always run and must never be skipped by any fallback.
- Every result shows a disclaimer that it is an estimate and not a replacement for a professional inspection.
- Collect personal data only with explicit consent and store the consent record.

## How to work in this repo
1. Before changing anything, inspect the project: read this file, the README, docs/, the relevant code and the existing tests. Then tell me your plan in a short list and wait if anything is unclear.
2. Preserve all working functionality. Do not rename, move or delete things outside the task's scope.
3. Implement only the requested scope. List other improvements you notice as follow-ups instead of doing them.
4. Add or update tests for every change. Run the whole test suite (backend and frontend) and fix failures you caused.
5. Keep migrations in Alembic. Never edit an applied migration; add a new one.
6. Keep secrets in .env files. Update .env.example when adding a variable.
7. At the end, report: what changed (files), test results, and the exact commands to run and try the feature.

## Design
White and orange theme matching instantmechanic.online. Brand orange #F07A2A for accents only; CTA fill #D9620F with white bold text 18px+; orange text #B4500D; ink #15120F; warm white #FFF6EE; danger #C62828 (safety only). Very heavy black display headings, rounded pill buttons, mobile first, WCAG 2.2 AA.
