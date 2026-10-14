import { useState } from 'react'
import { createRoot } from 'react-dom/client'
import { Report } from '../src/App.jsx'
import '../src/styles.css'

const empty = {
  base_commit: 'artificial-older', target_commit: 'artificial-newer',
  changed_symbols: [{ id: 'service.py::changed', changed_lines: [2] }],
  affected_symbols: [], affected_routes: [], related_tests: [],
  historical_impact: { affected_symbols: [], affected_routes: [], related_tests: [] },
  evidence_paths: [], analysis_errors: [],
}
const cases = {
  isolation: empty,
  cycle: { ...empty, evidence_paths: [
    { source: 'target', symbols: ['service.py::changed', 'service.py::caller', 'service.py::changed (cycle)'] },
  ] },
  incomplete: { ...empty, analysis_errors: [{ source: 'target', path: 'broken.py', error: 'Artificial parse error' }] },
  branching: { ...empty, evidence_paths: Array.from({ length: 70 }, (_, i) => ({
    source: 'target', symbols: ['service.py::changed', `callers.py::caller_${i}`],
  })) },
  alternatives: { ...empty, related_tests: ['tests/test_service.py::test_shared'], evidence_paths: [
    { source: 'target', symbols: ['service.py::changed', 'service.py::left', 'tests/test_service.py::test_shared'] },
    { source: 'target', symbols: ['service.py::changed', 'service.py::right', 'tests/test_service.py::test_shared'] },
  ] },
  deep: { ...empty, evidence_paths: [{ source: 'target', symbols: [
    'service.py::changed', ...Array.from({ length: 70 }, (_, i) => `deep.py::step_${i}`),
  ] }] },
}

function Preview() {
  const [scenario, setScenario] = useState('isolation')
  return <main className="page">
    <h1>Map verification fixtures</h1>
    <p>Artificial reports for development checks. These are not real repository analyses.</p>
    <label htmlFor="scenario">Scenario</label>
    <select id="scenario" value={scenario} onChange={(event) => setScenario(event.target.value)}>
      {Object.keys(cases).map((name) => <option key={name}>{name}</option>)}
    </select>
    <Report key={scenario} report={cases[scenario]} initialView="map" />
  </main>
}

createRoot(document.getElementById('root')).render(<Preview />)
