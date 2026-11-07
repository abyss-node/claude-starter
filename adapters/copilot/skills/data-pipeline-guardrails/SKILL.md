---
name: data-pipeline-guardrails
description: >-
  Use when writing or changing a job that loads data into a database, warehouse,
  file or SaaS destination and may be re-run: ETL/ELT, sync/import scripts,
  scrapers that save results, dbt/Airflow/Dagster tasks. Not for one-off
  analysis or reading config.
---

# Data Pipeline Guardrails

Checks to run *while* building data jobs. The failure mode this exists to catch:
a job that works on today's clean sample, then silently corrupts the store when
it's re-run, when a column changes, or when bad rows arrive — and nobody notices
until a dashboard is wrong weeks later.

Default to the simplest design that works (see the Complexity budget section in AGENTS.md, if you have one):
correctness under reruns and dirty data is needed on day one; distributed engines and streaming are not.

## Checks by activity

### Ingestion / reading source data
- Validate the schema at the boundary. Tolerate additive nullable columns; fail
  loudly on missing, renamed or retyped required columns (a rename looks like a
  drop plus an add).
- Quarantine bad records in a reject table rather than failing on one malformed
  row — but count them, and fail the batch if the reject rate passes a threshold.
- Don't trust source types: numbers as strings, mixed date formats, encoding.
  Coerce and validate explicitly.

### Scrapers and third-party sources
- A 200 is not success. Verify it's the page you asked for (detect block,
  captcha and login pages) — and that the detector doesn't reject real pages.
- Pagination truncates silently. Check an expected count or a last-page signal.
- Treat a zero-row run as a failure until shown otherwise.
- Cache raw responses so re-parsing doesn't re-fetch. Respect rate limits and
  robots.txt.
- Never invent identifiers (slugs, IDs, URLs) you haven't verified exist.

### Idempotency & reruns (the one people skip)
- Every job must be safely re-runnable and produce the same result. Use
  upsert/merge on a key, or overwrite by partition — never blind append, which
  double-counts on the inevitable rerun.
- Use the run's logical date / data interval, never wall-clock `now()` or
  `CURRENT_DATE` — a backfill of last Tuesday must process last Tuesday.
- Dedupe source keys within the batch before a MERGE or upsert. For keys already
  in the target, duplicates make it error (Postgres, BigQuery, Snowflake by
  default) or pick a row arbitrarily. For new keys, every duplicate is inserted,
  silently in warehouses that don't enforce primary keys.
- Upsert does not propagate deletes. If the source deletes, handle it.
- Incremental high-water marks: be explicit about `>` vs `>=`, and overlap the
  window so rows sharing the boundary timestamp aren't lost; the upsert absorbs
  the repeats.
- Publish atomically (load to staging, then swap) so readers never see half a
  load.
- No side effects (counters, notifications) that fire again on retry.
- Backfilling a past date range is a parameter, not a code change.

### Late data & transforms
- Event time is not processing time; "today's data" doesn't all arrive today.
  Make aggregations correctable rather than assuming first-run completeness.
- Document the grain (one row per what?) and nullability — grain bugs are the
  most common and most silent.
- Test on edge data (empty, null, duplicate, boundary), not just a clean sample.

### Data quality — fail loud ★
- Check freshness (is the data recent?), volume (row-count anomalies vs
  history), nulls in required fields, duplicates on keys, and referential
  integrity.
- Alert on the *pipeline* when these fail — before bad data reaches consumers.
  Discovering corruption from a wrong dashboard is the failure this prevents.

### Storage, orchestration & PII
- In a warehouse (BigQuery/Snowflake): partition on a low-cardinality, commonly
  filtered column (usually date); cluster on high-cardinality ones. Don't
  partition small OLTP tables.
- Model real dependencies as a DAG, not timing luck; retry with backoff; no
  silent partial success where half the DAG ran.
- Mask PII and keep it out of intermediate copies you can't later delete from.

## Before you call it done
- **Run the job twice** and confirm identical output.
- Feed it **malformed, empty, and late** input; confirm it degrades gracefully.
- Confirm the **backfill path** works for a past date range.
- Confirm quality checks fire and make failure visible: non-zero exit, alert, or
  a message you'll actually see.
- Run against a local/dev target; ask before touching a shared database or
  spending money.
- Anything you could not actually run goes under Unverified in your report —
  never claim a check you didn't perform.
