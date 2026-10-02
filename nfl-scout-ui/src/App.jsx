import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { askAgent } from './services/api'
import './App.css'

function App() {
  const [question, setQuestion] = useState('')
  const [messages, setMessages] = useState([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')

  async function handleSubmit(event) {
    event.preventDefault()

    const cleanedQuestion = question.trim()
    if (!cleanedQuestion || isLoading) {
      return
    }

    setMessages((current) => [
      ...current,
      { id: crypto.randomUUID(), role: 'user', text: cleanedQuestion },
    ])
    setQuestion('')
    setError('')
    setIsLoading(true)

    try {
      const answer = await askAgent(cleanedQuestion)
      setMessages((current) => [
        ...current,
        { id: crypto.randomUUID(), role: 'assistant', text: answer },
      ])
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : 'The scouting agent could not be reached.',
      )
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <main className="app-shell">
      <header className="app-header">
        <p className="eyebrow">NFL scouting workspace</p>
        <h1>Scouting Agent</h1>
        <p className="subtitle">
          Ask about schedules, team performance, player leaders, or matchups.
        </p>
      </header>

      <section className="chat-panel" aria-label="Scouting conversation">
        <div className="messages" aria-live="polite">
          {messages.length === 0 && (
            <div className="empty-state">
              <h2>Start with a scouting question</h2>
              <p>Try “Compare the Seahawks and 49ers in 2026.”</p>
            </div>
          )}

          {messages.map((message) => (
  <article className={`message ${message.role}`} key={message.id}>
    <span className="message-label">
      {message.role === 'user' ? 'You' : 'Scout agent'}
    </span>

    {message.role === 'assistant' ? (
      <div className="markdown-content">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>
          {message.text}
        </ReactMarkdown>
      </div>
    ) : (
      <p>{message.text}</p>
    )}
  </article>
))}

          {isLoading && (
            <div className="loading" role="status">
              Analyzing available scouting data…
            </div>
          )}
        </div>

        {error && (
          <div className="error-message" role="alert">
            {error} Make sure the FastAPI server is running on port 8000.
          </div>
        )}

        <form className="question-form" onSubmit={handleSubmit}>
          <label htmlFor="scout-question">Ask the scouting agent</label>
          <div className="input-row">
            <textarea
              id="scout-question"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="Who leads Seattle in rushing yards?"
              rows="3"
              maxLength="2000"
              disabled={isLoading}
            />
            <button
              type="submit"
              disabled={isLoading || !question.trim()}
            >
              {isLoading ? 'Analyzing…' : 'Ask agent'}
            </button>
          </div>
        </form>
      </section>
    </main>
  )
}

export default App
