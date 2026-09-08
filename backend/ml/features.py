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
