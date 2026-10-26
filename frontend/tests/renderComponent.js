import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'

export async function renderComponent(modulePath, exportName, props) {
  const server = await createServer({
    server: { middlewareMode: true, hmr: false, ws: false },
    appType: 'custom',
  })
  try {
    const component = (await server.ssrLoadModule(modulePath))[exportName]
    return renderToStaticMarkup(createElement(component, props))
  } finally { await server.close() }
}
