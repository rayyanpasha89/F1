
CREATE TABLE circuits (
	circuit_id INTEGER NOT NULL, 
	circuit_ref TEXT NOT NULL, 
	name TEXT NOT NULL, 
	location TEXT NOT NULL, 
	country TEXT NOT NULL, 
	lat FLOAT NOT NULL, 
	lng FLOAT NOT NULL, 
	alt INTEGER NOT NULL, 
	url TEXT NOT NULL, 
	PRIMARY KEY (circuit_id)
)

;

CREATE TABLE constructors (
	constructor_id INTEGER NOT NULL, 
	constructor_ref TEXT NOT NULL, 
	name TEXT NOT NULL, 
	nationality TEXT NOT NULL, 
	url TEXT NOT NULL, 
	PRIMARY KEY (constructor_id)
)

;

CREATE TABLE drivers (
	driver_id INTEGER NOT NULL, 
	driver_ref TEXT NOT NULL, 
	number INTEGER, 
	code TEXT, 
	forename TEXT NOT NULL, 
	surname TEXT NOT NULL, 
	dob TEXT NOT NULL, 
	nationality TEXT NOT NULL, 
	url TEXT NOT NULL, 
	PRIMARY KEY (driver_id)
)

;

CREATE TABLE seasons (
	year INTEGER NOT NULL, 
	url TEXT NOT NULL, 
	PRIMARY KEY (year)
)

;

CREATE TABLE status (
	status_id INTEGER NOT NULL, 
	status TEXT NOT NULL, 
	PRIMARY KEY (status_id)
)

;

CREATE TABLE races (
	race_id INTEGER NOT NULL, 
	year INTEGER NOT NULL, 
	round INTEGER NOT NULL, 
	circuit_id INTEGER NOT NULL, 
	name TEXT NOT NULL, 
	date TEXT NOT NULL, 
	time TEXT, 
	url TEXT NOT NULL, 
	fp1_date TEXT, 
	fp1_time TEXT, 
	fp2_date TEXT, 
	fp2_time TEXT, 
	fp3_date TEXT, 
	fp3_time TEXT, 
	quali_date TEXT, 
	quali_time TEXT, 
	sprint_date TEXT, 
	sprint_time TEXT, 
	PRIMARY KEY (race_id), 
	FOREIGN KEY(year) REFERENCES seasons (year), 
	FOREIGN KEY(circuit_id) REFERENCES circuits (circuit_id)
)

;

CREATE TABLE constructor_results (
	constructor_results_id INTEGER NOT NULL, 
	race_id INTEGER NOT NULL, 
	constructor_id INTEGER NOT NULL, 
	points FLOAT NOT NULL, 
	status TEXT, 
	PRIMARY KEY (constructor_results_id), 
	FOREIGN KEY(race_id) REFERENCES races (race_id), 
	FOREIGN KEY(constructor_id) REFERENCES constructors (constructor_id)
)

;

CREATE TABLE constructor_standings (
	constructor_standings_id INTEGER NOT NULL, 
	race_id INTEGER NOT NULL, 
	constructor_id INTEGER NOT NULL, 
	points FLOAT NOT NULL, 
	position INTEGER NOT NULL, 
	position_text TEXT NOT NULL, 
	wins INTEGER NOT NULL, 
	PRIMARY KEY (constructor_standings_id), 
	FOREIGN KEY(race_id) REFERENCES races (race_id), 
	FOREIGN KEY(constructor_id) REFERENCES constructors (constructor_id)
)

;

CREATE TABLE driver_standings (
	driver_standings_id INTEGER NOT NULL, 
	race_id INTEGER NOT NULL, 
	driver_id INTEGER NOT NULL, 
	points FLOAT NOT NULL, 
	position INTEGER NOT NULL, 
	position_text TEXT NOT NULL, 
	wins INTEGER NOT NULL, 
	PRIMARY KEY (driver_standings_id), 
	FOREIGN KEY(race_id) REFERENCES races (race_id), 
	FOREIGN KEY(driver_id) REFERENCES drivers (driver_id)
)

;

CREATE TABLE lap_times (
	race_id INTEGER NOT NULL, 
	driver_id INTEGER NOT NULL, 
	lap INTEGER NOT NULL, 
	position INTEGER NOT NULL, 
	time TEXT NOT NULL, 
	milliseconds INTEGER NOT NULL, 
	PRIMARY KEY (race_id, driver_id, lap), 
	FOREIGN KEY(race_id) REFERENCES races (race_id), 
	FOREIGN KEY(driver_id) REFERENCES drivers (driver_id)
)

;

CREATE TABLE pit_stops (
	race_id INTEGER NOT NULL, 
	driver_id INTEGER NOT NULL, 
	stop INTEGER NOT NULL, 
	lap INTEGER NOT NULL, 
	time TEXT NOT NULL, 
	duration TEXT NOT NULL, 
	milliseconds INTEGER NOT NULL, 
	PRIMARY KEY (race_id, driver_id, stop), 
	FOREIGN KEY(race_id) REFERENCES races (race_id), 
	FOREIGN KEY(driver_id) REFERENCES drivers (driver_id)
)

;

CREATE TABLE qualifying (
	qualify_id INTEGER NOT NULL, 
	race_id INTEGER NOT NULL, 
	driver_id INTEGER NOT NULL, 
	constructor_id INTEGER NOT NULL, 
	number INTEGER NOT NULL, 
	position INTEGER NOT NULL, 
	q1 TEXT, 
	q2 TEXT, 
	q3 TEXT, 
	PRIMARY KEY (qualify_id), 
	FOREIGN KEY(race_id) REFERENCES races (race_id), 
	FOREIGN KEY(driver_id) REFERENCES drivers (driver_id), 
	FOREIGN KEY(constructor_id) REFERENCES constructors (constructor_id)
)

;

CREATE TABLE results (
	result_id INTEGER NOT NULL, 
	race_id INTEGER NOT NULL, 
	driver_id INTEGER NOT NULL, 
	constructor_id INTEGER NOT NULL, 
	number INTEGER, 
	grid INTEGER NOT NULL, 
	position INTEGER, 
	position_text TEXT NOT NULL, 
	position_order INTEGER NOT NULL, 
	points FLOAT NOT NULL, 
	laps INTEGER NOT NULL, 
	time TEXT, 
	milliseconds INTEGER, 
	fastest_lap INTEGER, 
	rank INTEGER, 
	fastest_lap_time TEXT, 
	fastest_lap_speed FLOAT, 
	status_id INTEGER NOT NULL, 
	PRIMARY KEY (result_id), 
	FOREIGN KEY(race_id) REFERENCES races (race_id), 
	FOREIGN KEY(driver_id) REFERENCES drivers (driver_id), 
	FOREIGN KEY(constructor_id) REFERENCES constructors (constructor_id), 
	FOREIGN KEY(status_id) REFERENCES status (status_id)
)

;

CREATE TABLE sprint_results (
	result_id INTEGER NOT NULL, 
	race_id INTEGER NOT NULL, 
	driver_id INTEGER NOT NULL, 
	constructor_id INTEGER NOT NULL, 
	number INTEGER NOT NULL, 
	grid INTEGER NOT NULL, 
	position INTEGER, 
	position_text TEXT NOT NULL, 
	position_order INTEGER NOT NULL, 
	points INTEGER NOT NULL, 
	laps INTEGER NOT NULL, 
	time TEXT, 
	milliseconds INTEGER, 
	fastest_lap INTEGER, 
	fastest_lap_time TEXT, 
	status_id INTEGER NOT NULL, 
	PRIMARY KEY (result_id), 
	FOREIGN KEY(race_id) REFERENCES races (race_id), 
	FOREIGN KEY(driver_id) REFERENCES drivers (driver_id), 
	FOREIGN KEY(constructor_id) REFERENCES constructors (constructor_id), 
	FOREIGN KEY(status_id) REFERENCES status (status_id)
)

;
CREATE INDEX ix_races_circuit_id ON races (circuit_id);
CREATE INDEX ix_races_year ON races (year);
CREATE INDEX ix_races_year_round ON races (year, round);
CREATE INDEX ix_constructor_results_constructor_id ON constructor_results (constructor_id);
CREATE INDEX ix_constructor_results_race_id ON constructor_results (race_id);
CREATE INDEX ix_constructor_standings_constructor_id ON constructor_standings (constructor_id);
CREATE INDEX ix_constructor_standings_race_id ON constructor_standings (race_id);
CREATE INDEX ix_driver_standings_driver_id ON driver_standings (driver_id);
CREATE INDEX ix_driver_standings_race_id ON driver_standings (race_id);
CREATE INDEX ix_lap_times_driver_id ON lap_times (driver_id);
CREATE INDEX ix_pit_stops_driver_id ON pit_stops (driver_id);
CREATE INDEX ix_qualifying_constructor_id ON qualifying (constructor_id);
CREATE INDEX ix_qualifying_driver_id ON qualifying (driver_id);
CREATE INDEX ix_qualifying_race_id ON qualifying (race_id);
CREATE INDEX ix_results_constructor_id ON results (constructor_id);
CREATE INDEX ix_results_driver_id ON results (driver_id);
CREATE INDEX ix_results_race_driver ON results (race_id, driver_id);
CREATE INDEX ix_results_race_id ON results (race_id);
CREATE INDEX ix_results_status_id ON results (status_id);
CREATE INDEX ix_sprint_results_constructor_id ON sprint_results (constructor_id);
CREATE INDEX ix_sprint_results_driver_id ON sprint_results (driver_id);
CREATE INDEX ix_sprint_results_race_id ON sprint_results (race_id);
CREATE INDEX ix_sprint_results_status_id ON sprint_results (status_id);