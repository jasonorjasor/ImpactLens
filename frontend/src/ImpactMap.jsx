import { useEffect, useId, useMemo, useRef, useState } from 'react'
import SourceEvidence from './SourceEvidence.jsx'
import {
  buildImpactGraph, changedRoots, connectionPaths, graphView, initialRoot,
  INITIAL_NODE_LIMIT, MAX_NODE_LIMIT,
} from './impactGraph.js'

function changeLabel(change) {
  return ({ added: 'Added', deleted: 'Deleted', renamed: 'Renamed' })[change?.change_type] || 'Changed'
}

function Roles({ node }) {
  return (
    <span className="map-roles">
      {node.change && <span>{changeLabel(node.change)}</span>}
      {node.routes.length > 0 && <span>Route</span>}
      {node.isTest && <span>Test</span>}
      {!node.change && !node.routes.length && !node.isTest && <span>Code</span>}
    </span>
  )
}

function MapCanvas({ view, selectedKey, highlightedNodes, highlightedEdges, onSelect }) {
  const canvas = useRef(null)
  const buttons = useRef(new Map())
  const [geometry, setGeometry] = useState({ width: 0, height: 0, positions: new Map() })
  const marker = useId().replace(/:/g, '')
  const signature = JSON.stringify(view.nodes.map((node) => node.key))
  useEffect(() => {
    let frame
    function measure() {
      const bounds = canvas.current.getBoundingClientRect()
      const positions = new Map()
      for (const [key, element] of buttons.current) {
        const box = element.getBoundingClientRect()
        positions.set(key, {
          x: box.left - bounds.left, y: box.top - bounds.top, width: box.width, height: box.height,
        })
      }
      setGeometry({ width: bounds.width, height: bounds.height, positions })
    }
    function schedule() {
      cancelAnimationFrame(frame)
      frame = requestAnimationFrame(measure)
    }
    const observer = new ResizeObserver(schedule)
    observer.observe(canvas.current)
    for (const element of buttons.current.values()) observer.observe(element)
    measure()
    return () => { observer.disconnect(); cancelAnimationFrame(frame) }
  }, [signature])

  const layers = [...new Set(view.nodes.map((node) => node.depth))]
  return (
    <div className={`map-canvas ${highlightedEdges.size ? 'has-path' : ''}`} ref={canvas}>
      <svg width={geometry.width} height={geometry.height} className="map-connectors" aria-hidden="true">
        <defs>
          <marker id={`${marker}-arrow`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="context-stroke" />
          </marker>
        </defs>
        {view.edges.map((edge) => {
          const from = geometry.positions.get(edge.from)
          const to = geometry.positions.get(edge.to)
          if (!from || !to || !geometry.width) return null
          const start = { x: from.x + from.width / 2, y: from.y + from.height }
          const end = { x: to.x + to.width / 2, y: to.y }
          const backward = edge.cycle || end.y < start.y
          const side = Math.min(from.x, to.x) - 18
          const middle = (start.y + end.y) / 2
          const d = backward
            ? `M ${from.x} ${from.y + from.height / 2} C ${side} ${from.y + from.height / 2}, ${side} ${to.y + to.height / 2}, ${to.x} ${to.y + to.height / 2}`
            : `M ${start.x} ${start.y} C ${start.x} ${middle}, ${end.x} ${middle}, ${end.x} ${end.y - 3}`
          return <path key={edge.key} d={d} markerEnd={`url(#${marker}-arrow)`}
            className={`map-edge ${highlightedEdges.has(edge.key) ? 'is-highlighted' : ''} ${edge.cycle ? 'is-cycle' : ''}`} />
        })}
      </svg>
      {layers.map((depth) => (
        <div className="map-layer" key={depth}>
          <span className="map-layer-label">{depth === 0 ? 'Selected change' : 'Used by'}</span>
          <div className="map-layer-items">
            {view.nodes.filter((node) => node.depth === depth).map((node) => (
              <button type="button" key={node.key}
                ref={(element) => { if (element) buttons.current.set(node.key, element); else buttons.current.delete(node.key) }}
                className={`map-node ${highlightedNodes.has(node.key) ? 'on-path' : ''}`}
                aria-label={`Inspect ${node.name} in ${node.file}`}
                aria-pressed={selectedKey === node.key} onClick={() => onSelect(node.key)}
                title={`${node.name} in ${node.file}`}>
                <Roles node={node} />
                <code className="map-node-name">{node.name}</code>
                {node.routes.map((route) => <span className="map-route" key={`${route.method} ${route.path}`}>{route.method} {route.path}</span>)}
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

function RootMap({ report, root }) {
  const graph = useMemo(() => buildImpactGraph(report, root), [report, root])
  const [selectedKey, setSelectedKey] = useState(graph.rootKey)
  const [pathIndex, setPathIndex] = useState(null)
  const [wholePath, setWholePath] = useState(false)
  const [showContext, setShowContext] = useState(false)
  const [limit, setLimit] = useState(INITIAL_NODE_LIMIT)
  const node = graph.nodes.find((item) => item.key === selectedKey) || graph.nodes[0]
  const path = pathIndex === null ? null : graph.paths[pathIndex]
  const stop = path ? (wholePath ? path.nodes.length : path.nodes.indexOf(selectedKey) + 1) : 0
  const pathNodes = path?.nodes.slice(0, stop) || []
  const pathEdges = path?.edges.slice(0, Math.max(0, stop - 1)) || []
  const view = graphView(graph, limit, pathNodes, path && !showContext ? pathEdges : null)
  const options = connectionPaths(graph, selectedKey, pathIndex)
  const historical = root.source === 'base'

  function selectNode(key) {
    setSelectedKey(key)
    setPathIndex(key === graph.rootKey ? null : graph.paths.find((item) => item.nodes.includes(key))?.index ?? null)
    setWholePath(false)
    setShowContext(false)
  }

  function explorePath(value) {
    const index = value === '' ? null : Number(value)
    setPathIndex(index)
    setWholePath(true)
    setShowContext(false)
    setSelectedKey(index === null ? graph.rootKey : graph.paths[index].nodes.at(-1))
  }

  function reset() {
    setSelectedKey(graph.rootKey); setPathIndex(null); setWholePath(false); setShowContext(false); setLimit(INITIAL_NODE_LIMIT)
  }

  return (
    <div className="map-workspace">
      <div className="map-summary">
        <span className={`map-version ${historical ? 'is-historical' : ''}`}>
          {historical ? 'Older version · before deletion' : 'Newer version'}
        </span>
        <h3>Connections for <code>{root.name}</code></h3>
        <p className="map-desktop-help">Follow an arrow from code toward a possible caller. Select an item to inspect its connection.</p>
        <p className="map-mobile-help">Select a caller to inspect its connection to the changed code.</p>
        {historical && <p>The deleted code and its connections come from the older version. They may no longer exist.</p>}
      </div>
      <div className="map-toolbar">
        <div>
          <label htmlFor="explore-path">Explore a reported path</label>
          <select id="explore-path" value={pathIndex ?? ''} onChange={(event) => explorePath(event.target.value)}>
            <option value="">All visible connections</option>
            {graph.paths.map((item) => {
              const end = graph.nodes.find((entry) => entry.key === item.nodes.at(-1))
              return <option value={item.index} key={item.index}>{item.index + 1}. {end.name}{item.cycle ? ' (cycle)' : ''}</option>
            })}
          </select>
        </div>
        <button type="button" className="map-plain-button" onClick={reset}>Reset map</button>
      </div>
      <p className="map-count" aria-live="polite">
        {path && !showContext && 'Focused connection · '}Showing {view.nodes.length} of {graph.nodes.length} resolved code {graph.nodes.length === 1 ? 'item' : 'items'} · {graph.paths.length} reported {graph.paths.length === 1 ? 'path' : 'paths'}
      </p>
      {path && <button type="button" className="map-plain-button map-context-button" onClick={() => setShowContext(!showContext)}>
        {showContext ? 'Focus selected connection' : 'Show surrounding connections'}
      </button>}
      {graph.edges.length === 0 && <p className="map-note">No caller connections were resolved for this change. It may still have dependencies that source analysis cannot find.</p>}
      {graph.excludedPaths > 0 && <p className="map-note">{graph.excludedPaths} reported {graph.excludedPaths === 1 ? 'path cannot' : 'paths cannot'} be drawn. Inspect the full evidence in Report.</p>}
      {view.hiddenPathSteps > 0 && <p className="map-note">The selected path continues beyond this view. Its full steps are available in Report.</p>}
      {view.edges.some((edge) => edge.cycle) && <p className="map-count">A dashed arrow closes a cycle back to an earlier item.</p>}
      <div className="map-scroll">
        <MapCanvas view={view} selectedKey={selectedKey} highlightedNodes={new Set(pathNodes)}
          highlightedEdges={new Set(pathEdges)} onSelect={selectNode} />
      </div>
      <div className="map-mobile-list">
        <ul>
          {view.nodes.map((item) => (
            <li key={item.key}>
              <span>{item.isRoot ? 'Selected change' : 'Connected caller'}</span>
              <button type="button" className="map-node" aria-pressed={selectedKey === item.key}
                aria-label={`Inspect ${item.name} in ${item.file}`} onClick={() => selectNode(item.key)}>
                <Roles node={item} /><code>{item.name}</code>
                {item.routes.map((route) => <span className="map-route" key={`${route.method} ${route.path}`}>{route.method} {route.path}</span>)}
              </button>
              {!item.isRoot && <p className="map-list-reason">May call {view.edges.filter((edge) => edge.to === item.key)
                .map((edge) => graph.nodes.find((entry) => entry.key === edge.from).name).join(', ')}.</p>}
            </li>
          ))}
        </ul>
      </div>
      {view.hiddenCount > 0 && <div className="map-expansion">
        <span>{view.hiddenCount} {view.hiddenCount === 1 ? 'code item is' : 'code items are'} outside this view.</span>
        {path && !showContext && view.hiddenPathSteps > 0 && limit < MAX_NODE_LIMIT &&
          <button type="button" className="map-plain-button" onClick={() => setLimit(Math.min(MAX_NODE_LIMIT, limit + INITIAL_NODE_LIMIT))}>Show more path steps</button>}
        {path && !showContext ? <span>Show surrounding connections to explore the other callers.</span> : limit < MAX_NODE_LIMIT
          ? <button type="button" className="map-plain-button" onClick={() => setLimit(Math.min(MAX_NODE_LIMIT, limit + INITIAL_NODE_LIMIT))}>Show more connections</button>
          : <span>Use Report to inspect the remaining evidence.</span>}
      </div>}
      <section className="map-details" aria-label="Selected item details">
        <div className="map-details-heading"><h4>Selected item</h4><Roles node={node} /></div>
        <code className="map-detail-name">{node.name}</code>
        <dl><div><dt>File</dt><dd><code>{node.file}</code></dd></div>
          <div><dt>Version</dt><dd>{historical ? 'Older, before deletion' : 'Newer'}</dd></div>
          {node.change?.previous_id && <div><dt>Previous ID</dt><dd><code>{node.change.previous_id}</code></dd></div>}
        </dl>
        <p>{node.isRoot
          ? (historical ? 'This code was deleted. The map shows its former callers.' : 'This code changed in the newer version. Select a caller to see how it connects.')
          : <>This code appears on a reported caller path from <code>{root.name}</code>.</>}</p>
        {node.routes.map((route) => <p key={`${route.method} ${route.path}`}>{route.registration === 'declared' ? 'Declares' : 'Handles'} <code>{route.method} {route.path}</code>.{route.registration === 'declared' && ' App registration was not found; this may be a partial address.'}</p>)}
        {node.isTest && <p>This is a test identified by source analysis. ImpactLens has not run it.</p>}
        {path && <>
          {options.length > 1 && <div className="map-path-choice"><label htmlFor="connection-path">Alternative paths to this item</label>
            <select id="connection-path" value={pathIndex} onChange={(event) => { setPathIndex(Number(event.target.value)); setWholePath(false); setShowContext(false) }}>
              {options.map((item, index) => <option key={item.index} value={item.index}>Connection {index + 1} of {options.length}</option>)}
            </select>
          </div>}
          <p className="map-path-caption">Highlighted connection · each next step may use the step before it</p>
          <ol className="map-detail-path">
            {pathNodes.slice(0, 8).map((key, index) => <li key={`${key}-${index}`}>
              <span>{index === 0 ? 'Changed code' : 'Used by'}</span>
              <code>{graph.nodes.find((item) => item.key === key).name}</code>
              {path.cycle && index === path.nodes.length - 1 && <span>Cycle returns here</span>}
            </li>)}
          </ol>
          {pathNodes.length > 8 && <details className="more-results">
            <summary>Show the remaining {pathNodes.length - 8} path steps</summary>
            <ol className="map-detail-path" start={9}>
              {pathNodes.slice(8).map((key, index) => <li key={`${key}-${index}`}>
                <span>Used by</span><code>{graph.nodes.find((item) => item.key === key).name}</code>
                {path.cycle && index + 8 === path.nodes.length - 1 && <span>Cycle returns here</span>}
              </li>)}
            </ol>
          </details>}
        </>}
        <SourceEvidence report={report} source={root.source} identifier={node.id}
          identifiers={pathNodes.map((key) => graph.nodes.find((item) => item.key === key).id)} />
        {node.change && (node.change.changed_lines?.length > 0 || node.change.removed_lines?.length > 0) &&
          <details className="line-details"><summary>Show changed line numbers</summary>
            {node.change.changed_lines?.length > 0 && <p>Newer version: {node.change.changed_lines.join(', ')}</p>}
            {node.change.removed_lines?.length > 0 && <p>Older version, removed: {node.change.removed_lines.join(', ')}</p>}
          </details>}
      </section>
    </div>
  )
}

export default function ImpactMap({ report }) {
  const roots = useMemo(() => changedRoots(report), [report])
  const [rootKey, setRootKey] = useState(() => initialRoot(report, roots)?.key)
  const root = roots.find((item) => item.key === rootKey) || roots[0]
  if (!root) return null
  return (
    <section className="impact-map" aria-label="Impact map">
      <nav className="map-roots" aria-label="Changed code">
        <h3>Changed code <span className="count">{roots.length}</span></h3>
        <p>Select a change to explore.</p>
        <div className="map-root-select"><label htmlFor="changed-code">Changed code</label>
          <select id="changed-code" value={root.key} onChange={(event) => setRootKey(event.target.value)}>
            {roots.map((item) => <option key={item.key} value={item.key}>{changeLabel(item)} · {item.name} — {item.file}</option>)}
          </select>
        </div>
        <ul className="map-root-list">
          {roots.map((item) => <li key={item.key}><button type="button"
            aria-label={`Explore ${item.name} in ${item.file}`} aria-pressed={root.key === item.key}
            onClick={() => setRootKey(item.key)}>
            <span className="map-root-change">{changeLabel(item)}{item.isTest ? ' · Test' : ''}</span>
            <code>{item.name}</code><span className="map-root-file">{item.file}</span>
          </button></li>)}
        </ul>
      </nav>
      <RootMap key={root.key} report={report} root={root} />
    </section>
  )
}
