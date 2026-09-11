import React, { useState, useEffect } from 'react';
import { useMatch } from 'react-router-dom';
import { request, useApi } from './api';
import QueryChart from './QueryChart';
function saved() {
  try {
    return JSON.parse(sessionStorage.getItem('f1-chat') || '[]').slice(-12);
  } catch {
    return [];
  }
}

const supportedIntents = new Set([
  'statistics',
  'prediction',
  'explanation',
  'unsupported',
  'clarify',
]);
const supportedEntityKinds = new Set(['drivers', 'constructors', 'circuits']);

function compactConversation(messages) {
  return messages
    .slice(-3)
    .map((message) => {
      const entities = (message.response?.trace?.entities || [])
        .filter(
          (entity) =>
            supportedEntityKinds.has(entity.kind) &&
            Number.isInteger(entity.id) &&
            entity.id > 0 &&
            typeof entity.name === 'string' &&
            entity.name.length > 0,
        )
        .slice(0, 8)
        .map(({ kind, id, name }) => ({ kind, id, name }));
      return {
        question: message.question,
        intent: message.response?.intent,
        entities,
        race_id: Number.isInteger(message.race_id) ? message.race_id : null,
      };
    })
    .filter(
      (turn) =>
        typeof turn.question === 'string' &&
        turn.question.length >= 3 &&
        supportedIntents.has(turn.intent),
    );
}

function titleCase(value) {
  return typeof value === 'string'
    ? value.charAt(0).toUpperCase() + value.slice(1).replaceAll('_', ' ')
    : 'Unavailable';
}

function AuditTrace({ trace }) {
  if (!trace) return null;
  const repairs = Number(trace.repair_count) || 0;
  const attempts = Array.isArray(trace.attempts) ? trace.attempts.length : 0;
  const elapsed = Number(trace.total_elapsed_ms);
  return (
    <details className="agent-trace">
      <summary>How this answer was built</summary>
      <dl>
        <div>
          <dt>Interpreted question</dt>
          <dd>{trace.interpreted_question || trace.original_question || 'Unavailable'}</dd>
        </div>
        <div>
          <dt>Route</dt>
          <dd>{titleCase(trace.route)}</dd>
        </div>
        <div>
          <dt>Entities</dt>
          <dd>
            {trace.entities?.length
              ? trace.entities.map((entity) => entity.name).join(', ')
              : 'None selected'}
          </dd>
        </div>
        <div>
          <dt>Tables</dt>
          <dd>{trace.tables?.length ? trace.tables.join(', ') : 'No SQL tables used'}</dd>
        </div>
        <div>
          <dt>SQL attempts</dt>
          <dd>
            {attempts} ({repairs} {repairs === 1 ? 'repair' : 'repairs'})
          </dd>
        </div>
        <div>
          <dt>Model calls</dt>
          <dd>{Number(trace.provider_call_count) || 0}</dd>
        </div>
        <div>
          <dt>Total time</dt>
          <dd>{Number.isFinite(elapsed) ? `${(elapsed / 1000).toFixed(2)} s` : 'Unavailable'}</dd>
        </div>
      </dl>
    </details>
  );
}

export default function StrategistChat() {
  const [open, setOpen] = useState(false),
    [messages, setMessages] = useState(saved),
    [question, setQuestion] = useState(''),
    [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  const config = useApi('/chat/config');
  const [accessCode, setAccessCode] = useState('');
  const race = useMatch('/races/:id');
  useEffect(() => {
    try {
      sessionStorage.setItem('f1-chat', JSON.stringify(messages.slice(-12)));
    } catch {
      // Noncritical parsing/storage failure; keep the usable in-memory state.
    }
  }, [messages]);
  async function send(e) {
    e.preventDefault();
    if (!question.trim() || busy) return;
    const asked = question.trim();
    setError('');
    setBusy(true);
    try {
      const selectedRaceId = race ? Number(race.params.id) : null;
      const result = await request('/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'x-chat-access-code': accessCode },
        body: JSON.stringify({
          question: asked,
          race_id: selectedRaceId,
          previous_question: messages.at(-1)?.question || null,
          conversation: compactConversation(messages),
        }),
      });
      setMessages((current) => [
        ...current.slice(-11),
        { question: asked, race_id: selectedRaceId, response: result },
      ]);
      setQuestion('');
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <button
        className="chat-toggle"
        onClick={() => setOpen(!open)}
        aria-label={open ? 'Close strategist' : 'Ask the strategist'}
        aria-expanded={open}
        aria-controls="strategist-chat"
      >
        {open ? 'Close strategist' : 'Ask the strategist'}
      </button>
      {open && (
        <aside id="strategist-chat" className="chat-drawer" aria-label="F1 strategist chat">
          <div className="chat-title">
            <div>
              <p className="eyebrow">F1 strategist</p>
              <h2>Ask the archive.</h2>
            </div>
            <button
              onClick={() => {
                setMessages([]);
                setError('');
              }}
            >
              Clear
            </button>
          </div>
          <p className="caption">
            {race
              ? 'Race questions use the weekend you are viewing.'
              : 'Open a race weekend to ask about its podium prediction.'}{' '}
            Answers use the archive through 2024.
          </p>
          <div className="chat-messages" aria-live="polite">
            {messages.length === 0 && (
              <p className="chat-intro">
                Try “Who won the most races for Red Bull?” or “How many races were held in 2023?”
              </p>
            )}
            {messages.map((m, i) => (
              <article className="chat-message" key={i}>
                <h3>{m.question}</h3>
                {m.response.corrections?.length > 0 && (
                  <p className="caption">
                    Interpreted spelling:{' '}
                    {m.response.corrections.map((c) => `${c.original} → ${c.corrected}`).join(', ')}
                    .
                  </p>
                )}
                <p>{m.response.answer}</p>
                {m.response.assumptions?.length > 0 && (
                  <p className="caption">Assumptions: {m.response.assumptions.join(' ')}</p>
                )}
                <AuditTrace trace={m.response.trace} />
                {m.response.result && (
                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          {m.response.result.columns.map((c, j) => (
                            <th key={j}>{c.replaceAll('_', ' ')}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {m.response.result.rows.map((row, j) => (
                          <tr key={j}>
                            {row.map((value, k) => (
                              <td key={k}>
                                {value == null
                                  ? 'Not recorded'
                                  : typeof value === 'number'
                                    ? value.toLocaleString(undefined, { maximumFractionDigits: 3 })
                                    : String(value)}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                {m.response.result && <QueryChart result={m.response.result} />}
                {m.response.sql && (
                  <details className="sql">
                    <summary>Inspect generated SQL</summary>
                    <pre>
                      <code>{m.response.sql}</code>
                    </pre>
                    <p className="caption">
                      {m.response.status === 'executed'
                        ? 'Executed through the read-only query boundary.'
                        : 'This query was rejected and did not produce an answer.'}
                    </p>
                  </details>
                )}
                {m.response.prediction && (
                  <div>
                    {m.response.prediction.predictions.map((d) => (
                      <details className="chat-driver" key={d.driver_id}>
                        <summary>
                          {d.driver_name} — {(d.probability * 100).toFixed(1)}%
                        </summary>
                        <p className="caption">
                          Grid baseline: {(d.baseline_probability * 100).toFixed(1)}%. SHAP
                          contributions below are calibrated log-odds, not causal effects.
                        </p>
                        {d.factors.map((f) => (
                          <p className="caption" key={f.feature}>
                            {f.feature.replaceAll('_', ' ')}:{' '}
                            {f.log_odds_contribution >= 0 ? '+' : ''}
                            {f.log_odds_contribution.toFixed(3)} (input {f.value.toFixed(3)})
                          </p>
                        ))}
                      </details>
                    ))}
                  </div>
                )}
              </article>
            ))}
          </div>
          {error && (
            <p role="alert" className="error state">
              {error}
            </p>
          )}
          <form onSubmit={send}>
            {config.data?.requires_access_code && (
              <label>
                Chat access code
                <input
                  type="password"
                  autoComplete="off"
                  value={accessCode}
                  onChange={(e) => setAccessCode(e.target.value)}
                />
              </label>
            )}
            <label htmlFor="chat-question">Your F1 question</label>
            <textarea
              id="chat-question"
              value={question}
              maxLength={1500}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="Ask about a driver, season or race…"
              rows={3}
            />
            <button type="submit" disabled={busy || !question.trim()}>
              {busy ? 'Consulting the archive…' : 'Ask question'}
            </button>
          </form>
        </aside>
      )}
    </>
  );
}
