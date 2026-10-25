import { useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { api } from './api'
import type { Answer, ChartPerson, PresetName } from './api'
import { dept } from './WhyPanel'

interface Props {
  companyId: string
  preset: PresetName
  people: ChartPerson[]
  nameOf: (id: string) => string | undefined
  onGoTo: (id: string) => void
}

// [[id|Name]] becomes a link to that person; **bold** becomes bold.
function inline(text: string, onGoTo: (id: string) => void, known: (id: string) => boolean): ReactNode[] {
  return text.split(/(\[\[[^|\]]+\|[^\]]+\]\]|\*\*[^*]+\*\*)/).map((part, i) => {
    const link = part.match(/^\[\[([^|\]]+)\|([^\]]+)\]\]$/)
    if (link) {
      return known(link[1])
        ? <button key={i} className="link" onClick={() => onGoTo(link[1])}>{link[2]}</button>
        : link[2]
    }
    const bold = part.match(/^\*\*([^*]+)\*\*$/)
    return bold ? <strong key={i}>{bold[1]}</strong> : part
  })
}

// Paragraphs and bullet lists, which is all Gemini is asked to write.
function Rendered({ text, onGoTo, known }: { text: string; onGoTo: (id: string) => void; known: (id: string) => boolean }) {
  const blocks: ReactNode[] = []
  let items: string[] = []
  const flush = () => {
    if (items.length) blocks.push(<ul key={blocks.length}>{items.map((t, i) => <li key={i}>{inline(t, onGoTo, known)}</li>)}</ul>)
    items = []
  }
  for (const line of text.split('\n')) {
    const bullet = line.match(/^\s*[*-]\s+(.*)$/)
    if (bullet) items.push(bullet[1])
    else {
      flush()
      if (line.trim()) blocks.push(<p key={blocks.length}>{inline(line, onGoTo, known)}</p>)
    }
  }
  flush()
  return <>{blocks}</>
}

function describe(step: Answer['trail'][number], nameOf: (id: string) => string | undefined): string {
  const filters = [step.args.level, dept(step.args.department)].filter(Boolean).join(', ')
  switch (step.tool) {
    case 'find_people':
      return `searched ${step.args.query ? `“${step.args.query}”` : 'everyone'}${filters ? ` (${filters})` : ''}`
    case 'person':
      return `opened ${nameOf(step.args.id) ?? 'a person'}`
    case 'people_under':
      return `listed people under ${nameOf(step.args.id) ?? 'someone'}${filters ? ` (${filters})` : ''}`
    case 'company_overview':
      return 'read the company overview'
    default:
      return step.tool
  }
}

export function AskBox({ companyId, preset, people, nameOf, onGoTo }: Props) {
  const [question, setQuestion] = useState('')
  const [asked, setAsked] = useState<string | null>(null)
  const [answer, setAnswer] = useState<Answer | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  // Example questions from this company's own departments.
  const examples = useMemo(() => {
    const counts = new Map<string, number>()
    for (const p of people) if (p.function && p.function !== 'executive') counts.set(p.function, (counts.get(p.function) ?? 0) + 1)
    const top = [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 2).map(([f]) => dept(f))
    return [`Who leads ${top[0]}?`, 'Who reports to the CEO?', 'Which managers have the biggest teams?',
      ...(top[1] ? [`How is ${top[1]} organised?`] : [])]
  }, [people])

  const submit = (q: string) => {
    const text = q.trim()
    if (!text || busy) return
    setQuestion(text)
    setAsked(text)
    setBusy(true)
    setError(null)
    setAnswer(null)
    api.ask(companyId, text, preset)
      .then(setAnswer)
      .catch((e: Error) => setError(e.message))
      .finally(() => setBusy(false))
  }

  const known = (id: string) => nameOf(id) !== undefined

  return (
    <section className="ask">
      <form
        className="ask-form"
        onSubmit={(e) => {
          e.preventDefault()
          submit(question)
        }}
      >
        <span className="ask-spark" aria-hidden>✦</span>
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask about this company"
          maxLength={300}
          aria-label="Ask a question about this company"
        />
        <button className="primary" disabled={busy || !question.trim()}>{busy ? 'Thinking…' : 'Ask'}</button>
      </form>
      {!asked && (
        <div className="ask-examples">
          {examples.map((q) => <button key={q} onClick={() => submit(q)}>{q}</button>)}
        </div>
      )}
      {error && <p className="error">{error}</p>}
      {answer && asked && (
        <div className="ask-answer">
          <div className="ask-text"><Rendered text={answer.answer} onGoTo={onGoTo} known={known} /></div>
          {answer.trail.length > 0 && (
            <p className="muted small">How it found this: {answer.trail.map((s) => describe(s, nameOf)).join(' · ')}</p>
          )}
          <p className="muted small">
            Gemini answered from the chart at {preset} strictness, not from the answer key{answer.cached ? ' (saved answer)' : ''}.
            The linked people are the evidence: click one to check the line.
          </p>
        </div>
      )}
    </section>
  )
}
