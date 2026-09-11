import React from 'react';
import { createRoot } from 'react-dom/client';
import {
  BrowserRouter,
  Link,
  NavLink,
  Route,
  Routes,
  useParams,
  useSearchParams,
} from 'react-router-dom';
import '@fontsource/barlow/400.css';
import '@fontsource/barlow/600.css';
import '@fontsource/barlow-condensed/600.css';
import '@fontsource/barlow-condensed/700.css';
import './style.css';
import { useApi } from './api';
import Predictions from './Predictions';
import GridScenarioLab from './GridScenarioLab';
import ForecastReview from './ForecastReview';
import DriverComparison from './DriverComparison';
import StrategistChat from './StrategistChat';
import LoadingTable from './LoadingTable';

const ModelLab = React.lazy(() => import('./ModelLab'));

const fmt = (value) =>
  value == null
    ? '—'
    : typeof value === 'number'
      ? value.toLocaleString(undefined, { maximumFractionDigits: 2 })
      : value;
export function DataState({ state, children, className = '' }) {
  if (state.loading)
    return (
      <p role="status" className={`state ${className}`.trim()}>
        Loading race data…
      </p>
    );
  if (state.error)
    return (
      <div role="alert" className={`state error ${className}`.trim()}>
        {state.error} <button onClick={() => window.location.reload()}>Reload</button>
      </div>
    );
  return children(state.data);
}
export function Table({
  rows,
  columns,
  empty = 'No records in the supplied dataset for this selection.',
}) {
  if (!rows?.length) return <p className="state">{empty}</p>;
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.key} scope="col">
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r.result_id ?? r.qualify_id ?? i}>
              {columns.map((c) => (
                <td key={c.key}>{c.render ? c.render(r) : fmt(r[c.key])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
const driverCol = {
  key: 'driver_name',
  label: 'Driver',
  render: (r) => <Link to={`/drivers/${r.driver_id}`}>{r.driver_name}</Link>,
};
const teamCol = {
  key: 'constructor_name',
  label: 'Constructor',
  render: (r) => <Link to={`/constructors/${r.constructor_id}`}>{r.constructor_name}</Link>,
};
function SeasonSelect({ value, onChange }) {
  const seasons = useApi('/seasons');
  return (
    <label className="season-select">
      Season{' '}
      <select aria-label="Season" value={value} onChange={(e) => onChange(e.target.value)}>
        {seasons.data?.data.map((s) => (
          <option key={s.year}>{s.year}</option>
        ))}
      </select>
    </label>
  );
}
function Standings({ kind, year }) {
  const state = useApi(`/standings/${kind}/${year}`);
  if (state.loading) {
    return (
      <LoadingTable label={`Loading ${kind === 'drivers' ? 'driver' : 'constructor'} standings…`} />
    );
  }
  return (
    <DataState state={state}>
      {({ data }) => (
        <Table
          rows={data}
          empty="No constructor championship records for this season."
          columns={[
            { key: 'position', label: 'Pos.' },
            {
              key: 'name',
              label: kind === 'drivers' ? 'Driver' : 'Constructor',
              render: (r) => (
                <Link
                  to={`/${kind}/${r[kind === 'drivers' ? 'driver_id' : 'constructor_id']}?year=${year}`}
                >
                  {r.name}
                </Link>
              ),
            },
            { key: 'points', label: 'Points' },
            { key: 'wins', label: 'Wins' },
          ]}
        />
      )}
    </DataState>
  );
}
function Season() {
  const [search, setSearch] = useSearchParams();
  const year = search.get('year') || '2024';
  const races = useApi(`/races?year=${year}`);
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">Championship archive / {year}</p>
          <h1>
            The season,
            <br />
            <span>in perspective.</span>
          </h1>
        </div>
        <SeasonSelect value={year} onChange={(year) => setSearch({ year })} />
      </div>
      <p className="lede">
        Recorded standings, every race weekend, and the drivers behind the results.
      </p>
      <div className="standings-layout">
        <section>
          <div className="section-heading">
            <h2>Driver championship</h2>
            <span>Final recorded standings</span>
          </div>
          <Standings kind="drivers" year={year} />
        </section>
        <section>
          <div className="section-heading">
            <h2>Constructors</h2>
            <span>Official snapshot</span>
          </div>
          <Standings kind="constructors" year={year} />
          <aside className="coverage">
            <b>75 seasons of racing</b>
            <p>
              This archive ends in 2024. Qualifying, lap and pit-stop coverage varies by season.
            </p>
          </aside>
        </section>
      </div>
      <section className="race-calendar">
        <div className="section-heading">
          <h2>Race weekends</h2>
          <span>{year} calendar</span>
        </div>
        <DataState state={races}>
          {({ data }) => (
            <div className="race-list">
              {data.map((r) => (
                <Link className="race-item" key={r.race_id} to={`/races/${r.race_id}`}>
                  <span className="round">{String(r.round).padStart(2, '0')}</span>
                  <div>
                    <small>
                      {r.date} · {r.country}
                    </small>
                    <h3>{r.name}</h3>
                    <p>{r.circuit_name}</p>
                  </div>
                  <span aria-hidden="true">↗</span>
                </Link>
              ))}
            </div>
          )}
        </DataState>
      </section>
    </>
  );
}
function RaceTable({ raceId, kind, columns }) {
  const state = useApi(`/races/${raceId}/${kind}`);
  if (state.loading) {
    return <LoadingTable label={`Loading race ${kind.replace('-', ' ')}…`} rows={20} />;
  }
  return (
    <DataState state={state}>{({ data }) => <Table rows={data} columns={columns} />}</DataState>
  );
}
function Race() {
  const { id } = useParams();
  const state = useApi(`/races/${id}`);
  const [search, setSearch] = useSearchParams();
  const tab = search.get('tab') || 'results';
  const kinds = ['results', 'grid', 'qualifying', 'pit-stops'];
  return (
    <DataState state={state} className="route-page-state">
      {(r) => (
        <>
          <Link className="back" to={`/?year=${r.year}`}>
            ← {r.year} championship
          </Link>
          <div className="page-heading race-heading">
            <div>
              <p className="eyebrow">
                Round {r.round} / {r.country} / {r.date}
              </p>
              <h1>{r.name}</h1>
              <p className="lede">
                {r.circuit_name} · {r.location}
              </p>
            </div>
            <div className="round-large" aria-hidden="true">
              {String(r.round).padStart(2, '0')}
            </div>
          </div>
          <div className="race-body">
            <section>
              <nav className="tabs" aria-label="Race data">
                {kinds.map((k) => (
                  <button
                    key={k}
                    className={tab === k ? 'active' : ''}
                    aria-pressed={tab === k}
                    onClick={() => setSearch({ tab: k })}
                  >
                    {k.replace('-', ' ')}
                  </button>
                ))}
              </nav>
              {tab === 'results' && (
                <RaceTable
                  raceId={id}
                  kind="results"
                  columns={[
                    { key: 'position_text', label: 'Pos.' },
                    driverCol,
                    teamCol,
                    { key: 'grid', label: 'Grid' },
                    { key: 'points', label: 'Points' },
                    { key: 'status_name', label: 'Status' },
                  ]}
                />
              )}{' '}
              {tab === 'grid' && (
                <>
                  <p className="caption">
                    Recorded starting grid. Zero denotes a pit-lane, unknown or nonstandard start.
                  </p>
                  <RaceTable
                    raceId={id}
                    kind="grid"
                    columns={[{ key: 'grid', label: 'Grid' }, driverCol, teamCol]}
                  />
                </>
              )}
              {tab === 'qualifying' && (
                <RaceTable
                  raceId={id}
                  kind="qualifying"
                  columns={[
                    { key: 'position', label: 'Pos.' },
                    driverCol,
                    { key: 'q1', label: 'Q1' },
                    { key: 'q2', label: 'Q2' },
                    { key: 'q3', label: 'Q3' },
                  ]}
                />
              )}{' '}
              {tab === 'pit-stops' && (
                <>
                  <p className="caption">
                    Elapsed pit-stop duration, including transit and interruptions; not a measure of
                    stationary service time alone.
                  </p>
                  <RaceTable
                    raceId={id}
                    kind="pit-stops"
                    columns={[
                      driverCol,
                      { key: 'stops', label: 'Stops' },
                      { key: 'fastest_seconds', label: 'Fastest (s)' },
                      { key: 'average_seconds', label: 'Average (s)' },
                      { key: 'total_seconds', label: 'Total (s)' },
                    ]}
                  />
                </>
              )}
            </section>
            <aside className="coverage">
              <p className="eyebrow">Race context</p>
              <h2>Read the whole weekend</h2>
              <p>
                Compare the recorded starting grid with qualifying and the classified race result.
              </p>
              <p>
                Historical data may reflect later corrections. Missing timing records are shown as a
                dash.
              </p>
            </aside>
          </div>
          <DriverComparison key={`comparison-${id}`} raceId={id} />
          <Predictions key={id} raceId={id} year={r.year} />
          <GridScenarioLab key={`scenario-${id}`} raceId={id} year={r.year} />
          <ForecastReview key={`review-${id}`} raceId={id} year={r.year} />
        </>
      )}
    </DataState>
  );
}
function Profile() {
  const { kind, id } = useParams();
  const [search, setSearch] = useSearchParams();
  const year = search.get('year') || '2024';
  const state = useApi(`/profiles/${kind}/${id}?year=${year}`);
  return (
    <DataState state={state}>
      {(p) => (
        <>
          <Link className="back" to={`/?year=${year}`}>
            ← Championship
          </Link>
          <div className="page-heading">
            <div>
              <p className="eyebrow">
                {kind === 'drivers' ? 'Driver' : 'Constructor'} profile / {p.entity.nationality}
              </p>
              <h1>{p.entity.name}</h1>
            </div>
            <SeasonSelect value={year} onChange={(year) => setSearch({ year })} />
          </div>
          <div className="stat-strip">
            {[
              ['races', 'Career races'],
              ['wins', 'Race wins'],
              ['podium_races', 'Races with a podium'],
              ['race_points', 'Career race points'],
            ].map(([key, label]) => (
              <div key={key}>
                <b>{fmt(p.career[key])}</b>
                <span>{label}</span>
              </div>
            ))}
          </div>
          <p className="caption">
            Career race points exclude sprints and are not championship totals. A team double podium
            counts as one podium race.
          </p>
          <section>
            <div className="section-heading">
              <h2>Recent form · {year}</h2>
              <span>Latest {p.recent_form.races} recorded race weekends</span>
            </div>
            <div className="stat-strip">
              <div>
                <b>{fmt(p.recent_form.race_points)}</b>
                <span>Race points</span>
              </div>
              <div>
                <b>{fmt(p.recent_form.podium_races)}</b>
                <span>Races with a podium</span>
              </div>
              <div>
                <b>{fmt(p.recent_form.average_classification)}</b>
                <span>Average classification per entry</span>
              </div>
            </div>
            <p className="caption">
              Descriptive results for the selected season, including completed races. The prediction
              model uses only earlier history.
            </p>
          </section>
          <section>
            <div className="section-heading">
              <h2>{year} race results</h2>
              <span>Most recent first</span>
            </div>
            <Table
              rows={p.results}
              columns={[
                {
                  key: 'race_name',
                  label: 'Race',
                  render: (r) => <Link to={`/races/${r.race_id}`}>{r.race_name}</Link>,
                },
                driverCol,
                teamCol,
                { key: 'grid', label: 'Grid' },
                { key: 'position_text', label: 'Finish' },
                { key: 'points', label: 'Points' },
                { key: 'status_name', label: 'Status' },
              ]}
            />
          </section>
          <div className="standings-layout">
            <section>
              <h2>People & constructors · {year}</h2>
              <Table rows={p.associates} columns={[driverCol, teamCol]} />
            </section>
            <section>
              <h2>Circuit record · {year}</h2>
              <Table
                rows={p.circuits}
                columns={[
                  { key: 'name', label: 'Circuit' },
                  { key: 'races', label: 'Races' },
                  { key: 'average_classification', label: 'Avg. classification' },
                  { key: 'podium_races', label: 'Podium races' },
                ]}
              />
            </section>
          </div>
        </>
      )}
    </DataState>
  );
}
function App() {
  return (
    <>
      <header className="masthead">
        <Link className="brand" to="/">
          <span className="brand-mark">F1</span>
          <span>
            RACE
            <br />
            STRATEGIST
          </span>
        </Link>
        <NavLink to="/">Championship archive</NavLink>
        <NavLink to="/model">Model accountability</NavLink>
        <span className="archive-label">Historical intelligence · 1950—2024</span>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<Season />} />
          <Route path="/races/:id" element={<Race />} />
          <Route
            path="/model"
            element={
              <React.Suspense
                fallback={
                  <p role="status" className="state model-page-state">
                    Opening model accountability…
                  </p>
                }
              >
                <ModelLab />
              </React.Suspense>
            }
          />
          <Route path="/:kind/:id" element={<Profile />} />
          <Route
            path="*"
            element={
              <p>
                Page not found. <Link to="/">Open the championship archive</Link>.
              </p>
            }
          />
        </Routes>
      </main>
      <StrategistChat />
      <footer>
        F1 Race Strategist{' '}
        <span>Academic project · Historical data, no live feed · Unofficial</span>
      </footer>
    </>
  );
}
createRoot(document.getElementById('root')).render(
  <BrowserRouter>
    <App />
  </BrowserRouter>,
);
