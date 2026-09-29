# Guidance Relevance Filter — operator UI

Wizard + job runner around the existing [`guidance-relevance-filter`](../guidance-relevance-filter/) CLI. Wordsearch only. New runs pick **batch** (0.5×, default) or **synchronous** (full-price Messages API) in the wizard. Not a pipeline stage.

## Run

```bash
cd guidance-relevance-web
uv sync
export ANTHROPIC_API_KEY=sk-...
export GRF_CORPUS=data/corpus          # library of snapshots (see docs/updating-the-corpus.md)
export GRF_JOBS=data/jobs
# optional
export GRF_MAX_ROUTED=650
export GRF_DAILY_MAX_ROUTED=2000
# GRF_LLM_MODE=sync          # fallback for jobs without meta.llm_mode; UI is the control for new runs
# GRF_SYNC_CONCURRENCY=10
export GRF_PUBLIC_BASE_URL=http://127.0.0.1:8000
export MAIL_FROM=noreply@example.gov.uk
export MAIL_URL=smtp://localhost:1025   # unset = write jobs/<id>/mail.log

uv run guidance-relevance-web
# → http://127.0.0.1:8000  (binds GRF_HOST, default 127.0.0.1)
```

Put one or more frozen Guidance Discovery snapshots in `$GRF_CORPUS` first (legacy flat `with_body.json` at the root, and/or `<built_on>-<sha8>/` children). See [docs/updating-the-corpus.md](docs/updating-the-corpus.md).

## Docker

Image binds `0.0.0.0:8000`. Corpus and jobs stay on the host. One replica only (in-process worker).

```bash
cd guidance-relevance-web
cp .env.example .env   # ANTHROPIC_API_KEY; set GRF_PUBLIC_BASE_URL to the public URL
docker compose up --build
# → http://127.0.0.1:8000
```

`GRF_CORPUS` / `GRF_JOBS` inside the container are `/data/corpus` and `/data/jobs` (compose bind-mounts `./data/...`). First preview of a snapshot writes `stem_index/` next to that snapshot.

## What it does

1. Author full category files (`name`, `description`, `exclusion_criteria`, optional hints, lexicon). Pick a **Guidance index** snapshot. Optional ticked **organisations** (publishers on the selected snapshot) and **document types** (content-store types on that snapshot) slice it **before** wordsearch. Empty field / none ticked = that axis unconstrained. Both set → AND. Type `defra` in the org filter to find `department-for-environment-food-rural-affairs`.
2. **Preview** queries a disk-backed inverted stem index — no Anthropic. First preview of a snapshot streams `with_body.json`, Porter-stems it, and writes `stem_index/<sha256>.sqlite`. Later previews are lexicon term lookups (and identical lexicon + corpus + scope hashes skip the gate entirely). The preview (and the submitted job) pin `corpus_sha256`.
3. If `would_route ≤ GRF_MAX_ROUTED` and the daily routed budget allows, **submit** a job. The wizard radio chooses batch (Anthropic Message Batches, 0.5×) or synchronous (Messages API, 1×). Default is batch.
4. A single worker process runs GRF on the pinned snapshot’s `with_body.json`, or on `jobs/<id>/corpus.json` when either scope filter is set, always passing `--stem-index` at the snapshot sqlite so the CLI does not re-stem:

   ```bash
   python -m guidance_relevance_filter run \
     $GRF_CORPUS/<snapshot>/with_body.json \   # or jobs/<id>/corpus.json
     jobs/<id>/output \
     --categories jobs/<id>/categories.json \
     --lexicon jobs/<id>/lexicon.json \
     --max-routed $GRF_MAX_ROUTED \
     --stem-index $GRF_CORPUS/<snapshot>/stem_index/<sha>.sqlite
     # plus --sync --concurrency $GRF_SYNC_CONCURRENCY when the job is sync
   ```

5. On boot and every `GRF_SWEEP_SECONDS` (default 120), incomplete jobs with a live `checkpoint.json` are reattached (same CLI, same output dir).
6. Email once when the job is `done` / `failed` / `blocked_cap`. Address lives in `meta.json` only, never in the zip.
7. Download the GRF run zip, or a kept/dropped `.xlsx`. Upload the edited workbook to write `pages.json` for Guidance Proposition Extractor.

## Job layout

```text
$GRF_JOBS/jobs/<uuid>/
  categories.json
  lexicon.json
  organisations.json   # [] if unrestricted
  document_types.json  # [] if unrestricted
  scope.json           # preview org/type miss counts for the job funnel (when filtered)
  corpus.json          # sliced pages; only when a filter is set
  meta.json            # includes email + llm_mode + corpus_sha256 / built_on / n_pages
  status.json
  run.log
  output/              # GRF output_dir
  pages.json           # after xlsx upload
```

## Caps

- Per run: cheap-gate `n_routed` (default 650). Preview does not debit the daily counter.
- Per UTC day: sum of `would_route` for jobs the worker actually starts (default 2000).
