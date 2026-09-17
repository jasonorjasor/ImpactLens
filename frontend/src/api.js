export async function requestAnalysis(payload, send = fetch) {
  let response
  try {
    response = await send('/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
  } catch {
    throw new Error('Could not reach the analysis service. Make sure the API is running.')
  }

  let data
  try {
    data = await response.json()
  } catch {
    throw new Error('Could not read the analysis service response. Make sure the API is running.')
  }

  if (!response.ok) {
    throw new Error(typeof data.detail === 'string' ? data.detail : 'Analysis failed')
  }
  return data
}
