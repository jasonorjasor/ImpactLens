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

  assert.match(html, /<h2>Affected routes<\/h2><span class="count">2<\/span>/)
  assert.match(html, /Changed directly/)
  assert.match(html, /Reached via calls/)
  assert.match(html, /<h2>Related tests<\/h2><span class="count">1<\/span>/)
  assert.match(html, /<h2>Affected code<\/h2><span class="count">1<\/span>/)
  assert.equal(html.split('tests/test_api.py::test_direct').length - 1, 1)
  assert.match(html, /<h2>Impact paths<\/h2><span class="count">1<\/span>/)
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

  assert.match(html, /<h2>Historical routes<\/h2><span class="count">1<\/span>/)
  assert.match(html, /Changed directly/)
  assert.match(html, /<h2>Impact paths<\/h2><span class="count">0<\/span>/)
  assert.match(html, /No caller paths found/)
})

test('lists directly changed tests only once', async () => {
  const html = await render(makeReport({
    changed_symbols: [{ id: 'tests/test_api.py::test_direct', changed_lines: [4] }],
    related_tests: ['tests/test_api.py::test_direct'],
  }))

  assert.match(html, /<h2>Related tests<\/h2><span class="count">0<\/span>/)
  assert.match(html, /Changed tests are listed above/)
  assert.equal(html.split('tests/test_api.py::test_direct').length - 1, 1)
})
