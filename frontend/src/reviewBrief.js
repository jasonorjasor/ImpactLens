import { nodeKey } from './impactGraph.js'

function withoutCycle(identifier) {
  return identifier.replace(/ \(cycle\)$/, '')
}

function snapshotBrief(report, source) {
  const summary = source === 'base' ? report.historical_impact : report
  const changed = new Set(report.changed_symbols
    .filter((item) => (item.change_type === 'deleted' ? 'base' : 'target') === source)
    .map((item) => item.id))
  const paths = report.evidence_paths.filter((path) => path.source === source && changed.has(path.symbols[0]))

  function evidence(identifiers, preferConnection = false) {
    const direct = identifiers.find((id) => changed.has(id))
    const matches = paths.filter((path) => path.symbols.some((id) => identifiers.includes(withoutCycle(id))))
    const external = matches.filter((path) => !identifiers.includes(path.symbols[0]))
    const roots = [...new Set(external.map((path) => path.symbols[0]))]
    const path = preferConnection ? external[0] || matches[0] : matches[0]
    const useDirect = direct && (!preferConnection || !external.length)
    const identifier = useDirect ? direct : path && identifiers.find((id) => path.symbols.map(withoutCycle).includes(id))
    const rootId = useDirect ? direct : path?.symbols[0]
    return {
      direct: Boolean(direct), roots,
      focus: rootId ? { source, rootKey: nodeKey(source, rootId), identifier } : null,
    }
  }

  const routeKeys = new Set()
  const routes = summary.affected_routes.filter((route) => {
    const key = JSON.stringify([route.symbol_id, route.method, route.path, route.registration])
    if (routeKeys.has(key)) return false
    routeKeys.add(key)
    return true
  }).map((route) => ({ ...route, ...evidence([route.symbol_id]) }))

  const files = new Map()
  for (const identifier of summary.related_tests) {
    const separator = identifier.lastIndexOf('::')
    const path = separator > 0 ? identifier.slice(0, separator) : identifier
    if (!files.has(path)) files.set(path, new Set())
    files.get(path).add(identifier)
  }
  const tests = [...files].map(([path, ids]) => ({ path, identifiers: [...ids], ...evidence([...ids], true) }))
  const directFirst = (left, right) => Number(right.direct) - Number(left.direct)
  return { routes: routes.sort(directFirst), tests: tests.sort(directFirst) }
}

export function buildReviewBrief(report) {
  return { target: snapshotBrief(report, 'target'), base: snapshotBrief(report, 'base') }
}

function portablePath(path) {
  return typeof path === 'string' && path.endsWith('.py') && !path.startsWith('/')
    && !/[\\:"\u0000-\u001f\u007f-\u009f\u2028\u2029]/.test(path)
    && path.split('/').every((part) => part && part !== '.' && part !== '..')
}

export function suggestedTestCommand(paths, shell) {
  const files = [...new Set(paths)]
  if (!files.length || !files.every(portablePath) || !['powershell', 'posix'].includes(shell)) return null
  const quote = shell === 'powershell'
    ? (value) => `'${value.replaceAll("'", "''")}'`
    : (value) => `'${value.replaceAll("'", "'\"'\"'")}'`
  const command = `python -m pytest -- ${files.map((file) => quote(`./${file}`)).join(' ')}`
  return command.length <= 16000 ? command : null
}
