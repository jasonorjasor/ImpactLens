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

function Section({ title, description, items, renderItem, emptyText = 'None found', collapseAfter, moreLabel }) {
  const visibleItems = collapseAfter ? items.slice(0, collapseAfter) : items
  const hiddenItems = collapseAfter ? items.slice(collapseAfter) : []
  return (
    <section className="result-section">
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

function ImpactSummary({ report, historical = false, changedIds }) {
  const relatedTests = report.related_tests.filter((test) => !changedIds.has(test))
  return (
    <div className="result-grid">
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
            <span className="detail">
              {changedIds.has(route.symbol_id)
                ? (historical ? 'Deleted code in the older version' : 'Changed in this comparison')
                : 'Linked through calls'}
            </span>
          </>
        )}
      />
      <Section
        title={historical ? 'Tests in the older version' : 'Additional tests to review'}
        description={historical
          ? 'These tests may have called deleted code before the change.'
          : 'Tests that were not edited but may use changed code.'}
        items={relatedTests}
        emptyText={report.related_tests.length > 0
          ? (historical
            ? 'The deleted tests appear under Changes above.'
            : 'The linked tests were edited in this commit and appear under Changes above.')
          : 'No additional tests found.'}
        renderItem={(test) => (
          <>
            <SymbolLabel identifier={test} />
            <span className="detail">Linked through calls</span>
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
  )
}

export function Report({ report }) {
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
          <code>{report.base_commit}</code> → <code>{report.target_commit}</code>
        </p>
      </div>
      <div className="report-explainer">
        <p>
          <strong>{report.changed_symbols.length} Python functions or classes changed.</strong>{' '}
          The groups below show the changed code and possible callers.
        </p>
        <p>ImpactLens reads source code. A link suggests a dependency; it does not mean anything failed.</p>
      </div>
      <div className="result-grid">
        <Section
          title="Changes in this comparison"
          description="Functions, classes, and tests whose Python code differs between the two versions."
          items={report.changed_symbols}
          emptyText="No changed Python functions or classes found. Other file types are outside this analysis."
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
      <ImpactSummary report={report} changedIds={targetChangedIds} />
      {baseChangedIds.size > 0 && (
        <>
          <h3 className="group-heading">What used to depend on deleted code</h3>
          <p className="caution">
            These links come from the older version. The callers, routes, and tests
            may no longer exist in the newer version.
          </p>
          <ImpactSummary report={report.historical_impact} historical changedIds={baseChangedIds} />
        </>
      )}
      <Section
        title="Possible caller paths"
        description={baseChangedIds.size > 0
          ? 'Older-version paths appear first. Each step calls the one above it. These paths suggest what to review, not what failed.'
          : 'Start with changed code. Each next step is code that calls the step above it. A path suggests what to review, not what failed.'}
        items={displayPaths}
        collapseAfter={5}
        moreLabel="paths"
        emptyText={report.changed_symbols.length > 0 ? 'No caller paths found.' : 'No changed Python functions or classes found.'}
        renderItem={(path) => (
          <div className="path-card">
            <span className="path-source">
              {path.source === 'base' ? 'Older version, before deletion' : 'Newer version'}
            </span>
            <ol className="path-steps">
              {path.symbols.map((symbol, index) => (
                <li key={index}>
                  <span className="step-label">
                    {index === 0 ? (path.source === 'base' ? 'Deleted code' : 'Changed code') : 'Called by'}
                  </span>
                  <SymbolLabel identifier={symbol} />
                </li>
              ))}
            </ol>
          </div>
        )}
      />
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
        <div className="brand-mark">IL</div>
        <div>
          <strong>ImpactLens</strong>
          <span className="brand-subtitle">Python change analysis</span>
        </div>
      </header>

      <div className="intro">
        <p className="eyebrow">Compare two commits</p>
        <h1>See what a code change might affect.</h1>
        <p>
          Enter a public Python GitHub repository and two commits. ImpactLens follows
          function calls to show related routes, tests, and the paths connecting them.
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
            <label htmlFor="base_commit">Base commit</label>
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
            <label htmlFor="target_commit">Target commit</label>
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
