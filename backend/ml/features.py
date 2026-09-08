"""Explicitly allowlisted pre-race inputs. Outcomes are separate evaluation columns."""

import pandas as pd
from sqlalchemy import text


def source_frame(engine):
    with engine.connect() as conn:
        return pd.read_sql(
            text("""SELECT x.result_id, x.race_id, x.driver_id, x.constructor_id,
            x.grid, x.position, x.position_order, x.points, r.year, r.round, r.date, r.circuit_id,
            s.status AS status_name FROM results x JOIN races r USING(race_id)
            JOIN status s USING(status_id) ORDER BY r.date, x.result_id"""),
            conn,
        )


def baseline_frame(source):
    frame = (
        source.copy()
        .sort_values(["date", "race_id", "driver_id", "result_id"])
        .reset_index(drop=True)
    )
    frame["podium"] = frame["position"].isin([1, 2, 3]).astype(int)
    # A fixed value outside a modern starting grid; do not learn a fill value from test data.
    frame["grid_position"] = frame["grid"].where(frame["grid"].gt(0), 25).astype(float)
    return frame


def split_masks(frame, train_start=2010):
    return {
        "train": frame.year.between(train_start, 2018),
        "validation": frame.year.between(2019, 2021),
        "test": frame.year.between(2022, 2024),
    }


FEATURE_SETS = {
    "grid": ["grid_position"],
    "driver": [
        "grid_position",
        "driver_recent_podium",
        "driver_recent_finish",
        "driver_recent_dnf",
    ],
    "team": [
        "grid_position",
        "driver_recent_podium",
        "driver_recent_finish",
        "driver_recent_dnf",
        "constructor_recent_podium",
    ],
    "full": [
        "grid_position",
        "driver_recent_podium",
        "driver_recent_finish",
        "driver_recent_dnf",
        "constructor_recent_podium",
        "driver_circuit_podium",
        "driver_career_podium",
    ],
    "career": ["grid_position", "driver_career_podium"],
}


def build_features(source):
    """Read past history, emit all same-date inputs, THEN update histories.

    Outcome columns remain present only for scoring. Model callers must select a
    named feature set. History warmup starts 1990; no shared-drive grain in this era.
    """
    from collections import defaultdict
    import numpy as np

    frame = baseline_frame(source.loc[source.year >= 1990])
    if frame.duplicated(["race_id", "driver_id"]).any():
        raise ValueError("Modern driver/race input must be unique")
    drivers, constructors, circuits = defaultdict(list), defaultdict(list), defaultdict(list)
    output = []
    for date, daily in frame.groupby("date", sort=True):
        for row in daily.to_dict("records"):
            dh = drivers[row["driver_id"]]
            ch = constructors[row["constructor_id"]]
            circuit = circuits[(row["driver_id"], row["circuit_id"])]
            recent = dh[-5:]
            row.update(
                {
                    "driver_recent_podium": float(np.mean([v[0] for v in recent]))
                    if recent
                    else 0.15,
                    "driver_recent_finish": float(np.mean([v[1] for v in recent]))
                    if recent
                    else 12,
                    "driver_recent_dnf": float(np.mean([v[2] for v in recent])) if recent else 0.2,
                    "constructor_recent_podium": float(np.mean(ch[-5:])) if ch else 0.15,
                    "driver_career_podium": (sum(v[0] for v in dh) + 1.5) / (len(dh) + 10),
                    "driver_circuit_podium": (sum(circuit) + 0.45) / (len(circuit) + 3),
                    "history_races": len(dh),
                }
            )
            output.append(row)
        for row in daily.to_dict("records"):
            status = row["status_name"]
            nonfinish = not (status == "Finished" or status.startswith("+"))
            drivers[row["driver_id"]].append((row["podium"], row["position_order"], int(nonfinish)))
            circuits[(row["driver_id"], row["circuit_id"])].append(row["podium"])
        for (_, constructor), group in daily.groupby(["race_id", "constructor_id"]):
            constructors[constructor].append(float(group.podium.mean()))
    return pd.DataFrame(output)
