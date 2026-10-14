export const INITIAL_NODE_LIMIT = 20
export const MAX_NODE_LIMIT = 60

export function symbolLabel(identifier) {
  const [file, ...parts] = identifier.split('::')
  return { file, name: parts.join('::') || file }
}

export function nodeKey(source, identifier) {
  return JSON.stringify([source, identifier])
}

export function changedRoots(report) {
  return report.changed_symbols.map((symbol) => {
    const source = symbol.change_type === 'deleted' ? 'base' : 'target'
    const summary = source === 'base' ? report.historical_impact : report
    return {
      ...symbolLabel(symbol.id), ...symbol,
      source, key: nodeKey(source, symbol.id),
      isTest: summary.related_tests.includes(symbol.id),
    }
  })
}

export function initialRoot(report, roots = changedRoots(report)) {
  return roots.find((root) => !root.isTest && report.evidence_paths.some(
    (path) => path.source === root.source && path.symbols[0] === root.id,
  )) || roots[0]
}

export function buildImpactGraph(report, root) {
  const summary = root.source === 'base' ? report.historical_impact : report
  const changes = new Map(changedRoots(report).filter((item) => item.source === root.source)
    .map((item) => [item.id, item]))
  const nodes = new Map()
  const edges = new Map()
  const paths = []
  const pathSignatures = new Set()
  let excludedPaths = 0

  function ensureNode(identifier) {
    const key = nodeKey(root.source, identifier)
    if (!nodes.has(key)) {
      const change = changes.get(identifier)
      nodes.set(key, {
        key, id: identifier, source: root.source, ...symbolLabel(identifier),
        change, isRoot: identifier === root.id,
        isTest: summary.related_tests.includes(identifier),
        routes: summary.affected_routes.filter((route) => route.symbol_id === identifier),
      })
    }
    return key
  }

  const rootKey = ensureNode(root.id)
  for (const evidence of report.evidence_paths) {
    if (evidence.source !== root.source || evidence.symbols[0] !== root.id) continue
    const signature = JSON.stringify(evidence.symbols)
    if (pathSignatures.has(signature)) continue
    pathSignatures.add(signature)
    const identifiers = []
    let cyclic = false
    let valid = true
    for (const [index, identifier] of evidence.symbols.entries()) {
      if (identifier.endsWith(' (cycle)')) {
        const actual = identifier.slice(0, -8)
        if (index !== evidence.symbols.length - 1 || !identifiers.includes(actual)) {
          valid = false
          break
        }
        identifiers.push(actual)
        cyclic = true
      } else identifiers.push(identifier)
    }
    if (!valid) {
      excludedPaths += 1
      continue
    }
    const pathNodes = identifiers.map(ensureNode)
    const pathEdges = []
    for (let index = 1; index < pathNodes.length; index += 1) {
      const from = pathNodes[index - 1]
      const to = pathNodes[index]
      const key = JSON.stringify([from, to])
      if (!edges.has(key)) edges.set(key, { key, from, to, cycle: false })
      if (cyclic && index === pathNodes.length - 1) edges.get(key).cycle = true
      pathEdges.push(key)
    }
    paths.push({ index: paths.length, nodes: pathNodes, edges: pathEdges, cycle: cyclic })
  }

  const adjacent = new Map([...nodes.keys()].map((key) => [key, []]))
  for (const edge of edges.values()) adjacent.get(edge.from).push(edge.to)
  const order = [rootKey]
  const depths = new Map([[rootKey, 0]])
  for (let index = 0; index < order.length; index += 1) {
    const key = order[index]
    for (const next of adjacent.get(key)) {
      if (!depths.has(next)) {
        depths.set(next, depths.get(key) + 1)
        order.push(next)
      }
    }
  }
  return {
    rootKey, root, paths, excludedPaths,
    nodes: order.map((key) => ({ ...nodes.get(key), depth: depths.get(key) })),
    edges: [...edges.values()],
  }
}

export function graphView(graph, limit = INITIAL_NODE_LIMIT, highlightedNodes = [], focusedEdges = null) {
  const budget = Math.max(1, Math.min(MAX_NODE_LIMIT, limit))
  const visible = new Set([graph.rootKey])
  const known = new Set(graph.nodes.map((node) => node.key))
  for (const key of highlightedNodes) {
    if (visible.size >= budget && !visible.has(key)) break
    if (!known.has(key)) break
    visible.add(key)
  }
  if (focusedEdges === null) {
    for (const node of graph.nodes) {
      if (visible.size >= budget) break
      visible.add(node.key)
    }
  }
  const edgeSelection = focusedEdges === null ? null : new Set(focusedEdges)
  return {
    nodes: graph.nodes.filter((node) => visible.has(node.key)),
    edges: graph.edges.filter((edge) => visible.has(edge.from) && visible.has(edge.to) && (!edgeSelection || edgeSelection.has(edge.key))),
    hiddenCount: graph.nodes.length - visible.size,
    hiddenPathSteps: highlightedNodes.filter((key) => !visible.has(key)).length,
  }
}

export function connectionPaths(graph, key, preferredIndex = null) {
  const unique = new Map()
  for (const path of graph.paths) {
    const index = path.nodes.indexOf(key)
    if (index === -1) continue
    const signature = JSON.stringify(path.nodes.slice(0, index + 1))
    if (!unique.has(signature) || path.index === preferredIndex) unique.set(signature, path)
  }
  return [...unique.values()]
}
