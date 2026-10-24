import { useEffect, useMemo, useRef, useState } from 'react'
import type { CompanySummary } from './api'

interface Props {
  companies: CompanySummary[]
  selected: CompanySummary | null
  onSelect: (c: CompanySummary) => void
}

const MAX_SHOWN = 60

export function CompanyPicker({ companies, selected, onSelect }: Props) {
  const [query, setQuery] = useState('')
  const [industry, setIndustry] = useState('')
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const box = useRef<HTMLDivElement>(null)

  const industries = useMemo(() => [...new Set(companies.map((c) => c.industry))].sort(), [companies])
  const matches = useMemo(() => {
    const q = query.trim().toLowerCase()
    return companies.filter(
      (c) => (!industry || c.industry === industry) && (!q || c.name.toLowerCase().includes(q) || c.hq.toLowerCase().includes(q)),
    )
  }, [companies, query, industry])

  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])

  const choose = (c: CompanySummary) => {
    onSelect(c)
    setQuery('')
    setOpen(false)
  }

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setOpen(true)
      setActive((a) => Math.min(a + 1, Math.min(matches.length, MAX_SHOWN) - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActive((a) => Math.max(a - 1, 0))
    } else if (e.key === 'Enter' && matches[active]) {
      choose(matches[active])
    } else if (e.key === 'Escape') {
      setOpen(false)
    }
  }

  return (
    <div className="picker" ref={box}>
      <div className="picker-row">
        <input
          className="picker-input"
          type="search"
          placeholder={selected ? `Search companies (now: ${selected.name})` : 'Search 600 companies by name or city'}
          value={query}
          onChange={(e) => {
            setQuery(e.target.value)
            setOpen(true)
            setActive(0)
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={onKey}
          aria-label="Search companies"
        />
        <select className="picker-industry" value={industry} onChange={(e) => {
          setIndustry(e.target.value)
          setOpen(true)
          setActive(0)
        }} aria-label="Filter by industry">
          <option value="">All industries</option>
          {industries.map((i) => (
            <option key={i} value={i}>{i}</option>
          ))}
        </select>
      </div>
      {open && (
        <ul className="picker-list" role="listbox">
          {matches.length === 0 && <li className="picker-empty">No companies match</li>}
          {matches.slice(0, MAX_SHOWN).map((c, i) => (
            <li
              key={c.company_id}
              role="option"
              aria-selected={i === active}
              className={i === active ? 'active' : ''}
              onMouseEnter={() => setActive(i)}
              onMouseDown={(e) => {
                e.preventDefault()
                choose(c)
              }}
            >
              <span className="picker-name">{c.name}</span>
              <span className="picker-meta">
                {c.industry} · {c.headcount_band} staff · {c.hq}
              </span>
            </li>
          ))}
          {matches.length > MAX_SHOWN && (
            <li className="picker-empty">{matches.length - MAX_SHOWN} more: keep typing to narrow down</li>
          )}
        </ul>
      )}
    </div>
  )
}
