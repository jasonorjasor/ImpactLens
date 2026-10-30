import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import test from 'node:test'
import { buildReviewBrief, suggestedTestCommand } from '../src/reviewBrief.js'
import { renderComponent } from './renderComponent.js'

function report(overrides = {}) {
  return {
    changed_symbols: [{ id: 'auth.py::user' }],
    affected_routes: [{ symbol_id: 'routes.py::me', method: 'GET', path: '/users/me', registration: 'registered' }],
    related_tests: ['tests/test_routes.py::TestRoutes.test_me', 'tests/test_routes.py::test_other'],
    evidence_paths: [{ source: 'target', symbols: ['auth.py::user', 'routes.py::me', 'tests/test_routes.py::TestRoutes.test_me'] }],
    historical_impact: { affected_routes: [], related_tests: [] },
    ...overrides,
  }
}

test('groups test files and links review actions to a real source-qualified changed root', () => {
  const data = report()
  const original = JSON.stringify(data)
  const brief = buildReviewBrief(data)
  assert.equal(brief.target.tests.length, 1)
  assert.equal(brief.target.tests[0].path, 'tests/test_routes.py')
  assert.deepEqual(brief.target.tests[0].focus, { source: 'target', rootKey: '["target","auth.py::user"]', identifier: 'tests/test_routes.py::TestRoutes.test_me' })
  assert.deepEqual(brief.target.routes[0].roots, ['auth.py::user'])
  assert.equal(JSON.stringify(data), original)
})

test('keeps historical files out of newer-version suggestions', () => {
  const brief = buildReviewBrief(report({
    changed_symbols: [{ id: 'auth.py::user', change_type: 'deleted' }],
    affected_routes: [], related_tests: [],
    historical_impact: { affected_routes: [{ symbol_id: 'routes.py::me', method: 'GET', path: '/old' }], related_tests: ['tests/test_old.py::test_old'] },
    evidence_paths: [{ source: 'base', symbols: ['auth.py::user', 'routes.py::me', 'tests/test_old.py::test_old'] }],
  }))
  assert.deepEqual(brief.target.tests, [])
  assert.deepEqual(brief.target.routes, [])
  assert.equal(brief.base.routes[0].focus.rootKey, '["base","auth.py::user"]')
  assert.equal(brief.base.tests[0].path, 'tests/test_old.py')
  assert.equal(suggestedTestCommand(brief.target.tests.map((item) => item.path), 'powershell'), null)
})

test('prefers direct changes in lists but follows useful code connections for edited test files', () => {
  const brief = buildReviewBrief(report({
    changed_symbols: [{ id: 'auth.py::user' }, { id: 'routes.py::direct' }, { id: 'tests/test_routes.py::TestRoutes.test_me' }],
    affected_routes: [...report().affected_routes, { symbol_id: 'routes.py::direct', method: 'POST', path: '/direct' }],
  }))
  assert.equal(brief.target.routes[0].symbol_id, 'routes.py::direct')
  assert.equal(brief.target.routes[0].focus.identifier, 'routes.py::direct')
  assert.equal(brief.target.tests[0].direct, true)
  assert.equal(brief.target.tests[0].focus.rootKey, '["target","auth.py::user"]')
})

test('a file shared by both snapshots remains eligible through its newer-version test', () => {
  const brief = buildReviewBrief(report({
    changed_symbols: [{ id: 'old.py::removed', change_type: 'deleted' }, { id: 'new.py::changed' }],
    affected_routes: [], related_tests: ['tests/test_shared.py::test_new'],
    historical_impact: { affected_routes: [], related_tests: ['tests/test_shared.py::test_old'] },
    evidence_paths: [
      { source: 'base', symbols: ['old.py::removed', 'tests/test_shared.py::test_old'] },
      { source: 'target', symbols: ['new.py::changed', 'tests/test_shared.py::test_new'] },
    ],
  }))
  assert.equal(brief.target.tests[0].focus.source, 'target')
  assert.equal(brief.target.tests[0].focus.identifier, 'tests/test_shared.py::test_new')
  assert.equal(brief.base.tests[0].focus.source, 'base')
  assert.equal(brief.base.tests[0].focus.identifier, 'tests/test_shared.py::test_old')
  assert.equal(suggestedTestCommand(brief.target.tests.map((item) => item.path), 'posix'), "python -m pytest -- './tests/test_shared.py'")
})

test('does not invent a map focus without matching changed code and handles cycle markers', () => {
  const data = report({ evidence_paths: [] })
  assert.equal(buildReviewBrief(data).target.routes[0].focus, null)
  data.evidence_paths = [{ source: 'target', symbols: ['auth.py::user', 'routes.py::me', 'auth.py::user (cycle)'] }]
  assert.equal(buildReviewBrief(data).target.routes[0].focus.identifier, 'routes.py::me')
  data.evidence_paths[0].symbols[0] = 'unrelated.py::caller'
  assert.equal(buildReviewBrief(data).target.routes[0].focus, null)
})

test('deduplicates repeated symbols and file paths without guessing pytest class node IDs', () => {
  const data = report({ related_tests: ['tests/test_routes.py::TestRoutes.test_me', 'tests/test_routes.py::TestRoutes.test_me'] })
  data.affected_routes.push({ ...data.affected_routes[0] })
  const brief = buildReviewBrief(data)
  assert.equal(brief.target.routes.length, 1)
  assert.deepEqual(brief.target.tests[0].identifiers, ['tests/test_routes.py::TestRoutes.test_me'])
  assert.equal(suggestedTestCommand([brief.target.tests[0].path, brief.target.tests[0].path], 'posix'), "python -m pytest -- './tests/test_routes.py'")
})

test('quotes spaces, apostrophes and shell metacharacters as literal file names', () => {
  const path = "tests/test user's $HOME;$(echo NO).py"
  assert.equal(suggestedTestCommand([path], 'powershell'), "python -m pytest -- './tests/test user''s $HOME;$(echo NO).py'")
  assert.equal(suggestedTestCommand([path], 'posix'), "python -m pytest -- './tests/test user'\"'\"'s $HOME;$(echo NO).py'")
  assert.equal(suggestedTestCommand(['@args.py', '-options.py'], 'posix'), "python -m pytest -- './@args.py' './-options.py'")
})

test('rejects unsupported paths as a whole instead of silently copying a partial suggestion', () => {
  for (const path of ['../outside.py', '/tmp/test.py', 'C:/test.py', 'tests\\test.py', 'tests/test.py\nINJECT', 'tests//test.py', 'tests/./test.py', 'tests/test.py::test_run', 'tests/test"quote.py']) {
    assert.equal(suggestedTestCommand(['tests/test_ok.py', path], 'powershell'), null, path)
  }
  assert.equal(suggestedTestCommand(['tests/test_ok.py'], 'cmd'), null)
  assert.equal(suggestedTestCommand(Array.from({ length: 400 }, (_, index) => `tests/test_${index}_${'x'.repeat(40)}.py`), 'powershell'), null)
})

test('PowerShell command preserves literal arguments at a native executable boundary', { skip: process.platform !== 'win32' }, () => {
  const paths = ["tests/test user's $HOME;$(Write-Error INJECTED).py", '@args.py', '-options.py']
  const command = suggestedTestCommand(paths, 'powershell')
  const probe = "python -c 'import json,sys;print(json.dumps(sys.argv[1:]))'"
  const result = spawnSync('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', command.replace('python -m pytest', probe)], { encoding: 'utf8' })
  assert.equal(result.status, 0, result.stderr)
  assert.deepEqual(JSON.parse(result.stdout), ['--', ...paths.map((path) => `./${path}`)])
})

test('POSIX command preserves literal arguments at a native executable boundary', { skip: process.platform === 'win32' }, () => {
  const paths = ["tests/test user's $HOME;$(echo INJECTED).py", '@args.py', '-options.py']
  const command = suggestedTestCommand(paths, 'posix')
  const probe = "node -e 'process.stdout.write(JSON.stringify(process.argv.slice(1)))'"
  const result = spawnSync('sh', ['-c', command.replace('python -m pytest', probe)], { encoding: 'utf8' })
  assert.equal(result.status, 0, result.stderr)
  assert.deepEqual(JSON.parse(result.stdout), paths.map((path) => `./${path}`))
})

test('review focus opens the matching map item and its real dependency evidence', async () => {
  const data = {
    ...report(), schema_version: 3,
    resolved_commits: { base: 'a'.repeat(40), target: 'b'.repeat(40) },
    symbol_locations: [],
    call_sites: [{ source: 'target', caller_id: 'routes.py::me', callee_id: 'auth.py::user', path: 'routes.py', line: 5, line_end: 5, column: 12, resolution: 'import', relationship: 'fastapi_dependency', code: 'def me(user=Depends(user)):' }],
  }
  const html = await renderComponent('/src/ImpactMap.jsx', 'default', { report: data, initialFocus: buildReviewBrief(data).target.routes[0].focus })
  assert.match(html, /aria-label="Inspect me in routes.py" aria-pressed="true"/)
  assert.match(html, /me<\/code> depends on <code>user/)
  assert.match(html, /Declared with Depends/)
  assert.match(html, /Highlighted connection/)
  assert.match(html, /class="map-list-reason">May use/)
})

test('historical review focus pins the older map and does not show target call evidence', async () => {
  const data = {
    ...report({
      changed_symbols: [{ id: 'auth.py::user', change_type: 'deleted' }, { id: 'other.py::changed' }],
      affected_routes: [], related_tests: [],
      historical_impact: { affected_routes: report().affected_routes, related_tests: [] },
      evidence_paths: [{ source: 'base', symbols: ['auth.py::user', 'routes.py::me'] }],
    }), schema_version: 3,
    resolved_commits: { base: 'a'.repeat(40), target: 'b'.repeat(40) }, symbol_locations: [],
    call_sites: [{ source: 'base', caller_id: 'routes.py::me', callee_id: 'auth.py::user', path: 'routes.py', line: 5, line_end: 5, column: 12, resolution: 'import', code: 'return OLD_user()' }, { source: 'target', caller_id: 'routes.py::me', callee_id: 'auth.py::user', path: 'routes.py', line: 6, line_end: 6, column: 12, resolution: 'import', code: 'return NEW_user()' }],
  }
  const html = await renderComponent('/src/ImpactMap.jsx', 'default', { report: data, initialFocus: buildReviewBrief(data).base.routes[0].focus })
  assert.match(html, /Older version · before deletion/)
  assert.match(html, /OLD_user/)
  assert.doesNotMatch(html, /NEW_user/)
})

test('brief explains missing connections without implying absent coverage', async () => {
  const html = await renderComponent('/src/ReviewBrief.jsx', 'default', { report: report({ affected_routes: [], related_tests: [] }) })
  assert.match(html, /Start your review/)
  assert.match(html, /This does not mean the change is untested/)
  assert.doesNotMatch(html, /Copy command/)
})

test('deletion-only brief opens former connections instead of starting with empty current lists', async () => {
  const data = report({
    changed_symbols: [{ id: 'auth.py::user', change_type: 'deleted' }], affected_routes: [], related_tests: [],
    historical_impact: { affected_routes: report().affected_routes, related_tests: ['tests/test_old.py::test_old'] },
    evidence_paths: [{ source: 'base', symbols: ['auth.py::user', 'routes.py::me', 'tests/test_old.py::test_old'] }],
  })
  const html = await renderComponent('/src/ReviewBrief.jsx', 'default', { report: data })
  assert.match(html, /class="brief-history" open=""/)
  assert.match(html, /1 former route, 1 test file/)
  assert.match(html, /Start with the older-version evidence/)
  assert.doesNotMatch(html, /Suggested pytest command/)
  assert.match(html, /may no longer exist/)
})

test('brief exposes partial addresses, limits long lists and escapes paths and descriptions', async () => {
  const data = report({ affected_routes: Array.from({ length: 5 }, (_, index) => ({ symbol_id: 'routes.py::me', method: 'GET', path: `/route-${index}<script>`, registration: 'declared' })) })
  const html = await renderComponent('/src/ReviewBrief.jsx', 'default', { report: data })
  assert.match(html, /Show 2 more routes/)
  assert.match(html, /its app address may be partial/)
  assert.match(html, /&lt;script&gt;/)
  assert.doesNotMatch(html, /<script>/)
  assert.match(html, /not an exhaustive review checklist/)
})
