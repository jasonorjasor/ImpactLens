import { connectionEvidence, sourceLink, symbolLabel } from './impactGraph.js'

function SourceLocation({ report, source, path, start, end = start, children }) {
  const href = sourceLink(report, source, path, start, end)
  return href
    ? <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>
    : <span>{children}</span>
}

function CallStep({ report, source, step }) {
  function siteRow(site) {
    return (
      <li key={`${site.path}:${site.line}:${site.column}`}>
        <SourceLocation report={report} source={source} path={site.path} start={site.line} end={site.line_end}>
          {site.path}:{site.line}{site.line_end > site.line ? `–${site.line_end}` : ''}
        </SourceLocation>
        <pre><code>{site.code}{site.code_truncated ? ' …' : ''}</code></pre>
        {site.relationship === 'fastapi_dependency' && <p>Declared with Depends(): FastAPI supplies this dependency when handling a request. This is not a direct call in the function body.</p>}
        <p>{site.resolution === 'import' ? 'Matched through an imported name.' : 'Matched by a name in the same file.'}</p>
      </li>
    )
  }
  return (
    <li className="call-evidence-step">
      <p><code>{symbolLabel(step.caller).name}</code> {step.sites.some((site) => site.relationship === 'fastapi_dependency') ? 'depends on' : 'calls'} <code>{symbolLabel(step.callee).name}</code></p>
      {step.sites.length === 0
        ? <p>Call-site evidence is unavailable for this step.</p>
        : <>
          <ul className="call-site-list">{step.sites.slice(0, 2).map(siteRow)}</ul>
          {step.sites.length > 2 && <details className="more-results">
            <summary>Show {step.sites.length - 2} more call {step.sites.length === 3 ? 'site' : 'sites'}</summary>
            <ul className="call-site-list">{step.sites.slice(2).map(siteRow)}</ul>
          </details>}
        </>}
    </li>
  )
}

export default function SourceEvidence({ report, source, identifier, identifiers = [] }) {
  if (![2, 3].includes(report.schema_version)) return <p className="map-note">Source evidence is unavailable in this older report. Run the comparison again to inspect call sites.</p>
  const locations = report.symbol_locations.filter((item) => item.source === source && item.id === identifier)
  const steps = connectionEvidence(report, source, identifiers)
  const commit = report.resolved_commits[source]
  return (
    <section className="source-evidence" aria-label="Source evidence">
      <h4>Why this connection?</h4>
      <p>{source === 'base' ? 'Older version · before deletion' : 'Newer version'}{commit ? <> · commit <code title={commit}>{commit.slice(0, 10)}</code></> : ' · saved working-tree files'}</p>
      {locations.length > 1 && <p>Multiple definitions share this name. Inspect each source location; the name alone does not identify one definition.</p>}
      {locations.map((location) => <p key={`${location.path}:${location.line_start}:${location.line_end}`}>Selected definition:{' '}
        <SourceLocation report={report} source={source} path={location.path} start={location.line_start} end={location.line_end}>
          {location.path}:{location.line_start}–{location.line_end}
        </SourceLocation>
      </p>)}
      {steps.length === 0
        ? <p>Select a caller to see the source lines behind its connection.</p>
        : <>
          <p>Each step below names the code using a dependency first. Matches use source-level rules and can be imperfect.</p>
          <ol className="call-evidence-list">{steps.slice(0, 4).map((step, index) => <CallStep key={index} report={report} source={source} step={step} />)}</ol>
          {steps.length > 4 && <details className="more-results">
            <summary>Show the remaining {steps.length - 4} connection steps</summary>
            <ol className="call-evidence-list" start={5}>{steps.slice(4).map((step, index) => <CallStep key={index} report={report} source={source} step={step} />)}</ol>
          </details>}
        </>}
      {!report.repository_url && <p>File locations are local; GitHub links are available for public GitHub analyses.</p>}
    </section>
  )
}
