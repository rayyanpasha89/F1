# F1 terms grounded in this snapshot

Podium means classified position 1, 2 or 3 in results; sprint podiums must be explicitly requested from sprint_results. A constructor is the recorded team entity, not a guaranteed continuous corporate identity across renames. Grid zero denotes pit-lane/unknown/nonstandard starts, not pole. position_order ranks every classified result including nonfinishers; position_text preserves status notation. Operational nonfinish features use status other than Finished or +N laps and are not pure mechanical failure rates.

Standings are post-race cumulative snapshots. Use the last available snapshot of the requested season for championship standings; never sum standings points across races. Race-points sums exclude sprint points, deductions and historic scoring rules and cannot substitute for championship totals. Historical shared-drive records mean result_id is the universal result grain; race_id + driver_id is not universally unique.

Lap and pit-stop coverage starts later and varies. Missing records are missing data, not proof of no pit stop. Pit-stop elapsed duration includes transit and interruptions, not necessarily stationary service time. Qualifying Q3 NULL usually means no Q3 time, not zero seconds. Time strings represent different concepts; prefer milliseconds for duration arithmetic.

The archive is 1950–2024. “Last ten years” is ambiguous without an anchor; ask for clarification or explicitly anchor to the dataset's latest season (2015–2024). Weather, tyres, fuel, telemetry, injuries, live schedules and betting odds are absent. Do not invent proxies. Predictions are provided by the frozen ML model only for 2022–2024. SHAP explains model association in calibrated log-odds, not causality.
