const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'

export async function askAgent(question) {
  const response = await fetch(`${API_BASE_URL}/ask`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ question }),
  })

  if (!response.ok) {
    let message = `Request failed with status ${response.status}`

    try {
      const errorBody = await response.json()
      if (errorBody.detail) {
        message = typeof errorBody.detail === 'string'
          ? errorBody.detail
          : JSON.stringify(errorBody.detail)
      }
    } catch {
      // Keep the HTTP status message when the response is not JSON.
    }

    throw new Error(message)
  }

  const data = await response.json()
  if (typeof data.answer !== 'string') {
    throw new Error('The agent returned an invalid response.')
  }

  return data.answer
}
