import assert from 'node:assert/strict'
import test from 'node:test'
import { buildImpactGraph, changedRoots, connectionPaths, graphView, initialRoot, nodeKey } from '../src/impactGraph.js'

function report(overrides = {}) {
  return {
    changed_symbols: [{ id: 'service.py::changed', changed_lines: [2] }],
    affected_routes: [], related_tests: [],
    historical_impact: { affected_routes: [], related_tests: [] },
    evidence_paths: [], ...overrides,
  }
}

function graph(data) { return buildImpactGraph(data, changedRoots(data)[0]) }

test('merges shared connections while preserving reported path alternatives and input', () => {
  const data = report({
    evidence_paths: [
      { source: 'target', symbols: ['service.py::changed', 'api.py::route', 'tests/test_api.py::a'] },
      { source: 'target', symbols: ['service.py::changed', 'api.py::route', 'tests/test_api.py::b'] },
      { source: 'target', symbols: ['service.py::changed', 'api.py::route', 'tests/test_api.py::a'] },
    ],
  })
  const original = structuredClone(data)
  const result = graph(data)
  assert.equal(result.nodes.length, 4)
  assert.equal(result.edges.length, 3)
  assert.equal(result.paths.length, 2)
  assert.equal(result.paths[0].edges[0], result.paths[1].edges[0])
  assert.equal(connectionPaths(result, nodeKey('target', 'api.py::route')).length, 1)
  assert.equal(connectionPaths(result, nodeKey('target', 'api.py::route'), 1)[0].index, 1)
  assert.deepEqual(result.edges[0], {
    key: JSON.stringify([nodeKey('target', 'service.py::changed'), nodeKey('target', 'api.py::route')]),
    from: nodeKey('target', 'service.py::changed'), to: nodeKey('target', 'api.py::route'), cycle: false,
  })
  assert.deepEqual(data, original)
})

test('uses older roles and paths for deleted code and excludes other roots and versions', () => {
  const data = report({
    changed_symbols: [{ id: 'service.py::changed', change_type: 'deleted' }],
    related_tests: ['api.py::same'],
    historical_impact: {
      affected_routes: [{ symbol_id: 'api.py::same', method: 'POST', path: '/old' }], related_tests: [],
    },
    evidence_paths: [
      { source: 'base', symbols: ['service.py::changed', 'api.py::same'] },
      { source: 'target', symbols: ['service.py::changed', 'api.py::same'] },
      { source: 'base', symbols: ['other.py::changed', 'other.py::caller'] },
    ],
  })
  const result = graph(data)
  assert.equal(result.paths.length, 1)
  assert.equal(result.nodes.length, 2)
  assert.equal(result.nodes[1].key, nodeKey('base', 'api.py::same'))
  assert.notEqual(result.nodes[1].key, nodeKey('target', 'api.py::same'))
  assert.equal(result.nodes[1].routes[0].path, '/old')
  assert.equal(result.nodes[1].isTest, false)
})

test('attaches multiple route and test roles without inventing nodes or helper-test roles', () => {
  const data = report({
    affected_routes: [
      { symbol_id: 'service.py::changed', method: 'GET', path: '/a' },
      { symbol_id: 'service.py::changed', method: 'POST', path: '/b' },
      { symbol_id: 'api.py::unconnected', method: 'GET', path: '/unconnected' },
    ],
    related_tests: ['service.py::changed'],
    evidence_paths: [{ source: 'target', symbols: ['service.py::changed', 'tests/test_api.py::helper'] }],
  })
  const result = graph(data)
  assert.equal(result.nodes.length, 2)
  assert.equal(result.nodes[0].routes.length, 2)
  assert.equal(result.nodes[0].isTest, true)
  assert.ok(result.nodes[0].change)
  assert.equal(result.nodes[1].isTest, false)
})

test('keeps an isolated change visible and chooses a connected non-test root initially', () => {
  const data = report({
    changed_symbols: [{ id: 'tests/test_a.py::test_a' }, { id: 'service.py::changed' }],
    related_tests: ['tests/test_a.py::test_a'],
    evidence_paths: [{ source: 'target', symbols: ['service.py::changed', 'api.py::route'] }],
  })
  assert.equal(initialRoot(data).id, 'service.py::changed')
  const isolated = buildImpactGraph(data, changedRoots(data)[0])
  assert.equal(isolated.nodes.length, 1)
  assert.equal(isolated.edges.length, 0)
  assert.equal(initialRoot(report({ changed_symbols: [] })), undefined)
})

test('closes cycles on real items and exposes unsupported cycle evidence', () => {
  const result = graph(report({ evidence_paths: [
    { source: 'target', symbols: ['service.py::changed', 'api.py::route', 'service.py::changed (cycle)'] },
    { source: 'target', symbols: ['service.py::changed', 'missing.py::unknown (cycle)'] },
  ] }))
  assert.equal(result.nodes.length, 2)
  assert.equal(result.edges.length, 2)
  assert.equal(result.edges[1].to, result.rootKey)
  assert.equal(result.edges[1].cycle, true)
  assert.deepEqual(result.paths[0].nodes, [result.rootKey, nodeKey('target', 'api.py::route'), result.rootKey])
  assert.equal(result.excludedPaths, 1)
  assert.equal(result.paths.length, 1)
})

test('bounds a branching map, reserves selected path space and discloses long-path continuation', () => {
  const paths = Array.from({ length: 70 }, (_, index) => ({
    source: 'target', symbols: ['service.py::changed', `callers.py::caller_${index}`],
  }))
  const result = graph(report({ evidence_paths: paths }))
  const view = graphView(result, 20, result.paths[69].nodes)
  assert.equal(view.nodes.length, 20)
  assert.equal(view.hiddenCount, 51)
  assert.ok(view.nodes.some((node) => node.id === 'callers.py::caller_69'))
  const focused = graphView(result, 20, result.paths[69].nodes, result.paths[69].edges)
  assert.equal(focused.nodes.length, 2)
  assert.equal(focused.edges.length, 1)
  assert.equal(focused.hiddenCount, 69)
  assert.equal(graphView(result, 100).nodes.length, 60)

  const chain = ['service.py::changed', ...Array.from({ length: 70 }, (_, i) => `deep.py::step_${i}`)]
  const deep = graph(report({ evidence_paths: [{ source: 'target', symbols: chain }] }))
  const partial = graphView(deep, 60, deep.paths[0].nodes)
  assert.equal(partial.hiddenPathSteps, 11)
  assert.equal(partial.edges.length, 59)
  assert.equal(partial.edges.at(-1).to, nodeKey('target', 'deep.py::step_58'))
})
