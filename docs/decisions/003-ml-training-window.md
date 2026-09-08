# ADR 003 — Features and training window

Accepted 2026-09-08. Historical feature warmup starts in 1990 to avoid shared-drive grain ambiguity; model training starts in 2010. Every selected modern driver/race row is unique and this is asserted. Recent driver rates/average classification use the previous five appearances; team strength uses mean per-driver podium rate in each of its previous five races. Team updates are grouped after date-level feature emission, so the second teammate cannot see the first teammate's current outcome.

Career and driver/circuit podium rates use fixed smoothing priors (1.5 successes in 10 pseudo-races, and 0.45 in 3). Missing debut history uses fixed podium 0.15, finish 12 and nonfinish 0.2. None are calculated from final-test data. Nonfinish is operationally status other than Finished or +N laps; this includes some non-mechanical statuses and should not be described as mechanical failure probability. Recent finishing position is prior classification order, including retirements.

Compared 2010–2018 and 2014–2018 fit windows on 2019–2021 validation. The longer window won for both tested full logistic and boosting models; retain 2010–2018. This is a small prespecified search, not an exhaustive optimization. Validation uncertainty is not quantified. The 2022 regulation era remains final-test evaluation, not a tuning set.
