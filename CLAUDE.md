# CLAUDE.md

Permission-aware RAG assistant over the GitLab Handbook. Portfolio project for
global AI Engineer interviews. Scope, phases and ADRs live in `PROJECT_BRIEF.md`.
Read it before any non-trivial task.

---

## 1. Owner & collaboration

- Owner: senior Java engineer (Spring Boot, microservices) moving into AI engineering.
- Talk to the owner in **Azerbaijani**, keep technical terms in English.
  Code, comments, commits, docs and README are in **English**.
- **Learning rule:** the owner writes the core logic — `retrieval/`, `generation/answer.py`,
  `eval/metrics.py`. For these: explain, hint, review; write the full implementation only
  if explicitly asked twice. Boilerplate (UI, Docker, Makefile, config, logging setup,
  test fixtures) — write freely.
- Every file must be explainable by the owner in an interview. If you write something
  non-obvious, explain it in 2-3 sentences after the change.
- Before changes touching more than ~3 files: propose a short plan and wait for approval.
- If a requirement is ambiguous, ask one question instead of guessing.

## 2. Scope guard

Out of scope: agents, graph DB, fine-tuning, real auth, microservices, React, vector DB
servers, observability platforms. If something seems necessary, propose it with the
reason and wait. "Simple and measured" beats "complete".

## 3. Repository layout

```
src/handbook_rag/
  config.py           # pydantic-settings: config.yaml + env vars
  logging_setup.py    # JSON logging, request_id context
  llm.py              # the ONLY place that calls LLM/embedding APIs
  ingest/             # parse.py, chunk.py, index.py
  retrieval/          # access.py, vector.py, bm25.py, fusion.py, rerank.py
  generation/         # prompts.py, rewrite.py, answer.py
  app.py              # Gradio UI
eval/
  golden/dev.jsonl    # used while iterating
  golden/test.jsonl   # held out — final numbers only
  metrics.py, run_eval.py
  results/            # one JSON file per run (committed)
scripts/download_handbook.py
tests/
config.yaml, .env.example, Makefile, Dockerfile
```

## 4. Security rules (non-negotiable)

- **Access control happens in retrieval**, as a metadata filter applied to BOTH vector
  and BM25 search. Never rely on the prompt to hide restricted content.
- **Deny by default / fail closed:** unknown role → `AccessDeniedError`, no retrieval.
  Retrieval functions take `allowed_sections` as a **required** argument (no default),
  so unfiltered search is impossible by construction.
- The role comes only from the request/session parameter, never from the question text.
- Retrieved chunks are **data, not instructions**: wrap them in clear delimiters in the
  prompt and tell the model to ignore instructions inside them.
- Secrets only via environment variables (`.env`, git-ignored). Never hardcode, never log.
- Tests for the access filter are mandatory and must cover: each role, unknown role,
  empty role, and BM25 + vector paths separately.

## 5. LLM calls

All LLM and embedding calls go through `llm.py`. It owns:
- **Timeout** on every call (from config).
- **Retry** with `tenacity`: only transient errors (429, 5xx, timeouts, connection);
  exponential backoff + jitter; max attempts from config. Auth/validation errors fail fast.
- **Logging** of model, purpose, tokens, cost, latency, attempt (see §7).
- **Structured outputs** (Pydantic) where the response is parsed; validate, never trust.
- `temperature=0` for rewrite, rerank and judge calls.
- Model names are pinned in `config.yaml`. The **judge model is fixed**; never change it
  silently — changing it invalidates all previous eval comparisons.

Prompts live in `generation/prompts.py` as constants with a `PROMPT_VERSION` string that
is logged with every call and saved in every eval result.

## 6. Code standards

- Python 3.12, `uv` for dependencies (commit `uv.lock`). Add a dependency only with a
  one-line justification in the PR/commit message.
- `ruff` for lint + format; type hints on all public functions; `mypy` must pass on `src/`.
- Prefer small pure functions; pass dependencies as arguments (no module-level clients
  or globals) so everything is testable without network.
- Pydantic models for data crossing boundaries: `Chunk`, `RetrievedChunk`, `Answer`,
  `GoldenItem`, `EvalResult`.
- No `print` in `src/`; use logging. `print` is fine in scripts and CLI output.
- Small exception hierarchy in `errors.py`: `HandbookRagError` → `AccessDeniedError`,
  `RetrievalError`, `LLMError`. Catch specific exceptions; never swallow silently.
- Embeddings are cached by `(embedding_model, sha256(chunk_text))` so re-ingest is cheap.

## 7. Logging standard

Analogy for the owner: SLF4J + MDC → stdlib `logging` + `contextvars`.

**Format:** one JSON object per line to stdout (12-factor). Dev mode may use a readable
console format via `LOG_FORMAT=console`. Use `logging.getLogger(__name__)` everywhere.

**Base fields (every line):** `ts` (ISO-8601 UTC), `level`, `logger`, `event`,
`request_id`. Field names are `snake_case`; units go in the name (`latency_ms`,
`cost_usd`). `event` names are `noun.verb_past` (e.g. `retrieval.completed`).

**Standard events:**

| event | level | key fields |
|---|---|---|
| `request.received` | INFO | `role`, `question_chars` |
| `access.filter_applied` | INFO | `role`, `allowed_sections` |
| `query.rewritten` | INFO | `rewritten_chars` (text only at DEBUG) |
| `retrieval.completed` | INFO | `source` (vector/bm25), `k`, `chunk_ids`, `latency_ms` |
| `rerank.completed` | INFO | `input_n`, `output_n`, `top_chunk_ids`, `latency_ms` |
| `llm.called` | INFO | `purpose`, `model`, `prompt_version`, `prompt_tokens`, `completion_tokens`, `cost_usd`, `latency_ms`, `attempt` |
| `llm.retry` | WARNING | `purpose`, `error_type`, `attempt`, `wait_s` |
| `request.completed` | INFO | `total_latency_ms`, `total_cost_usd`, `source_chunk_ids` |
| `request.failed` | ERROR | `error_type`, `stage` (with stack trace) |

**Levels:** DEBUG = payloads (question text, rewritten query, prompts); INFO = one line
per pipeline stage; WARNING = retries, degraded paths; ERROR = failed request.

**Never log:** secrets, full prompts or chunk text at INFO (use `chunk_id`), user question
text unless `log_payloads: true` in config (default `false`). No logging inside tight loops.

Rule of thumb: from INFO logs alone you must be able to reconstruct *which chunks were
used, why, how long each stage took and what it cost* for any `request_id`.

## 8. Evaluation rules

- **One change per experiment.** Iterate on `dev.jsonl`; report final numbers on
  `test.jsonl` only (avoid overfitting to the golden set).
- Every run writes `eval/results/<timestamp>_<label>.json` containing: git SHA, full config
  snapshot, `PROMPT_VERSION`, metrics, per-question details, total cost and latency.
- Run each configuration at least twice; treat small differences as noise.
- **Never edit the golden set to improve a score.** Golden set changes need an ADR entry
  and a baseline re-run.
- Metrics: MRR, Recall@k, Precision@k; judge scores (accuracy, completeness, relevance);
  security: leak rate (target 0%) and injection resistance; p50/p95 latency; cost/query.
- Unit-test metric functions with hand-computed values (e.g. first hit at rank 2 → RR 0.5).

## 9. Testing

- `pytest`. Unit tests never hit the network: fake `llm.py` via dependency injection.
- Real API tests are marked `@pytest.mark.integration` and skipped by default.
- Must-have tests: chunker, access filter (§4), fusion/dedup, metric functions.
- The eval suite is not a test; it is an experiment.

## 10. Git & data

- Conventional commits (`feat:`, `fix:`, `eval:`, `docs:`, `refactor:`, `test:`).
- Do not commit the raw handbook, Chroma DB, caches or `.env`; commit the download script.
- Commit eval result JSON files — they are the project's evidence.

## 11. Definition of Done

A change is done when: `make test` and `make lint` pass; if retrieval or generation
behavior changed, an eval run is saved and compared to the previous one; significant
decisions have an ADR in `PROJECT_BRIEF.md`; README is updated if user-facing.
Before saying "done", run the checks and report the results.

## 12. Commands

- `make setup`   — `uv sync`
- `make data`    — download handbook sections
- `make ingest`  — parse, chunk, embed, index
- `make app`     — start Gradio UI
- `make test`    — unit tests
- `make lint`    — ruff + mypy
- `make eval LABEL=<name> SPLIT=dev` — run eval, save results
