import assert from 'node:assert/strict'
import test from 'node:test'
import { requestAnalysis } from '../src/api.js'

const payload = {
  repository: 'https://github.com/owner/repository',
  base_commit: 'base',
  target_commit: 'target',
}

test('sends the analysis request and returns its report', async () => {
  let request
  const report = { changed_symbols: [] }
  const result = await requestAnalysis(payload, async (url, options) => {
    request = { url, options }
    return Response.json(report)
  })

  assert.deepEqual(result, report)
  assert.equal(request.url, '/analyze')
  assert.equal(request.options.method, 'POST')
  assert.deepEqual(JSON.parse(request.options.body), payload)
})

test('shows a backend error without replacing its message', async () => {
  const send = async () => Response.json(
    { detail: "Could not find or fetch commit 'missing'." },
    { status: 400 },
  )

  await assert.rejects(
    requestAnalysis(payload, send),
    { message: "Could not find or fetch commit 'missing'." },
  )
})

test('explains an unavailable service instead of showing a JSON error', async () => {
  const send = async () => new Response('', { status: 500 })

  await assert.rejects(
    requestAnalysis(payload, send),
    { message: 'Could not read the analysis service response. Make sure the API is running.' },
  )
})

test('explains a failed connection', async () => {
  const send = async () => { throw new TypeError('Failed to fetch') }

  await assert.rejects(
    requestAnalysis(payload, send),
    { message: 'Could not reach the analysis service. Make sure the API is running.' },
  )
})
