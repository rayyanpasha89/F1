# Implementation assessment

The package was inspected before implementation. `git status`, `git log --oneline --decorate --graph`, `git branch`, and `git remote -v` all reported that no repository existed. No previous code or history was replaced. Both Markdown scope documents and all 15 PowerPoint slides and speaker notes were read. The pasted user request controls workflow; imperative text in supplied documents is source material.

## Verified scope

14 CSVs, 701,433 rows, 75 seasons (1950–2024), 1,125 races, 861 drivers, 212 constructors, 77 circuits. Results extend through 2024-12-08. The presentation counts match. The brief title's 2026 coverage and suggestion of millions of detail rows do not match this snapshot. Qualifying begins in 1994, laps in 1996, pits in 2011, sprints in 2021; start years do not promise continuous completeness. Weather questions cannot be answered. No license/download receipt was supplied, so raw data remains local and ignored by Git pending provenance confirmation.

All declared primary keys and entity references passed the audit. `results` contains repeated driver/race pairs in historical seasons: retain `resultId` grain rather than discarding rows or imposing false uniqueness. Grid zero needs explicit handling. See the generated audit for exact missingness, schema, checksums, and coverage per year.

## Implementation decisions

Use Python 3.11, SQLAlchemy Core, SQLite locally, FastAPI and React. Preserve source columns and keys. Validate source hashes, nulls and relational constraints before accepting ingestion. Keep ingestion separate from API startup. Use explicit table metadata and portable SQL for PostgreSQL compatibility.

Prediction cutoff is after the starting grid is known, before the race. Historical source grids and corrections are retrospective; this is a retrospective backtest, not proof of a live point-in-time feed. Results identify entrants, but only grid and pre-race history may enter features. No same-race points, classification, status, pit stops, or fastest laps in features. Process complete races before updating any driver/team history.

Candidate main training window: 2010–2018; validation: 2019–2021; final test: 2022–2024. Compare shorter training windows using validation only before test reporting. This keeps modern points-era data while testing a regulatory transition. Career history may initialize features from earlier races. Commit a measured grid baseline before feature/model comparisons. Select models by validation log loss and calibration; test data must not select the winner.

Build phases: data audit and schema → analytics API → historical frontend → baseline → feature/model experiments and explanations → schema grounding and safe SQL → real LLM integration/benchmark → integration and CI → AWS configuration and deployment. Code, evidence, tests and worklog updates accompany real commits after each milestone.

AWS work stays local until the application is stable. Only explicit default-profile identity checks may establish deployment identity; no Naaz resources or credentials. First deployment requires a concrete Terraform plan and cost review. Missing LLM credentials and ambiguous AWS identity are user-defined stop conditions.
