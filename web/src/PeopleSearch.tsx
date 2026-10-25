import { useMemo, useState } from 'react'
import type { ChartPerson } from './api'

interface Props {
  people: ChartPerson[]
  onPick: (id: string) => void
}

const MAX_SHOWN = 12

export function PeopleSearch({ people, onPick }: Props) {
  const [q, setQ] = useState('')
  const [active, setActive] = useState(0)
  const matches = useMemo(() => {
    const s = q.trim().toLowerCase()
    if (s.length < 2) return []
    const words = s.split(/\s+/)
    return people
      .filter((p) => {
        const hay = `${p.name} ${p.title} ${p.department}`.toLowerCase()
        return words.every((w) => hay.includes(w))
      })
      .slice(0, MAX_SHOWN)
  }, [people, q])

  const pick = (id: string) => {
    onPick(id)
    setQ('')
  }

  return (
    <div className="people-search">
      <input
        type="search"
        placeholder="Find a person or title, e.g. “head of security”"
        value={q}
        onChange={(e) => {
          setQ(e.target.value)
          setActive(0)
        }}
        onKeyDown={(e) => {
          if (e.key === 'ArrowDown') {
            e.preventDefault()
            setActive((a) => Math.min(a + 1, matches.length - 1))
          } else if (e.key === 'ArrowUp') {
            e.preventDefault()
            setActive((a) => Math.max(a - 1, 0))
          } else if (e.key === 'Enter' && matches[active]) {
            pick(matches[active].id)
          } else if (e.key === 'Escape') {
            setQ('')
          }
        }}
        aria-label="Find a person"
      />
      {q.trim().length >= 2 && (
        <ul className="picker-list" role="listbox">
          {matches.length === 0 && <li className="picker-empty">Nobody matches</li>}
          {matches.map((p, i) => (
            <li
              key={p.id}
              role="option"
              aria-selected={i === active}
              className={i === active ? 'active' : ''}
              onMouseEnter={() => setActive(i)}
              onMouseDown={(e) => {
                e.preventDefault()
                pick(p.id)
              }}
            >
              <span className="picker-name">{p.name}</span>
              <span className="picker-meta">
                {p.title || 'no title'} · {p.placement === 'unplaced' ? 'not placed' : p.placement === 'root' ? 'top' : 'in chart'}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
