# Updating the frozen guidance index

The operator UI does **not** crawl GOV.UK. It classifies snapshots produced by Guidance Discovery. Add a new snapshot when orgs/types change or the current one is too old. **Never overwrite a sibling** — `$GRF_CORPUS` is a library.

The catalog lists:

- the root itself if it has `with_body.json` + `MANIFEST.json` (legacy flat layout)
- each immediate child directory with the same pair (skip `stem_index/`, `embed_index/`)

Identity is `MANIFEST.with_body_sha256`. The wizard select and each job pin that sha.

## Checklist

1. From the repo root:

   ```bash
   cd guidance-discovery
   uv sync
   ./run.sh
   ```

   Stage 2 is restartable. Do not start from scratch unless `ORGANISATIONS` / `DOCUMENT_TYPES` in `src/filters.py` changed.

2. Inspect `guidance-discovery/output/funnel.json`:
   - `fetch_failed` and `body_empty` should not be huge.
   - Failed fetches are invisible to the relevance filter (missing/empty body).

3. Copy into a **new** dated-sha subdirectory of the webapp corpus library (`GRF_CORPUS`, default `guidance-relevance-web/data/corpus/`):

   ```bash
   python - << PY
   import hashlib, json
   from datetime import date
   from pathlib import Path
   import shutil

   src = Path("output/with_body.json")
   data = src.read_bytes()
   digest = hashlib.sha256(data).hexdigest()
   built = date.today().isoformat()
   dest = Path("../guidance-relevance-web/data/corpus") / f"{built}-{digest[:8]}"
   dest.mkdir(parents=True)
   shutil.copy2(src, dest / "with_body.json")
   shutil.copy2("output/funnel.json", dest / "funnel.json")
   pages = json.loads(data)
   orgs = sorted({
       slug
       for p in pages
       for slug in [
           (p.get("meta_data") or {}).get("primary_publishing_organisation") or "",
           *((p.get("meta_data") or {}).get("organisations") or []),
       ]
       if slug
   }, key=str.lower)
   types = sorted({
       (p.get("meta_data") or {}).get("document_type") or ""
       for p in pages
   } - {""}, key=str.lower)
   (dest / "MANIFEST.json").write_text(json.dumps({
       "built_on": built,
       "n_pages": len(pages),
       "with_body_sha256": digest,
       "discovery_git_sha": None,
       "organisations": orgs,
       "document_types": types,
   }, indent=2) + "\n")
   print(dest)
   PY
   ```

   Convention is `$GRF_CORPUS/<built_on>-<sha8>/`. The directory name is a label; the sha in `MANIFEST.json` is the id. `organisations` / `document_types` are the unique publishers and content-store types on that snapshot (wizard checkboxes). Put them in MANIFEST — the wizard will not scan `with_body.json` to fill them. See [MANIFEST.example.json](../data/corpus/MANIFEST.example.json).

4. Restart the webapp so the catalog re-lists. The header should show `N snapshots · newest …`. The new date appears in the **Guidance index** select (newest is default). The first preview of that snapshot streams the JSON, Porter-stems every page once, and writes `stem_index/<with_body_sha256>.sqlite` next to it. Later previews and CLI jobs reuse that file (lexicon-term lookups, not a RAM pickle). Delete that snapshot’s `stem_index/` to force a rebuild. Leftover `*.pkl` files are unused.

5. Smoke: open the UI, pick the new snapshot, load the **slurry** template, Preview. You should see a `would_route` well under the default cap of 650 (historical slurry runs were ~544 lexicon hits; a broader farm/animal lexicon on the 27k index was ~596). A second Preview with the same lexicon should return immediately (“Reused the previous wordsearch…”). Preview again with organisation `environment-agency` — `would_route` should drop vs the unfiltered slurry run. `defra` is not a GOV.UK org slug and should warn + route nothing.

Do not commit `with_body.json` (gitignored). Keep `MANIFEST.json` only if it points at a file that actually exists on that machine.

## Staleness

GRF classifies snapshot bodies. Guidance Proposition Extractor **re-fetches** live gov.uk. Pages born after the snapshot never appear; taken-down pages can still be labelled then fail later.
