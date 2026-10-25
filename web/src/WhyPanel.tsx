import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { api } from './api'
import type { ChartPerson, GradeLine, PresetName, Why } from './api'
import { confidenceBand } from './OrgTree'

interface Props {
  companyId: string
  person: ChartPerson
  preset: PresetName
  nameOf: (id: string) => string | undefined
  onGoTo: (id: string) => void
  onClose: () => void
  line?: GradeLine
}

const pct = (x: number) => `${Math.round(x * 100)}%`
export const dept = (f: string | null | undefined) => (f ? f.replace(/_/g, ' ') : null)

function Bar({ value, tone }: { value: number; tone: string }) {
  return (
    <span className="bar" aria-hidden>
      <span className={`bar-fill ${tone}`} style={{ width: `${Math.max(2, value * 100)}%` }} />
    </span>
  )
}

function Decision({ person, why, onGoTo }: { person: ChartPerson; why: Why; onGoTo: (id: string) => void }) {
  const d = why.decision
  const m = d.manager
  if (person.placement === 'root') return <p className="decision">Top of the company: nobody in the data is senior to them.</p>
  if (!m) {
    return (
      <p className="decision none">
        <strong>Not placed.</strong> {person.reason}. A wrong line is worse than no line, so we leave it blank.
      </p>
    )
  }
  const who = <button className="link" onClick={() => onGoTo(m.id)}>{m.name}</button>
  return d.kind === 'exact' ? (
    <p className="decision">
      Reports to {who}, {m.title} <span className={`conf ${confidenceBand(d.confidence)}`}>{pct(d.confidence)}</span>
    </p>
  ) : (
    <p className="decision">
      Reports <em>somewhere under</em> {who}, {m.title}{' '}
      <span className={`conf ${confidenceBand(d.confidence)}`}><span className="partial-tag">up to</span>{pct(d.confidence)}</span>
      <span className="muted small-block">
        We can't tell which of the likely bosses below is the direct one, but they all sit under {m.name}.
      </span>
    </p>
  )
}

// The answer key's verdict on this person, in a sentence.
function AnswerKey({ line, why, top, onGoTo }: { line: GradeLine; why: Why; top: boolean; onGoTo: (id: string) => void }) {
  const real = line.correct_manager
  const realLink = real && <button className="link" onClick={() => onGoTo(real.id)}>{real.name}</button>
  const ours = why.decision.manager?.name
  const given = real && why.candidates.find((c) => c.id === real.id)
  const gave = real && (given ? ` We gave them ${pct(given.probability)}.` : ' They weren\'t among our candidates.')
  const noBoss = line.kind === 'ghost' ? 'this is a stale profile of someone who has left' : 'their manager isn\'t in the data'
  const levels = (n: number) => `${n} level${n === 1 ? '' : 's'}`
  let tone = 'ok'
  let text: ReactNode
  switch (line.outcome) {
    case 'exact_correct':
      text = <>Right: {ours} is their direct manager.</>
      break
    case 'partial_correct':
      text = line.levels_above_manager
        ? <>Right: {ours} is {levels(line.levels_above_manager)} above their direct manager, {realLink}.</>
        : <>Right, and closer than we claimed: {ours} is their direct manager.</>
      break
    case 'partial_to_top':
      tone = 'weak'
      text = <>True, but not much use: {ours} is the top of their chain. Their direct manager is {realLink}.</>
      break
    case 'exact_wrong':
    case 'partial_wrong':
      tone = 'bad'
      text = <>Wrong: their real manager is {realLink}.{gave}</>
      break
    case 'false_claim':
      tone = 'bad'
      text = <>Wrong: {noBoss}, so nobody here manages them.</>
      break
    case 'correct_none':
      text = top ? <>Right: they're the top of the company.</> : <>Rightly left out: {noBoss}.</>
      break
    case 'abstain':
      tone = 'none'
      text = <>Left out. Their real manager is {realLink}.{gave}</>
      break
  }
  return (
    <section className={`answer-key ${tone}`}>
      <h3>Answer key</h3>
      <p>{text}</p>
      {line.kind === 'duplicate' && <p className="muted small">This record is a second profile of someone else in the data.</p>}
    </section>
  )
}

export function WhyPanel({ companyId, person, preset, nameOf, onGoTo, onClose, line }: Props) {
  const [why, setWhy] = useState<Why | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let stale = false
    api.why(companyId, person.id, preset)
      .then((w) => {
        if (!stale) {
          setWhy(w)
          setError(null)
        }
      })
      .catch((e) => !stale && setError(String(e)))
    return () => {
      stale = true
    }
  }, [companyId, person.id, preset])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const loaded = why && why.person.id === person.id ? why : null
  const r = loaded?.read_as

  return (
    <aside className="why" aria-label={`Why: ${person.name}`}>
      <header className="why-head">
        <div>
          <h2>{person.name}</h2>
          <p className="muted">{person.title || <em>no title</em>}</p>
        </div>
        <button className="close" onClick={onClose} aria-label="Close">×</button>
      </header>

      {error && <p className="error">{error}</p>}
      {!loaded && !error && <p className="muted">Loading…</p>}

      {loaded && r && (
        <>
          <Decision person={person} why={loaded} onGoTo={onGoTo} />
          {line && <AnswerKey line={line} why={loaded} top={person.placement === 'root'} onGoTo={onGoTo} />}

          <section>
            <h3>What we read from their profile</h3>
            <dl className="facts">
              <dt>Seniority</dt>
              <dd>{r.level ?? <span className="muted">unreadable</span>}</dd>
              <dt>Department</dt>
              <dd>
                {dept(r.department) ?? <span className="muted">unknown</span>}
                {loaded.person.department && <span className="muted"> · field says “{loaded.person.department}”</span>}
              </dd>
              {r.team && <><dt>Team</dt><dd>{r.team}</dd></>}
              <dt>Office</dt>
              <dd>{r.office ? r.office.replace(/\b\w/g, (c) => c.toUpperCase()) : <span className="muted">unknown</span>}</dd>
              <dt>Started</dt>
              <dd>{loaded.person.start_date || <span className="muted">unknown</span>}</dd>
              {loaded.person.prev_employer && <><dt>Previously</dt><dd>{loaded.person.prev_employer}</dd></>}
              <dt>Title parse</dt>
              <dd>
                {pct(r.confidence)} sure
                {r.flags.includes('gemini') && <span className="chip">Gemini helped</span>}
                {r.flags.filter((f) => f !== 'gemini').map((f) => <span key={f} className="chip">{f}</span>)}
              </dd>
            </dl>
          </section>

          {loaded.candidates.length > 0 && (
            <section>
              <h3>Who could be their direct boss</h3>
              <ol className="candidates">
                {loaded.candidates.map((c) => (
                  <li key={c.id}>
                    <div className="cand-head">
                      <button className="link cand-name" onClick={() => onGoTo(c.id)}>{c.name}</button>
                      <span className="cand-p">{pct(c.probability)}</span>
                    </div>
                    <div className="muted cand-title">{c.title || 'no title'}</div>
                    <Bar value={c.probability} tone={confidenceBand(c.probability)} />
                    {c.clues.length > 0 && (
                      <ul className="clues">
                        {c.clues.map((k) => (
                          <li key={k.clue} className={k.effect > 0 ? 'for' : 'against'} title={`Effect on the score: ${k.effect > 0 ? '+' : ''}${k.effect}`}>
                            {k.effect > 0 ? '+' : '−'} {k.clue}
                          </li>
                        ))}
                      </ul>
                    )}
                  </li>
                ))}
                <li>
                  <div className="cand-head">
                    <span className="cand-name">None of these</span>
                    <span className="cand-p">{pct(loaded.probability_no_boss_here)}</span>
                  </div>
                  <div className="muted cand-title">Their boss isn't in the data, or this profile is stale</div>
                  <Bar value={loaded.probability_no_boss_here} tone="none" />
                </li>
              </ol>
            </section>
          )}

          {loaded.reports_up_to.length > 0 && (
            <section>
              <h3>Somewhere above them</h3>
              <ul className="ups">
                {loaded.reports_up_to.map((a) => (
                  <li key={a.id}>
                    <button className="link" onClick={() => onGoTo(a.id)}>{nameOf(a.id) ?? a.name}</button>
                    <span className="muted"> {a.title}</span>
                    <span className="cand-p">{pct(a.probability)}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </>
      )}
    </aside>
  )
}
