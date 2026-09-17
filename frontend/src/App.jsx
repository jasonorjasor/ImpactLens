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

function Section({ title, items, renderItem, emptyText = 'None found' }) {
  return (
    <section className="result-section">
      <div className="section-heading">
        <h2>{title}</h2>
        <span className="count">{items.length}</span>
      </div>
      {items.length === 0 ? (
        <p className="empty">{emptyText}</p>
      ) : (
        <ul className="result-list">
          {items.map((item, index) => (
            <li key={index}>{renderItem(item)}</li>
          ))}
        </ul>
      )}
    </section>
  )
}

function ImpactSummary({ report, historical = false, changedIds }) {
  const relatedTests = report.related_tests.filter((test) => !changedIds.has(test))
  return (
    <div className="result-grid">
      <Section
        title={historical ? 'Historical routes' : 'Affected routes'}
        items={report.affected_routes}
        renderItem={(route) => (
          <>
            <span className="method">{route.method}</span> <code>{route.path}</code>
            <span className="detail">{route.symbol_id}</span>
            <span className="detail">
              {changedIds.has(route.symbol_id) ? 'Changed directly' : 'Reached via calls'}
            </span>
          </>
        )}
      />
      <Section
        title={historical ? 'Historical related tests' : 'Related tests'}
        items={relatedTests}
        emptyText={report.related_tests.length > 0 ? 'Changed tests are listed above' : 'None found'}
        renderItem={(test) => (
          <>
            <code>{test}</code>
            <span className="detail">Reached via calls</span>
          </>
        )}
      />
      <Section
        title={historical ? 'Historical callers' : 'Affected code'}
        items={report.affected_symbols.filter(
          (symbol) => !changedIds.has(symbol) && !isTestIdentifier(symbol),
        )}
        emptyText="No additional code callers found"
        renderItem={(symbol) => <code>{symbol}</code>}
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
      <p className="caution">
        These are possible impacts found from Python source. ImpactLens does not run the code.
      </p>
      <div className="result-grid">
        <Section
          title="Changed functions"
          items={report.changed_symbols}
          renderItem={(symbol) => (
            <>
              <code>{symbol.id}</code>
              {isTestIdentifier(symbol.id) && <span className="detail">Test code</span>}
              {symbol.change_type && <span className="detail">{symbol.change_type}</span>}
              {symbol.changed_lines?.length > 0 && (
                <span className="detail">Lines {symbol.changed_lines.join(', ')}</span>
              )}
              {symbol.removed_lines?.length > 0 && (
                <span className="detail">
                  Removed lines (base version): {symbol.removed_lines.join(', ')}
                </span>
              )}
            </>
          )}
        />
      </div>
      <p>Results from the target version:</p>
      <ImpactSummary report={report} changedIds={targetChangedIds} />
      {baseChangedIds.size > 0 && (
        <>
          <p className="caution">
            Historical results come from the base version. These functions, routes,
            and tests may no longer exist or depend on the deleted code.
          </p>
          <ImpactSummary report={report.historical_impact} historical changedIds={baseChangedIds} />
        </>
      )}
      <Section
        title="Impact paths"
        items={report.evidence_paths}
        emptyText={report.changed_symbols.length > 0 ? 'No caller paths found' : 'No changed functions found'}
        renderItem={(path) => (
          <div className="path">
            <span className="detail">
              {path.source === 'base' ? 'Base version (historical)' : 'Target version'}
            </span>
            {path.symbols.map((symbol, index) => (
              <span key={index}>
                {index > 0 && <span className="arrow">→</span>}
                <code>{symbol}</code>
              </span>
            ))}
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
