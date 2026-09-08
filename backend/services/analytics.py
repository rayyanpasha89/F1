"""Bound-parameter analytics queries, shared by the HTTP layer and tests."""

from sqlalchemy import text


class NotFound(Exception):
    pass


class Analytics:
    def __init__(self, engine):
        self.engine = engine

    def rows(self, sql, **params):
        with self.engine.connect() as conn:
            return [dict(r) for r in conn.execute(text(sql), params).mappings()]

    def one(self, sql, **params):
        rows = self.rows(sql, **params)
        if not rows:
            raise NotFound("No matching record in the supplied snapshot")
        return rows[0]

    def seasons(self):
        return self.rows(
            "SELECT year, COUNT(*) AS races FROM races GROUP BY year ORDER BY year DESC"
        )

    def races(self, year):
        self.one("SELECT year FROM seasons WHERE year=:year", year=year)
        return self.rows(
            """SELECT r.*, c.name AS circuit_name, c.country, c.location
            FROM races r JOIN circuits c USING(circuit_id) WHERE year=:year ORDER BY round""",
            year=year,
        )

    def race(self, race_id):
        return self.one(
            """SELECT r.*, c.name AS circuit_name, c.country, c.location, c.lat, c.lng
            FROM races r JOIN circuits c USING(circuit_id) WHERE race_id=:race_id""",
            race_id=race_id,
        )

    def standings(self, year, kind):
        # kind is an internal enum selected by the router, never arbitrary client SQL.
        table, entity, key, label = {
            "drivers": (
                "driver_standings",
                "drivers",
                "driver_id",
                "e.forename || ' ' || e.surname",
            ),
            "constructors": ("constructor_standings", "constructors", "constructor_id", "e.name"),
        }[kind]
        self.one("SELECT year FROM seasons WHERE year=:year", year=year)
        return self.rows(
            f"""SELECT s.*, {label} AS name, r.round, r.name AS race_name
            FROM {table} s JOIN {entity} e USING({key}) JOIN races r USING(race_id)
            WHERE s.race_id=(SELECT r2.race_id FROM races r2
                WHERE r2.year=:year AND EXISTS(SELECT 1 FROM {table} s2 WHERE s2.race_id=r2.race_id)
                ORDER BY r2.round DESC LIMIT 1)
            ORDER BY s.position, s.{key}""",
            year=year,
        )

    def race_table(self, race_id, kind):
        self.race(race_id)
        queries = {
            "results": """SELECT x.*, d.forename || ' ' || d.surname AS driver_name,
                c.name AS constructor_name, s.status AS status_name
                FROM results x JOIN drivers d USING(driver_id) JOIN constructors c USING(constructor_id)
                JOIN status s USING(status_id) WHERE race_id=:race_id ORDER BY position_order, result_id""",
            "qualifying": """SELECT q.*, d.forename || ' ' || d.surname AS driver_name, c.name AS constructor_name
                FROM qualifying q JOIN drivers d USING(driver_id) JOIN constructors c USING(constructor_id)
                WHERE race_id=:race_id ORDER BY position""",
            "pit-stops": """SELECT p.driver_id, d.forename || ' ' || d.surname AS driver_name,
                COUNT(*) AS stops, MIN(p.milliseconds)/1000.0 AS fastest_seconds,
                AVG(p.milliseconds)/1000.0 AS average_seconds, SUM(p.milliseconds)/1000.0 AS total_seconds
                FROM pit_stops p JOIN drivers d USING(driver_id) WHERE race_id=:race_id
                GROUP BY p.driver_id, d.forename, d.surname ORDER BY total_seconds""",
            "grid": """SELECT x.result_id, x.driver_id, x.constructor_id, x.grid,
                d.forename || ' ' || d.surname AS driver_name, c.name AS constructor_name
                FROM results x JOIN drivers d USING(driver_id) JOIN constructors c USING(constructor_id)
                WHERE race_id=:race_id ORDER BY CASE WHEN grid>0 THEN grid ELSE 999 END, x.driver_id""",
        }
        return self.rows(queries[kind], race_id=race_id)

    def entities(self, kind, year=None):
        table, key, label = {
            "drivers": ("drivers", "driver_id", "e.forename || ' ' || e.surname"),
            "constructors": ("constructors", "constructor_id", "e.name"),
        }[kind]
        if year is not None:
            self.one("SELECT year FROM seasons WHERE year=:year", year=year)
        return self.rows(
            f"""SELECT e.*, {label} AS name FROM {table} e
            WHERE (:year IS NULL OR EXISTS(SELECT 1 FROM results x JOIN races r USING(race_id)
            WHERE x.{key}=e.{key} AND r.year=:year)) ORDER BY name""",
            year=year,
        )

    def profile(self, kind, identifier, year=None):
        table, key, label = {
            "drivers": ("drivers", "driver_id", "e.forename || ' ' || e.surname"),
            "constructors": ("constructors", "constructor_id", "e.name"),
        }[kind]
        entity = self.one(
            f"SELECT e.*, {label} AS name FROM {table} e WHERE {key}=:id", id=identifier
        )
        if year is not None:
            self.one("SELECT year FROM seasons WHERE year=:year", year=year)
        stats_sql = f"""SELECT COUNT(DISTINCT race_id) AS races,
            COUNT(DISTINCT CASE WHEN position=1 THEN race_id END) AS wins,
            COUNT(DISTINCT CASE WHEN position BETWEEN 1 AND 3 THEN race_id END) AS podium_races,
            SUM(points) AS race_points FROM results WHERE {key}=:id"""
        career = self.one(stats_sql, id=identifier)
        results = self.rows(
            f"""SELECT x.*, r.year, r.round, r.date, r.name AS race_name,
            r.circuit_id, d.forename || ' ' || d.surname AS driver_name, c.name AS constructor_name,
            s.status AS status_name FROM results x JOIN races r USING(race_id)
            JOIN drivers d USING(driver_id) JOIN constructors c USING(constructor_id)
            JOIN status s USING(status_id)
            WHERE x.{key}=:id AND (:year IS NULL OR r.year=:year)
            ORDER BY r.date DESC, x.position_order LIMIT 2000""",
            id=identifier,
            year=year,
        )
        associates = self.rows(
            f"""SELECT DISTINCT d.driver_id, d.forename || ' ' || d.surname AS driver_name,
            c.constructor_id, c.name AS constructor_name FROM results x
            JOIN races r USING(race_id) JOIN drivers d USING(driver_id) JOIN constructors c USING(constructor_id)
            WHERE x.{key}=:id AND (:year IS NULL OR r.year=:year) ORDER BY constructor_name, driver_name""",
            id=identifier,
            year=year,
        )
        circuits = self.rows(
            f"""SELECT c.circuit_id, c.name, COUNT(DISTINCT x.race_id) AS races,
            AVG(x.position_order) AS average_classification,
            COUNT(DISTINCT CASE WHEN x.position BETWEEN 1 AND 3 THEN x.race_id END) AS podium_races
            FROM results x JOIN races r USING(race_id) JOIN circuits c USING(circuit_id)
            WHERE x.{key}=:id AND (:year IS NULL OR r.year=:year)
            GROUP BY c.circuit_id, c.name ORDER BY races DESC, c.name""",
            id=identifier,
            year=year,
        )
        return {
            "entity": entity,
            "career": career,
            "results": results,
            "associates": associates,
            "circuits": circuits,
            "year": year,
            "notes": [
                "Race points exclude sprints and are not official championship totals.",
                "Podium races count distinct races with a podium; team double podiums count once.",
                "Result history is capped at 2000 records; choose a season for complete detail.",
            ],
        }
