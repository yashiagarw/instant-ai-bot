# backend/engine

The diagnosis engine, as a plain Python package. Empty until task 1.5.

Rules:

- No web framework imports (no FastAPI, Starlette, or anything from `app`). The API calls the engine; the engine never calls the API. `tests/test_engine_package.py` enforces this.
- Facts (prices, part fit, safety rules) come in as data from the database layer. The engine never invents them.
- Safety rules run on every answer and are never skipped by any fallback.
- Every result carries an engine version, a coverage level (`part_fit_verified`, `segment_estimate`, `general_guidance`) and the estimate disclaimer.

Planned shape (task 1.5): input = vehicle, chosen tile or emergency topic, free text, answers so far; output = coverage level, ranked faults with evidence, next question or done, safety alerts, roadside verdict, segment cost range and repair time.
