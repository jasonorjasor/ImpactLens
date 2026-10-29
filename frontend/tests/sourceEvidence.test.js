import assert from 'node:assert/strict'
import test from 'node:test'
import { renderComponent } from './renderComponent.js'

async function render(report, identifiers, source = 'target') {
  return renderComponent('/src/SourceEvidence.jsx', 'default', { report, source, identifier: identifiers.at(-1), identifiers })
}

const ids = ['service.py::work', 'caller.py::run']
function report() {
  return {
    schema_version: 2, repository_url: 'https://github.com/owner/repo',
    resolved_commits: { base: 'a'.repeat(40), target: 'b'.repeat(40) },
    symbol_locations: [{ source: 'target', id: ids[1], path: 'caller.py', line_start: 3, line_end: 5 }],
    call_sites: [{ source: 'target', caller_id: ids[1], callee_id: ids[0], path: 'caller.py', line: 4, line_end: 4, column: 11, resolution: 'import', code: 'return compute()', code_truncated: false }],
  }
}

test('shows the actual caller, match basis, definition and pinned source', async () => {
  const html = await render(report(), ids)
  assert.match(html, /run<\/code> calls <code>work/)
  assert.match(html, /Matched through an imported name/)
  assert.match(html, /return compute\(\)/)
  assert.match(html, /Selected definition/)
  assert.ok(html.includes(`/blob/${'b'.repeat(40)}/caller.py#L4`))
  assert.ok(html.includes(`/blob/${'b'.repeat(40)}/caller.py#L3-L5`))
})

test('schema 3 labels dependency declarations without presenting them as direct calls', async () => {
  const data = report()
  data.schema_version = 3
  data.call_sites[0] = { ...data.call_sites[0], relationship: 'fastapi_dependency', code: 'def run(user=Depends(work)):' }
  const html = await render(data, ids)
  assert.match(html, /run<\/code> depends on <code>work/)
  assert.match(html, /Declared with Depends/)
  assert.match(html, /not a direct call in the function body/)
  assert.doesNotMatch(html, /run<\/code> calls <code>work/)
  assert.ok(html.includes(`/blob/${'b'.repeat(40)}/caller.py#L4`))
})

test('uses historical evidence and never substitutes a newer-version call site', async () => {
  const data = report()
  data.call_sites.push({ ...data.call_sites[0], source: 'base', line: 8, line_end: 9, resolution: 'local', code: 'return old_work(' })
  const html = await render(data, ids, 'base')
  assert.match(html, /Older version · before deletion/)
  assert.match(html, /Matched by a name in the same file/)
  assert.ok(html.includes(`/blob/${'a'.repeat(40)}/caller.py#L8-L9`))
  assert.doesNotMatch(html, /compute\(\)/)
})

test('escapes source text, discloses repeated sites and missing evidence', async () => {
  const data = report()
  data.call_sites[0].code = '<script>alert(1)</script>'
  data.call_sites.push({ ...data.call_sites[0], column: 30 }, { ...data.call_sites[0], line: 5 })
  const html = await render(data, [...ids, 'unknown.py::caller'])
  assert.match(html, /&lt;script&gt;/)
  assert.doesNotMatch(html, /<script>/)
  assert.match(html, /Show 1 more call site/)
  assert.match(html, /Call-site evidence is unavailable for this step/)
})

test('old reports and working-tree evidence do not invent commit links', async () => {
  assert.match(await render({}, ids), /Source evidence is unavailable in this older report/)
  const data = report()
  data.resolved_commits.target = null
  delete data.repository_url
  const html = await render(data, ids)
  assert.match(html, /saved working-tree files/)
  assert.doesNotMatch(html, /href=/)
})

test('duplicate definitions remain visible instead of selecting the first silently', async () => {
  const data = report()
  data.symbol_locations.push({ ...data.symbol_locations[0], line_start: 8, line_end: 10 })
  const html = await render(data, ids)
  assert.match(html, /Multiple definitions share this name/)
  assert.ok(html.includes('caller.py#L3-L5'))
  assert.ok(html.includes('caller.py#L8-L10'))
})
