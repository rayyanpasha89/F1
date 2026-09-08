# F1 Race Strategist

Academic race intelligence project in development. The first implemented milestone is a reproducible audit of the supplied 14-table Formula 1 snapshot, covering 1950–2024. No deployed application or model is claimed yet.

## Reproduce the current milestone

Use Python 3.11. Create a virtual environment and install `pip install -r requirements.lock`. Place the supplied CSV files in `dataset/` (not redistributed; see `docs/implementation_assessment.md`). Run:

```sh
python -m scripts.audit_data
pytest -q
ruff check scripts tests
```

Inspect `reports/data_audit.json` and `docs/data_audit.md`. Source fingerprints are in the JSON report. Scope and phased decisions are in `docs/implementation_assessment.md`; actual work is recorded in `docs/worklog.md`. See `AI_ASSISTANCE.md` for disclosure.
