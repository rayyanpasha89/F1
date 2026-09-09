# F1 Race Strategist: interim presentation guide

Use the PowerPoint for a 10–12 minute progress review, followed by a 4–5 minute demonstration. The slides contain speaker notes explaining the evidence and caveats. Status snapshot: 9 September 2026. Public AWS deployment is still undergoing provisioning and verification.

## Tabs to open before presenting

1. Local app: http://127.0.0.1:5173/
2. Monaco 2024: http://127.0.0.1:5173/races/1128
3. Repository: https://github.com/rayyanpasha89/F1
4. Commit history: https://github.com/rayyanpasha89/F1/commits/main/
5. Passing CI run: https://github.com/rayyanpasha89/F1/actions/runs/34343384677
6. Experiments: https://github.com/rayyanpasha89/F1/blob/main/EXPERIMENTS.md
7. Evaluation: https://github.com/rayyanpasha89/F1/blob/main/docs/evaluation.md
8. Worklog: https://github.com/rayyanpasha89/F1/blob/main/docs/worklog.md

Do not open `.env`, the chat access-code file, AWS secret values or Terraform state during screen sharing.

## Start the local application if needed

From `/Users/rayyan/Downloads/F1_Project`, use two terminals:

```sh
# Terminal 1
.venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

```sh
# Terminal 2
npm run dev --prefix frontend
```

If a port is already occupied by this project's server, use the running app. Do not start duplicate servers. The source, ingested database, models and private Bedrock configuration are already available locally. A fresh clone needs the exact supplied CSV package and the README training steps.

## What to demonstrate and say

| Step | Open or click | What to explain |
|---|---|---|
| 1 | Local homepage, season 2024 | “The dashboard reads the audited relational dataset. These are historical recorded standings.” |
| 2 | Monaco race weekend | Switch Results, Grid, Qualifying and Pit Stops. Explain different table meanings and incomplete historical timing coverage. |
| 3 | Charles Leclerc link | Show season results and career statistics, then return to Monaco. |
| 4 | Podium probabilities | Select Leclerc. Show 76.4% model probability and 70.9% grid baseline. Explain the actual SHAP factors and pre-race history. |
| 5 | Ask the strategist | Ask: **Who won the most races for Red Bull?** Expected snapshot result: Max Verstappen, 63. Expand **Inspect generated SQL**. Generated wording and aliases may vary. |
| 6 | Chat on the Monaco page | Ask: **Who is most likely to finish on the podium and why?** Explain that this route calls the frozen ML model. |
| 7 | Chat | Ask: **Who performs best at Monaco in wet races?** Show the refusal because reliable weather labels are absent. |
| 8 | Git commit history | Show audit, schema, API, model, chat, security corrections and infrastructure milestones. Explain that failures and corrective commits remain visible. |
| 9 | GitHub Actions | Show green Python, frontend and infrastructure jobs. State that CI covers a smaller scope than local integration with private data/model artifacts. |
| 10 | EXPERIMENTS and evaluation | Show baseline versus selected model. Explicitly acknowledge the slight decline in top-three hit rate. |

Keep chat requests spaced out. The demo has six requests/minute per client and a daily per-process cap. An access code is required if configured. If a live LLM call fails, explain the error and use the actual screenshots and saved benchmark report as evidence. Do not represent a saved screenshot as a fresh call.

## Slide-by-slide speaking cues

1. Introduce the project and call this an interim review.
2. Explain completed local work versus deployment still in progress. Avoid an invented completion percentage.
3. State the measured dataset size and coverage gaps.
4. Explain how database facts, model probabilities and LLM interpretation remain distinct.
5. Show the dashboard screenshot, then the corresponding local page if time allows.
6. Explain the race and profile navigation.
7. Describe one prediction and its real model factors.
8. Explain chronological training, validation and final testing. Mention retrospective grid provenance.
9. Compare probability scores honestly. Top-three selection did not improve.
10. Show executed SQL and unsupported-data refusal.
11. Explain the fixed benchmark, preserved failures and reused-suite limitation.
12. Show real Git history and the worklog.
13. Show passing CI and distinguish its scope from full local tests.
14. Explain AWS restrictions and the authorized Lightsail alternative. Do not claim the site is live until cloud verification succeeds.
15. Run the short demo and state remaining cloud verification/documentation work.

## Likely faculty questions

**How do you prevent leakage?** Features for a race use previous history. Tests mutate same-race/future/teammate outcomes and check invariance. Parameters use only the training and selection windows. The historical source may contain corrected grid values, which remains a provenance limitation.

**Is the LLM predicting the podium?** No. The frozen sklearn model produces probabilities. SHAP explains that model. Bedrock routes the user's request and generates SQL for statistics.

**Did the model beat the baseline?** It improved log loss, Brier score and AUC on 2022–2024. Top-three hit rate was slightly lower, so the project does not claim every metric improved.

**Does 40/40 mean perfect chat?** No. This fixed suite was reused during development. It checks row values, not row ordering, and structural join checks are limited proxies. All earlier failed runs remain available.

**Can the reviewer reproduce it?** Dependency locks, source checksums, scripts, tests and four executed notebooks are in the repo. A fresh clone requires the exact supplied CSV package and regenerated trusted model artifacts.

**What did AI assist with?** Codex assisted implementation, testing and documentation. The project discloses this in AI_ASSISTANCE.md. Evidence comes from executed code and observed outputs. The implementing agent's review is not independent faculty review.
