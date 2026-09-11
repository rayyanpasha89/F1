"""Evaluate the derived podium-set distribution across every supported stored race."""

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from backend.database import make_engine
from backend.ml.outcomes import PodiumOutcomeService
from backend.ml.predictor import Predictor, PredictionUnavailable


SCHEMA_VERSION = "f1-podium-outcome-evaluation-v1"


def evaluate_podium_outcomes(predictor, output):
    """Write append-only aggregate evidence without persisting driver-level forecasts."""

    output = Path(output)
    if output.exists():
        raise FileExistsError(output)

    supported = predictor.frame().loc[
        lambda frame: frame.year.between(2022, 2024), ["race_id", "year"]
    ]
    race_rows = supported.drop_duplicates().sort_values(["year", "race_id"])
    if race_rows.empty:
        raise PredictionUnavailable("No supported races are available for outcome evaluation.")

    service = PodiumOutcomeService(predictor)
    driver_counts = []
    combination_counts = []
    distribution_sum_errors = []
    reconstructed_sum_errors = []
    marginal_errors = []
    entropies = []
    effective_counts = []
    durations = []
    model_versions = set()

    evaluation_started = perf_counter()
    for row in race_rows.itertuples(index=False):
        race_started = perf_counter()
        result = service.derive(int(row.race_id), limit=3)
        durations.append((perf_counter() - race_started) * 1000)
        diagnostics = result.diagnostics
        driver_counts.append(diagnostics.driver_count)
        combination_counts.append(diagnostics.combination_count)
        distribution_sum_errors.append(abs(diagnostics.probability_sum - 1))
        reconstructed_sum_errors.append(abs(diagnostics.reconstructed_marginal_sum - 3))
        marginal_errors.append(diagnostics.maximum_marginal_error)
        entropies.append(diagnostics.entropy_bits)
        effective_counts.append(diagnostics.effective_outcome_count)
        model_versions.add(result.model_version)

    if len(model_versions) != 1:
        raise PredictionUnavailable("Outcome evaluation encountered inconsistent model versions.")

    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "passed",
        "model_version": model_versions.pop(),
        "support": {
            "years": [int(race_rows.year.min()), int(race_rows.year.max())],
            "race_count": len(race_rows),
            "driver_rows": sum(driver_counts),
        },
        "distribution": {
            "method": "maximum_entropy_fixed_size",
            "podium_size": 3,
            "complete_outcome_count": sum(combination_counts),
            "combination_count_range": [min(combination_counts), max(combination_counts)],
            "entropy_bits_range": [min(entropies), max(entropies)],
            "effective_outcome_count_range": [min(effective_counts), max(effective_counts)],
        },
        "integrity": {
            "maximum_distribution_sum_error": max(distribution_sum_errors),
            "maximum_reconstructed_sum_error": max(reconstructed_sum_errors),
            "maximum_marginal_error": max(marginal_errors),
            "all_races_converged": True,
        },
        "timing_ms": {
            "total": round((perf_counter() - evaluation_started) * 1000, 3),
            "mean_per_race": round(math.fsum(durations) / len(durations), 3),
            "maximum_race": round(max(durations), 3),
        },
        "evidence_boundary": {
            "source": "released frozen-model marginals",
            "outcome_data_used": False,
            "separately_trained_joint_model": False,
            "joint_forecast_validated": False,
            "ordering": "unordered_podium_set",
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    engine = make_engine()
    try:
        report = evaluate_podium_outcomes(Predictor(engine), args.output)
    except FileExistsError:
        print(json.dumps({"status": "failed", "error_code": "output_exists"}), file=sys.stderr)
        return 1
    except PredictionUnavailable:
        print(
            json.dumps({"status": "failed", "error_code": "outcome_evaluation_unavailable"}),
            file=sys.stderr,
        )
        return 1
    finally:
        engine.dispose()
    print(
        json.dumps(
            {
                "status": report["status"],
                "schema_version": report["schema_version"],
                "output": str(args.output),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
