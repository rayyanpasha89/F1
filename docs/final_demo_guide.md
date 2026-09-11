# F1 Race Strategist final demonstration guide

This guide demonstrates the deployed application and the evidence behind it. The live system is historical: its archive ends in 2024, and it does not contain weather, tyres, telemetry, betting, or a live race feed.

## Verified release

- Live application: https://f1-strategist-demo.ys85rp5g9ncdj.eu-north-1.cs.amazonlightsail.com/
- GitHub repository: https://github.com/rayyanpasha89/F1
- Deployed application commit: `7738da72311a390509d92377ef11b24d8e95a0e1`
- GitHub Actions: https://github.com/rayyanpasha89/F1/actions/runs/34599337165
- CodeBuild: `f1-race-strategist-dev:a1c49bad-70f5-4a74-a080-8ec21fdee065` (`SUCCEEDED`)
- Lightsail: service `f1-strategist-demo`, deployment 17, `RUNNING` / `ACTIVE`
- Region and account: `eu-north-1`, F1 account `148356747273`

The demo access code is stored outside Git in `outputs/chat-access-code.txt` in the Codex workspace. Do not put it in slides, screenshots, terminal history, or the repository.

## Recommended 10–12 minute walkthrough

### 1. Establish the real product and data boundary

Open the live root URL. Select season **2024**.

Show:

- final recorded driver and constructor standings;
- season navigation and race calendar;
- that the archive covers 1950–2024 and the UI labels it as historical.

Say: “The source package was audited before product work. The database contains 701,433 rows across 14 related tables. The frontend reads the FastAPI/PostgreSQL application; it does not use fixture results.”

### 2. Open a race weekend

Open Monaco 2024 directly at `/races/1128` or choose it from the calendar.

Show:

- race and circuit details;
- qualifying, starting grid, recorded result, and pit summary;
- driver comparison and strictly earlier recent form;
- all 20 podium probabilities.

Select **Charles Leclerc** in the prediction panel. Expected live result: **73.9%** projected podium probability versus a **70.8%** projected grid-only baseline. The raw selected-model output remains visible as **76.4%**. Point out the real calibrated SHAP contributions and the note that they are associations in calibrated log-odds, not causal effects. All 20 projected probabilities total three podium places.

Use **Build outcome map** in the **Podium Outcome Lab**. Show that all **1,140** unordered three-driver sets are included in the solution, while the interface ranks the leading 12. Expected Monaco results include:

- Carlos Sainz + Charles Leclerc + Oscar Piastri at **13.6%**;
- Charles Leclerc + Lando Norris + Oscar Piastri at **11.1%**;
- Max Verstappen + Charles Leclerc + Oscar Piastri at **10.6%**;
- Charles Leclerc + Oscar Piastri as the leading co-podium pair at **39.7%**;
- **79.9%** cumulative mass across the 12 shown sets;
- maximum marginal reconstruction error of about **1.94e-15**.

Explain that maximum entropy supplies the least-assumptive coherent distribution that preserves every released driver probability and exactly three places. It uses no race outcome and fits no new model. The three drivers within each set are unordered; this is not a learned interaction model or a validated finishing-order forecast.

Use the **Grid swap lab** below the forecast. Exchange two starters and show the full comparison: actual and scenario grid positions, exact transformed model inputs, released and scenario probabilities, rank movement, and the starting-grid SHAP change. Both probability columns total three. Explain that this is a controlled frozen-model sensitivity check; all other pre-race inputs stay fixed, and the result is not a causal estimate or future-race validation. Pit-lane grid `0` is shown separately from its fixed model proxy input `25`.

### 3. Demonstrate typo-tolerant grounded statistics

Open **Ask the archive**, enter the external access code, and submit:

> How many race wins does Lewis Hamliton have in the archive?

Expected evidence:

- the UI visibly corrects `Hamliton` to `Hamilton`;
- the answer is **105**;
- the generated read-only SQL is visible;
- the answer trace routes to **Statistics**;
- the selected entity is **Lewis Hamilton only**;
- selected tables are `drivers`, `races`, and `results`;
- there is one executed SQL attempt, zero repairs, and two provider calls in the verified cloud run.

Expand **How this answer was built**. Explain that spelling repair, database-backed entity reranking, and relationship-aware schema selection occur before bounded SQL generation. The database result, rather than the language model, supplies the statistic.

### 4. Demonstrate structured follow-up context

Submit:

> How many did he win in 2020?

Expected answer: **11**. The trace should retain Lewis Hamilton through a compact prior turn. The browser sends at most three structured turns containing questions, intent, entities, and race ID; it does not resend previous answers, SQL rows, provider payloads, or the access code.

### 5. Demonstrate conservative ambiguity handling

Clear the conversation, then submit:

> How many wins did Schumacher have?

Expected result: clarification among **Michael Schumacher**, **Mick Schumacher**, and **Ralf Schumacher**. The verified cloud response uses zero provider calls and executes no SQL.

### 6. Demonstrate grounded refusal

Submit:

> Who performs best at Monaco in wet wether?

Expected result: a refusal explaining that the supplied archive lacks reliable weather data. The verified cloud response uses zero provider calls and executes no SQL. This is the deliberate hallucination test from the approved scope.

### 7. Demonstrate model explanation routing

Return to Monaco 2024 and ask:

> Why is Lewis Hamliton given that podium probability?

Expected result: the typo is corrected, the request routes to **Explanation**, and the response cites Lewis Hamilton's actual **2.6%** projected selected-race output, the **12.8%** projected grid-only baseline, the visible **2.9%** raw model output, and real model contributions. It does not generate a substitute probability with the language model.

### 8. Close with engineering evidence

Open the live Model Lab and GitHub Actions run. The protected final presentation remains unchanged until an explicit presentation revision is requested. Show:

- 185 Python tests in the complete local artifact/source-backed suite, plus all four opt-in PostgreSQL integration checks;
- 22 frontend tests, ESLint, Prettier, and Vite production build;
- all 77,349 podium sets across 68 supported races reconstructed with maximum driver error `3.82e-13`;
- Ruff and both Terraform roots;
- fixed NL2SQL Run 09: 40/40, 3.651-second mean latency;
- Agentic Run 01: 22/22, 3.013-second mean latency, 29 provider calls, zero live repair;
- immutable CodeBuild image and active Lightsail deployment 17;
- 355 bounded runtime events exported and read back from CloudWatch, including prediction, scenario, review, and chat completion records with no configured credential, database-URL, SQL, or question-text matches; the final deployment window has zero traceback or error-level records;
- live Monaco Lighthouse scores of 100 for performance, accessibility, best practices, and SEO at desktop and mobile sizes, with zero total blocking time.

State that both benchmark suites were used during development and therefore do not estimate unseen generalization. The bounded one-repair path is covered by deterministic tests; no generated query in the reported live runs needed repair.

## Evidence map

| Evidence | Location |
|---|---|
| Final presentation | `docs/presentations/F1_Race_Strategist_Final_Review.pptx` |
| Architecture | `docs/architecture.md` |
| Adversarial review | `docs/adversarial_review.md` |
| Engineering history | `docs/worklog.md` |
| Deployment and cost notes | `docs/deployment.md` |
| AI assistance disclosure | `AI_ASSISTANCE.md` |
| Local agentic verification | `reports/agentic_local_verification.json` |
| AWS release | `reports/aws_agentic_release.json` |
| Public cloud verification | `reports/aws_agentic_cloud_verification.json` |
| Model-accountability local verification | `reports/model_accountability_local_verification.json` |
| Model-accountability public release | `reports/model_accountability_aws_release_final.json` |
| Model-accountability combined cloud verification | `reports/model_accountability_cloud_verification.json` |
| Grid Scenario local verification | `reports/grid_scenario_local_verification.json` |
| Grid Scenario public release | `reports/grid_scenario_aws_release_v17.json` |
| Grid Scenario combined cloud verification | `reports/grid_scenario_cloud_verification.json` |
| Podium Outcome numerical evaluation | `reports/podium_outcome_local_evaluation.json` |
| Podium Outcome local public contract | `reports/podium_outcome_local_release.json` |
| Fixed NL2SQL result | `reports/nl2sql_run_09.json` |
| Agentic result | `reports/agentic_run_01.json` |
| Screenshots | `docs/presentations/assets/` |

## Questions a reviewer may ask

**Are the 105 wins or 76.4% hard-coded?**

No. The wins answer comes from executed SQL against the archive. The probability comes from the frozen calibrated model artifact using the recorded pre-race grid and leakage-safe historical features.

**Could the query mutate the database?**

Generated SQL passes SQLGlot policy checks, row and time bounds, and a separate SELECT-only PostgreSQL role. Integration tests prove `DELETE` and `CREATE` are denied at the database level, and production startup rejects writable chat credentials.

**Does the model leak the race result?**

Features are emitted before same-date history is updated. Training is 2010–2018, selection is 2019–2021, and the final test is 2022–2024. Explicit tests cover same-race, future, and teammate leakage.

**Does the grid swap predict what would really happen after a penalty?**

No. It changes two model grid inputs while holding the remaining recorded pre-race features fixed. It demonstrates how the frozen model responds; it does not model causal race dynamics, strategy changes, or an alternate historical outcome.

**Did the model learn the probability of each three-driver podium set?**

No. The fitted model emits individual driver marginals. The outcome map derives the maximum-entropy distribution over unordered three-driver sets that exactly preserves those marginals. It is coherent under that stated assumption, but it does not learn driver dependence or predict first, second, and third order.

**Did the final model improve everything?**

No. It improved log loss, Brier score, and ROC-AUC versus the grid-only baseline; top-three hit rate was slightly lower. The repository reports that limitation directly.

**What remains operationally limited?**

The access code is shared demo protection rather than per-user identity. In-process limits reset on restart. The archive ends in 2024. Earlier ALB and supporting resources from the first AWS attempt remain billable because no deletion was authorized. The Lightsail baseline is about $30/month plus Bedrock and incidental logging/storage.
