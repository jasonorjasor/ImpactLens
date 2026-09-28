import assert from 'node:assert/strict'
import test from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'

function makeReport(overrides = {}) {
  return {
    base_commit: 'base',
    target_commit: 'target',
    changed_symbols: [],
    affected_symbols: [],
    affected_routes: [],
    related_tests: [],
    historical_impact: {
      affected_symbols: [],
      affected_routes: [],
      related_tests: [],
    },
    evidence_paths: [],
    analysis_errors: [],
    ...overrides,
  }
}

async function render(report) {
  const server = await createServer({
    server: { middlewareMode: true, hmr: false },
    appType: 'custom',
  })
  try {
    const { Report } = await server.ssrLoadModule('/src/App.jsx')
    return renderToStaticMarkup(createElement(Report, { report }))
  } finally {
    await server.close()
  }
}

test('distinguishes direct changes from reached routes and tests', async () => {
  const html = await render(makeReport({
    changed_symbols: [
      { id: 'api.py::direct_route', changed_lines: [2] },
      { id: 'tests/test_api.py::test_direct', changed_lines: [4] },
    ],
    affected_symbols: ['api.py::direct_route', 'service.py::caller'],
    affected_routes: [
      { symbol_id: 'api.py::direct_route', method: 'GET', path: '/direct' },
      { symbol_id: 'api.py::reached_route', method: 'GET', path: '/reached' },
    ],
    related_tests: ['tests/test_api.py::test_direct', 'tests/test_api.py::test_reached'],
    evidence_paths: [
      { source: 'target', symbols: ['api.py::direct_route', 'api.py::reached_route'] },
      { source: 'target', symbols: ['api.py::direct_route', 'tests/test_api.py::test_reached'] },
    ],
  }))

  assert.match(html, /<h3>Routes to review<\/h3><span class="count">2<\/span>/)
  assert.match(html, /Why listed:<\/strong> Its Python code changed in this comparison/)
  assert.match(html, /Why listed:<\/strong> May call .*direct_route/)
  assert.match(html, /why-listed--compact/)
  assert.match(html, /<h3>Additional tests to review<\/h3><span class="count">1<\/span>/)
  assert.match(html, /<h3>Other code callers<\/h3><span class="count">1<\/span>/)
  assert.equal(html.split('test_direct</code>').length - 1, 1)
  assert.match(html, /<h3>Possible caller paths<\/h3><span class="count">2<\/span>/)
  assert.match(html, /<h4>Changed code:/)
  assert.match(html, /Called by<\/span>/)
  assert.match(html, /direct_route<\/code>.*in <code>api.py<\/code>/)
})

test('keeps a deleted route visible when it has no caller path', async () => {
  const html = await render(makeReport({
    changed_symbols: [{ id: 'api.py::old_route', change_type: 'deleted', changed_lines: [] }],
    historical_impact: {
      affected_symbols: [],
      affected_routes: [{ symbol_id: 'api.py::old_route', method: 'GET', path: '/old' }],
      related_tests: [],
    },
  }))

  assert.match(html, /<h3>Routes in the older version<\/h3><span class="count">1<\/span>/)
  assert.match(html, /Why listed:<\/strong> Its Python code was deleted in this comparison/)
  assert.match(html, /<h3>Possible caller paths<\/h3><span class="count">0<\/span>/)
  assert.match(html, /No caller paths found\./)
})

test('lists directly changed tests only once', async () => {
  const html = await render(makeReport({
    changed_symbols: [{ id: 'tests/test_api.py::test_direct', changed_lines: [4] }],
    related_tests: ['tests/test_api.py::test_direct'],
  }))

  assert.match(html, /<h3>Additional tests to review<\/h3><span class="count">0<\/span>/)
  assert.match(html, /The linked tests were edited in this commit and appear under Changes above\./)
  assert.equal(html.split('test_direct<\/code>').length - 1, 1)
})

test('shows older-version caller steps and keeps exact line numbers expandable', async () => {
  const html = await render(makeReport({
    changed_symbols: [{
      id: 'service.py::old_function', change_type: 'deleted', changed_lines: [], removed_lines: [8, 9],
    }],
    evidence_paths: [
      { source: 'target', symbols: ['service.py::new_function', 'api.py::new_route'] },
      { source: 'base', symbols: ['service.py::old_function', 'api.py::route'] },
    ],
  }))

  assert.match(html, /<summary>Show line numbers<\/summary>/)
  assert.match(html, /Older version, removed lines: 8, 9/)
  assert.match(html, /Older version, before deletion/)
  assert.match(html, /<h4>Deleted code:/)
  assert.match(html, /Called by<\/span>/)
  assert.ok(html.indexOf('path-source">Older version, before deletion') < html.indexOf('path-source">Newer version'))
})

test('shows every changed root and keeps extra paths from each root available', async () => {
  const evidence_paths = Array.from({ length: 6 }, (_, index) => ({
    source: 'target', symbols: ['service.py::changed', `tests/test_service.py::test_${index}`],
  }))
  evidence_paths.push({
    source: 'target', symbols: ['service.py::other_change', 'api.py::route'],
  })
  const html = await render(makeReport({
    changed_symbols: [
      { id: 'service.py::changed', change_type: 'modified' },
      { id: 'service.py::other_change', change_type: 'modified' },
    ],
    evidence_paths,
  }))

  assert.match(html, /<h3>Possible caller paths<\/h3><span class="count">7<\/span>/)
  assert.match(html, /<summary>Show 5 more paths from this code<\/summary>/)
  assert.match(html, /other_change/)
  assert.equal(html.split('class="path-group"').length - 1, 2)
  assert.ok(html.indexOf('test_0') < html.indexOf('<details class="more-results">'))
  assert.ok(html.indexOf('test_1') > html.indexOf('<details class="more-results">'))
})

test('keeps additional tests available without making the report too long', async () => {
  const related_tests = Array.from({ length: 6 }, (_, index) => `tests/test_service.py::test_${index}`)
  const html = await render(makeReport({
    changed_symbols: [{ id: 'service.py::changed', change_type: 'modified' }],
    related_tests,
  }))

  assert.match(html, /<h3>Additional tests to review<\/h3><span class="count">6<\/span>/)
  assert.match(html, /<summary>Show 2 more tests<\/summary>/)
  assert.ok(html.indexOf('test_3') < html.indexOf('<summary>Show 2 more tests'))
  assert.ok(html.indexOf('test_4') > html.indexOf('<summary>Show 2 more tests'))
})

test('gives a concise result when only non-Python files changed', async () => {
  const html = await render(makeReport())

  assert.match(html, /No Python functions or classes changed/)
  assert.match(html, /Documentation and other non-Python files are outside this analysis/)
  assert.doesNotMatch(html, /Possible effects in the newer version/)
  assert.doesNotMatch(html, /Possible caller paths/)
})
