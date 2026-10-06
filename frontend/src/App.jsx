import { useState } from 'react'
import { requestAnalysis } from './api.js'

const initialForm = {
  repository: '',
  base_commit: '',
  target_commit: '',
}

function isTestIdentifier(identifier) {
  const path = identifier.split('::', 1)[0]
  const parts = path.split('/')
  const file = parts[parts.length - 1]
  return parts.includes('tests') || file.startsWith('test_') || file.endsWith('_test.py')
}

function SymbolLabel({ identifier }) {
  const [file, ...name] = identifier.split('::')
  return (
    <span className="symbol-label">
      <code className="symbol-name">{name.join('::') || file}</code>
      {name.length > 0 && <span className="symbol-file">in <code>{file}</code></span>}
    </span>
  )
}

function Section({ title, description, items, renderItem, emptyText = 'None found', className = '', collapseAfter, moreLabel = 'items' }) {
  const visibleItems = collapseAfter ? items.slice(0, collapseAfter) : items
  const hiddenItems = collapseAfter ? items.slice(collapseAfter) : []
  return (
    <section className={`result-section ${className}`}>
      <div className="section-heading">
        <h3>{title}</h3>
        <span className="count">{items.length}</span>
      </div>
      {description && <p className="section-description">{description}</p>}
      {items.length === 0 ? (
        <p className="empty">{emptyText}</p>
      ) : (
        <ul className="result-list">
          {visibleItems.map((item, index) => (
            <li key={index}>{renderItem(item)}</li>
          ))}
        </ul>
      )}
      {hiddenItems.length > 0 && (
        <details className="more-results">
          <summary>Show {hiddenItems.length} more {moreLabel}</summary>
          <ul className="result-list">
            {hiddenItems.map((item, index) => (
              <li key={index}>{renderItem(item)}</li>
            ))}
          </ul>
        </details>
      )}
    </section>
  )
}

function WhyListed({ identifier, changedIds, evidencePaths, historical, kind }) {
  if (changedIds.has(identifier)) {
    return (
      <p className={`why-listed ${kind === 'test' ? 'why-listed--compact' : ''}`}>
        <strong>Why listed:</strong> {historical
          ? 'Its Python code was deleted in this comparison.'
          : 'Its Python code changed in this comparison.'}
      </p>
    )
  }

  const path = evidencePaths.find((item) => (
    item.source === (historical ? 'base' : 'target') && item.symbols.includes(identifier)
  ))
  return (
    <p className={`why-listed ${kind === 'test' ? 'why-listed--compact' : ''}`}>
      <strong>Why listed:</strong>{' '}
      {path ? (
        <>
          {historical ? 'In the older version, it may have called ' : 'May call '}
          <SymbolLabel identifier={path.symbols[0]} /> directly or through other functions.
        </>
      ) : (
        <>Source analysis linked this {kind} to changed code. A matching path is not shown.</>
      )}
    </p>
  )
}

function ImpactSummary({ report, evidencePaths, historical = false, changedIds }) {
  const relatedTests = report.related_tests.filter((test) => !changedIds.has(test))
  return (
    <div className="result-grid">
      <div className="result-column">
        <Section
          title={historical ? 'Routes in the older version' : 'Routes to review'}
          description={historical
            ? 'These routes may have called deleted code before the change.'
            : 'App URLs changed directly or linked to changed code.'}
          items={report.affected_routes}
          renderItem={(route) => (
            <>
              <span className="method">{route.method}</span> <code>{route.path}</code>
              <span className="detail">Handled by <SymbolLabel identifier={route.symbol_id} /></span>
              <WhyListed identifier={route.symbol_id} changedIds={changedIds}
                evidencePaths={evidencePaths} historical={historical} kind="route" />
            </>
          )}
        />
        <Section
          title={historical ? 'Other callers in the older version' : 'Other code callers'}
          description="Code outside the Changes list that may call changed code."
          items={report.affected_symbols.filter(
            (symbol) => !changedIds.has(symbol) && !isTestIdentifier(symbol),
          )}
          emptyText="No other code callers found."
          renderItem={(symbol) => <SymbolLabel identifier={symbol} />}
        />
      </div>
      <div className="result-column">
        <Section
          title={historical ? 'Tests in the older version' : 'Additional tests to review'}
          description={historical
            ? 'These tests may have called deleted code before the change.'
            : 'Tests that were not edited but may use changed code.'}
          items={relatedTests}
          collapseAfter={4}
          moreLabel="tests"
          emptyText={report.related_tests.length > 0
            ? (historical
              ? 'The deleted tests appear under Changes above.'
              : 'The linked tests were edited in this commit and appear under Changes above.')
            : 'No additional tests found.'}
          renderItem={(test) => (
            <>
              <SymbolLabel identifier={test} />
              <WhyListed identifier={test} changedIds={changedIds}
                evidencePaths={evidencePaths} historical={historical} kind="test" />
            </>
          )}
        />
      </div>
    </div>
  )
}

function PathCard({ path }) {
  return (
    <ol className="path-steps">
      {path.symbols.slice(1).map((symbol, index) => (
        <li key={index}>
          <span className="step-label">Called by</span>
          <SymbolLabel identifier={symbol} />
        </li>
      ))}
    </ol>
  )
}

function CallerPaths({ paths, hasDeletedCode }) {
  const groups = []
  for (const path of paths) {
    const key = `${path.source}:${path.symbols[0]}`
    let group = groups.find((item) => item.key === key)
    if (!group) {
      group = { key, source: path.source, root: path.symbols[0], paths: [] }
      groups.push(group)
    }
    group.paths.push(path)
  }

  return (
    <section className="result-section path-section">
      <div className="section-heading">
        <h3>Possible caller paths</h3>
        <span className="count">{paths.length}</span>
      </div>
      <p className="section-description">
        {hasDeletedCode && 'Older-version paths appear first. '}
        Each next step calls the step above it. These are possible connections, not failures.
      </p>
      {groups.length === 0 ? (
        <p className="empty">No caller paths found.</p>
      ) : groups.map((group) => (
        <div className="path-group" key={group.key}>
          <div className="path-group-meta">
            <span className="path-source">{group.source === 'base' ? 'Older version, before deletion' : 'Newer version'}</span>
            <span className="path-count">{group.paths.length} {group.paths.length === 1 ? 'path' : 'paths'}</span>
          </div>
          <h4>{group.source === 'base' ? 'Deleted code: ' : 'Changed code: '}
            <SymbolLabel identifier={group.root} />
          </h4>
          <PathCard path={group.paths[0]} />
          {group.paths.length > 1 && (
            <details className="more-results">
              <summary>Show {group.paths.length - 1} more {group.paths.length === 2 ? 'path' : 'paths'} from this code</summary>
              {group.paths.slice(1).map((path, index) => (
                <div className="extra-path" key={index}><PathCard path={path} /></div>
              ))}
            </details>
          )}
        </div>
      ))}
    </section>
  )
}

export function Report({ report }) {
  const hasChanges = report.changed_symbols.length > 0
  const targetChangedIds = new Set(report.changed_symbols
    .filter((symbol) => symbol.change_type !== 'deleted')
    .map((symbol) => symbol.id))
  const baseChangedIds = new Set(report.changed_symbols
    .filter((symbol) => symbol.change_type === 'deleted')
    .map((symbol) => symbol.id))
  const displayPaths = [...report.evidence_paths].sort(
    (left, right) => Number(right.source === 'base') - Number(left.source === 'base'),
  )
  return (
    <div className="report">
      <div className="report-heading">
        <div>
          <p className="eyebrow">Analysis result</p>
          <h2>Potential impact</h2>
        </div>
        <p className="commit-pair">
          <span><span className="commit-label">Older</span> <code>{report.base_commit}</code></span>
          <span><span className="commit-label">Newer</span> <code>{report.target_commit}</code></span>
        </p>
      </div>
      <div className="report-explainer">
        <p>
          <strong>{hasChanges
            ? `${report.changed_symbols.length} Python functions or classes changed.`
            : 'No Python functions or classes changed.'}</strong>{' '}
          {hasChanges
            ? 'The groups below show the changed code and possible callers.'
            : 'There is no Python code change for ImpactLens to trace in this comparison.'}
        </p>
        <p>{hasChanges
          ? 'ImpactLens reads source code. A link suggests a dependency; it does not mean anything failed.'
          : 'Documentation and other non-Python files are outside this analysis.'}</p>
      </div>
      {hasChanges && (
        <>
          <div className="changes-grid">
            <Section
              className="changes-section"
              title="Changes in this comparison"
              description="Functions, classes, and tests whose Python code differs between the two versions."
              items={report.changed_symbols}
              renderItem={(symbol) => (
                <>
                  <SymbolLabel identifier={symbol.id} />
                  <span className="detail">
                    {isTestIdentifier(symbol.id) ? 'Test code · ' : ''}
                    {symbol.change_type === 'added' ? 'Added' : symbol.change_type === 'deleted' ? 'Deleted' : 'Changed'}
                  </span>
                  {(symbol.changed_lines?.length > 0 || symbol.removed_lines?.length > 0) && (
                    <details className="line-details">
                      <summary>Show line numbers</summary>
                      {symbol.changed_lines?.length > 0 && (
                        <span className="detail">Newer version: {symbol.changed_lines.join(', ')}</span>
                      )}
                      {symbol.removed_lines?.length > 0 && (
                        <span className="detail">Older version, removed lines: {symbol.removed_lines.join(', ')}</span>
                      )}
                    </details>
                  )}
                </>
              )}
            />
          </div>
          <h3 className="group-heading">Possible effects in the newer version</h3>
          <ImpactSummary report={report} evidencePaths={report.evidence_paths}
            changedIds={targetChangedIds} />
          {baseChangedIds.size > 0 && (
            <>
              <h3 className="group-heading">What used to depend on deleted code</h3>
              <p className="caution">
                These links come from the older version. The callers, routes, and tests
                may no longer exist in the newer version.
              </p>
              <ImpactSummary report={report.historical_impact} evidencePaths={report.evidence_paths}
                historical changedIds={baseChangedIds} />
            </>
          )}
          <CallerPaths paths={displayPaths} hasDeletedCode={baseChangedIds.size > 0} />
        </>
      )}
      {report.analysis_errors?.length > 0 && (
        <>
          <p className="caution">Some files could not be analyzed. Results may be incomplete.</p>
          <Section
            title="Files not analyzed"
            items={report.analysis_errors}
            renderItem={(item) => (
              <>
                <code>{item.path}</code>
                <span className="detail">{item.source} version: {item.error}</span>
              </>
            )}
          />
        </>
      )}
    </div>
  )
}

export default function App() {
  const [form, setForm] = useState(initialForm)
  const [report, setReport] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  function updateField(event) {
    setForm({ ...form, [event.target.name]: event.target.value })
  }

  async function submit(event) {
    event.preventDefault()
    setError('')
    setReport(null)
    setLoading(true)

    try {
      const data = await requestAnalysis({
        repository: form.repository.trim(),
        base_commit: form.base_commit.trim(),
        target_commit: form.target_commit.trim(),
      })
      setReport(data)
    } catch (caught) {
      setError(caught.message || 'Could not reach the API')
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="page">
      <header className="site-header">
        <strong>ImpactLens</strong>
        <span className="brand-subtitle">Python change analysis</span>
      </header>

      <div className="intro">
        <h1>Compare Python changes</h1>
        <p>
          Compare two commits in a public GitHub repository to find changed Python code
          and the routes, tests, and functions that may use it.
        </p>
      </div>

      <form className="analysis-form" onSubmit={submit}>
        <label htmlFor="repository">GitHub repository</label>
        <input
          id="repository"
          name="repository"
          type="url"
          placeholder="https://github.com/owner/repository"
          value={form.repository}
          onChange={updateField}
          required
        />
        <div className="commit-fields">
          <div>
            <label htmlFor="base_commit">Older commit (base)</label>
            <input
              id="base_commit"
              name="base_commit"
              placeholder="Older commit SHA"
              value={form.base_commit}
              onChange={updateField}
              required
            />
          </div>
          <div>
            <label htmlFor="target_commit">Newer commit (target)</label>
            <input
              id="target_commit"
              name="target_commit"
              placeholder="Newer commit SHA"
              value={form.target_commit}
              onChange={updateField}
              required
            />
          </div>
        </div>
        <button type="submit" disabled={loading}>
          {loading ? 'Analyzing…' : 'Analyze changes'}
        </button>
        {error && <p className="error" role="alert">{error}</p>}
      </form>

      {report && <Report report={report} />}
    </main>
  )
}
