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
    evidence_paths: [{ source: 'target', symbols: ['api.py::direct_route', 'service.py::caller'] }],
  }))

  assert.match(html, /<h3>Routes to review<\/h3><span class="count">2<\/span>/)
  assert.match(html, /Changed in this comparison/)
  assert.match(html, /Linked through calls/)
  assert.match(html, /<h3>Additional tests to review<\/h3><span class="count">1<\/span>/)
  assert.match(html, /<h3>Other code callers<\/h3><span class="count">1<\/span>/)
  assert.equal(html.split('test_direct</code>').length - 1, 1)
  assert.match(html, /<h3>Possible caller paths<\/h3><span class="count">1<\/span>/)
  assert.match(html, /Changed code<\/span>/)
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
  assert.match(html, /Deleted code in the older version/)
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
  assert.match(html, /Deleted code<\/span>/)
  assert.match(html, /Called by<\/span>/)
  assert.ok(html.indexOf('path-source">Older version, before deletion') < html.indexOf('path-source">Newer version'))
})

test('keeps long caller path lists available behind a disclosure', async () => {
  const evidence_paths = Array.from({ length: 6 }, (_, index) => ({
    source: 'target', symbols: ['service.py::changed', `tests/test_service.py::test_${index}`],
  }))
  const html = await render(makeReport({ evidence_paths }))

  assert.match(html, /<h3>Possible caller paths<\/h3><span class="count">6<\/span>/)
  assert.match(html, /<summary>Show 1 more paths<\/summary>/)
  assert.ok(html.indexOf('test_4') < html.indexOf('<details class="more-results">'))
  assert.ok(html.indexOf('test_5') > html.indexOf('<details class="more-results">'))
})
