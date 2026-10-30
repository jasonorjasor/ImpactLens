import { useMemo, useState } from 'react'
import { symbolLabel } from './impactGraph.js'
import { buildReviewBrief, suggestedTestCommand } from './reviewBrief.js'

function Reason({ item, historical }) {
  if (item.direct) return <p>{historical ? 'Contains code deleted in this comparison.' : 'Contains code changed in this comparison.'}</p>
  if (!item.roots.length) return <p>Listed in the report; no matching connection path is available.</p>
  return <p>{historical ? 'Previously connected to ' : 'May use '}
    <code title={item.roots[0]}>{symbolLabel(item.roots[0]).name}</code>
    {item.roots.length > 1 && ` and ${item.roots.length - 1} other changed ${item.roots.length === 2 ? 'function' : 'functions'}`}.
  </p>
}

function StartingPoints({ items, title, empty, historical = false, onExplore, routes = false }) {
  function row(item, index) {
    const label = routes ? `${item.method} ${item.path}` : item.path
    return <li key={index}>
      {routes && <span className="method">{item.method}</span>}<code>{item.path}</code>
      {routes && item.registration !== 'registered' && <p>{item.registration === 'declared' ? 'Router declaration; its app address may be partial.' : 'App registration was not included in this report.'}</p>}
      <Reason item={item} historical={historical} />
      {item.focus && <button type="button" className="brief-link" onClick={() => onExplore(item.focus)}
        aria-label={`Inspect ${historical ? 'older-version ' : ''}${label} connection`}>Inspect connection →</button>}
    </li>
  }
  return <div className="brief-group">
    <h4>{title} <span className="count">{items.length}</span></h4>
    {!items.length ? <p className="brief-empty">{empty}</p> : <ul className="brief-list">
      {items.slice(0, 3).map(row)}
    </ul>}
    {items.length > 3 && <details className="more-results">
      <summary>Show {items.length - 3} more {routes ? 'routes' : 'test files'}</summary>
      <ul className="brief-list">{items.slice(3).map(row)}</ul>
    </details>}
  </div>
}

export function TestCommand({ paths }) {
  const [shell, setShell] = useState('powershell')
  const [status, setStatus] = useState('')
  const command = suggestedTestCommand(paths, shell)

  async function copy() {
    try {
      await navigator.clipboard.writeText(command)
      setStatus('Command copied.')
    } catch {
      setStatus('Copy unavailable. Select and copy the command manually.')
    }
  }

  return <details className="brief-command">
    <summary>Suggested pytest command</summary>
    <p>Run from the repository root at the newer version, with its test dependencies installed.</p>
    <label htmlFor="test-command-shell">Command format</label>
    <select id="test-command-shell" value={shell} onChange={(event) => { setShell(event.target.value); setStatus('') }}>
      <option value="powershell">PowerShell</option>
      <option value="posix">Bash / zsh</option>
    </select>
    {command ? <>
      <label htmlFor="suggested-test-command">Suggested command</label>
      <textarea id="suggested-test-command" readOnly value={command} rows={2} onFocus={(event) => event.currentTarget.select()} />
      <button type="button" className="brief-link" onClick={copy}>Copy command</button>
      <span className="brief-copy-status" role="status">{status}</span>
    </> : <p>These paths cannot be combined into one supported command. Review the listed files manually.</p>}
    <p>This is a suggested subset, not complete test coverage. Keep your normal test suite. ImpactLens has not run these tests.</p>
  </details>
}

export default function ReviewBrief({ report, onExplore }) {
  const brief = useMemo(() => buildReviewBrief(report), [report])
  const hasHistory = report.changed_symbols.some((item) => item.change_type === 'deleted')
  const historicalOnly = hasHistory && !brief.target.routes.length && !brief.target.tests.length
  return <section className="review-brief" aria-label="Review starting points">
    <h3>Start your review</h3>
    <p>Inspect a connection to see the changed code and source evidence behind it. Directly changed items appear first.</p>
    {historicalOnly ? <p>No newer-version route or test connections detected. Start with the older-version evidence below.</p> : <div className="brief-grid">
      <StartingPoints items={brief.target.routes} title="Routes to inspect" routes onExplore={onExplore}
        empty="No route connections detected. Other effects may still need review." />
      <StartingPoints items={brief.target.tests} title="Test files to consider" onExplore={onExplore}
        empty="No test files connected by source analysis. This does not mean the change is untested." />
    </div>}
    {brief.target.tests.length > 0 && <TestCommand key={JSON.stringify(brief.target.tests.map((item) => item.path))} paths={brief.target.tests.map((item) => item.path)} />}
    {hasHistory && <details className="brief-history" open={historicalOnly}>
      <summary>Before deletion · {brief.base.routes.length} former {brief.base.routes.length === 1 ? 'route' : 'routes'}, {brief.base.tests.length} test {brief.base.tests.length === 1 ? 'file' : 'files'}</summary>
      <p>These connections come from the older version and may no longer exist. The command uses only newer-version test suggestions.</p>
      <div className="brief-grid">
        <StartingPoints items={brief.base.routes} title="Former routes" routes historical onExplore={onExplore}
          empty="No former route connections detected." />
        <StartingPoints items={brief.base.tests} title="Former test files" historical onExplore={onExplore}
          empty="No former test file connections detected." />
      </div>
    </details>}
    <p className="brief-footnote">A starting point, not an exhaustive review checklist. Source analysis can miss connections.</p>
  </section>
}
