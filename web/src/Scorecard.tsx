import { useState } from 'react'
import type { Grade, Preset } from './api'
import type { Tree } from './OrgTree'

interface Props {
  on: boolean
  onToggle: () => void
  grade: Grade | null
  preset: Preset | undefined
  tree: Tree | null
  onGoTo: (id: string) => void
}

const pct = (x: number) => `${(x * 100).toFixed(1)}%`

const SPLIT: Record<Grade['split'], string> = {
  train: 'The model was trained on this company, so expect it to score better than average.',
  dev: 'Used to tune the model, never to train it.',
  test: 'Held out: never seen while building the model.',
}

function Row({ n, label, tone }: { n: number; label: string; tone: 'ok' | 'bad' | 'weak' | 'none' }) {
  if (!n) return null
  return (
    <li className={`sc-row ${tone}`}>
      <span className="sc-n">{n}</span> {label}
    </li>
  )
}

export function Scorecard({ on, onToggle, grade, preset, tree, onGoTo }: Props) {
  const [showWrong, setShowWrong] = useState(false)
  const o = grade?.scorecard.outcomes ?? {}
  const n = (k: keyof typeof o) => o[k] ?? 0
  const wrong = grade && tree
    ? Object.entries(grade.lines).filter(([, l]) => l.wrong).map(([id, l]) => ({ id, line: l, p: tree.byId.get(id) }))
    : []
  // Of the people we left out who did have a boss, how often our best guess was that boss.
  const missed = grade && tree
    ? Object.entries(grade.lines).filter(([, l]) => l.outcome === 'abstain').map(([id, l]) => ({ p: tree.byId.get(id), l }))
    : []
  const guessRight = missed.filter(({ p, l }) => p?.best_guess_id && p.best_guess_id === l.correct_manager?.id).length

  return (
    <div className="scorecard">
      <label className="switch">
        <input type="checkbox" checked={on} onChange={onToggle} />
        <span className="switch-track" aria-hidden />
        <span>Grade against the answer key</span>
      </label>
      {!on && (
        <p className="muted small">The data is synthetic, so we know the real chart. Turn this on to mark every line right or wrong.</p>
      )}
      {on && !grade && <p className="muted small">Grading…</p>}
      {on && grade && (
        <>
          <div className="sc-head">
            <span className="sc-big">{pct(grade.scorecard.precision)}</span>
            <span>
              of {grade.scorecard.claims} lines right
              {preset && <span className="muted"> · {pct(preset.precision)} on average at {preset.name}</span>}
            </span>
          </div>
          <p className="muted small">
            <span className="chip">{grade.mess_level} data</span> {SPLIT[grade.split]}
          </p>

          <h4>Lines we drew</h4>
          <ul className="sc-list">
            <Row n={n('exact_correct')} label="direct boss right" tone="ok" />
            <Row n={n('partial_correct')} label={'"up to" right'} tone="ok" />
            <Row n={n('partial_to_top')} label={'"up to" right, but only to the top'} tone="weak" />
            <Row n={n('exact_wrong')} label="wrong direct boss" tone="bad" />
            <Row n={n('partial_wrong')} label={'"up to" the wrong branch'} tone="bad" />
            <Row n={n('false_claim')} label="line for someone with no boss in the data" tone="bad" />
          </ul>

          <h4>People we left out</h4>
          <ul className="sc-list">
            <Row n={n('correct_none')} label="rightly: no boss in the data (stale profiles, the top)" tone="ok" />
            <Row n={n('abstain')} label="had a boss we didn't name" tone="none" />
          </ul>
          {missed.length > 0 && (
            <p className="muted small">
              Had we guessed for those, we'd have been right for {guessRight} of {missed.length}
              {' '}({Math.round((guessRight / missed.length) * 100)}%). That's why we leave them blank.
            </p>
          )}

          {wrong.length > 0 && (
            <>
              <button className="section-toggle" aria-expanded={showWrong} onClick={() => setShowWrong((s) => !s)}>
                {showWrong ? '▾' : '▸'} The wrong lines <span className="muted">({wrong.length})</span>
              </button>
              {showWrong && (
                <ul className="sc-wrong">
                  {wrong.map(({ id, line, p }) => {
                    const said = p?.manager_id ? tree?.byId.get(p.manager_id) : undefined
                    return (
                      <li key={id}>
                        <button className="link" onClick={() => onGoTo(id)}>{p?.name ?? id}</button>
                        <span className="muted small-block">
                          we said {p?.placement === 'partial' ? 'under ' : ''}{said?.name ?? '?'}; {line.correct_manager ? `really ${line.correct_manager.name}` : 'really no boss in the data'}
                        </span>
                      </li>
                    )
                  })}
                </ul>
              )}
            </>
          )}
        </>
      )}
    </div>
  )
}
