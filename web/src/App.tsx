import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from './api'
import type { Chart, CompanySummary, Preset, PresetName } from './api'
import { CompanyPicker } from './CompanyPicker'
import { OrgTree, buildTree, confidenceBand } from './OrgTree'
import { StrictnessSlider } from './StrictnessSlider'
import './App.css'

const PRESETS: PresetName[] = ['strict', 'balanced', 'broad']

// The company and strictness live in the URL, so a chart can be shared as a link.
function readUrl(): { company: string | null; preset: PresetName } {
  const q = new URLSearchParams(window.location.search)
  const preset = q.get('preset') as PresetName
  return { company: q.get('company'), preset: PRESETS.includes(preset) ? preset : 'strict' }
}

function writeUrl(company: string | null, preset: PresetName) {
  const q = new URLSearchParams()
  if (company) q.set('company', company)
  if (preset !== 'strict') q.set('preset', preset)
  window.history.replaceState(null, '', `${window.location.pathname}${q.toString() ? `?${q}` : ''}`)
}

export default function App() {
  const [initial] = useState(readUrl)
  const [companies, setCompanies] = useState<CompanySummary[]>([])
  const [presets, setPresets] = useState<Preset[]>([])
  const [companyId, setCompanyId] = useState<string | null>(initial.company)
  const [preset, setPreset] = useState<PresetName>(initial.preset)
  const [chart, setChart] = useState<Chart | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [selected, setSelected] = useState<string | null>(null)
  const [showUnplaced, setShowUnplaced] = useState(false)

  useEffect(() => {
    Promise.all([api.companies(), api.presets()])
      .then(([c, p]) => {
        setCompanies(c)
        setPresets(p)
      })
      .catch((e) => setError(String(e)))
  }, [])

  useEffect(() => {
    writeUrl(companyId, preset)
    if (!companyId) return
    let stale = false
    setLoading(true)
    setError(null)
    api.chart(companyId, preset)
      .then((c) => !stale && setChart(c))
      .catch((e) => !stale && setError(String(e)))
      .finally(() => !stale && setLoading(false))
    return () => {
      stale = true
    }
  }, [companyId, preset])

  const tree = useMemo(() => (chart ? buildTree(chart.people) : null), [chart])

  // A new company opens with the top of the company expanded.
  useEffect(() => {
    if (!tree) return
    setExpanded((prev) => {
      const known = [...prev].filter((id) => tree.byId.has(id))
      return known.length ? new Set(known) : new Set(tree.roots.map((p) => p.id))
    })
  }, [tree])

  const selectCompany = (c: CompanySummary) => {
    if (c.company_id === companyId) return
    setChart(null)
    setExpanded(new Set())
    setSelected(null)
    setShowUnplaced(false)
    setCompanyId(c.company_id)
  }

  const toggle = useCallback((id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  const expandAll = () => tree && setExpanded(new Set([...tree.children.keys()]))
  const collapseAll = () => tree && setExpanded(new Set(tree.roots.map((p) => p.id)))

  const current = companies.find((c) => c.company_id === companyId) ?? chart?.company ?? null
  const person = selected && tree ? tree.byId.get(selected) : undefined
  const manager = person?.manager_id && tree ? tree.byId.get(person.manager_id) : undefined

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" aria-hidden>⌥</span>
          <span>Org chart inference</span>
        </div>
        <CompanyPicker companies={companies} selected={current} onSelect={selectCompany} />
      </header>

      {error && <div className="error" role="alert">Something went wrong: {error}</div>}

      {!companyId && (
        <main className="empty">
          <h1>Who reports to whom?</h1>
          <p>
            Pick one of {companies.length || 600} companies. We infer each reporting line from job titles, departments,
            offices and start dates, and give every line a confidence. Where we can't tell, we don't guess.
          </p>
          {companies.length > 0 && (
            <button className="primary" onClick={() => selectCompany(companies[Math.floor(Math.random() * companies.length)])}>
              Show me a random company
            </button>
          )}
        </main>
      )}

      {companyId && (
        <main className="layout">
          <aside className="controls">
            {current && (
              <div className="company-card">
                <h1>{current.name}</h1>
                <p className="muted">
                  {current.industry} · {current.headcount_band} staff · HQ {current.hq}
                </p>
              </div>
            )}
            <StrictnessSlider presets={presets} value={preset} onChange={setPreset} />
            {chart && (
              <dl className="counts">
                <div><dt>Direct lines</dt><dd>{chart.counts.exact}</dd></div>
                <div><dt>"Reports up to"</dt><dd>{chart.counts.partial}</dd></div>
                <div><dt>Not placed</dt><dd>{chart.counts.unplaced}</dd></div>
                <div><dt>Records</dt><dd>{chart.people.length}</dd></div>
              </dl>
            )}
            <div className="legend">
              <span><i className="conf high" /> 90%+</span>
              <span><i className="conf mid" /> 75–90%</span>
              <span><i className="conf low" /> below 75%</span>
              <span><span className="partial-tag">up to</span> somewhere above, not direct</span>
            </div>
            {person && (
              <div className="person-card">
                <h2>{person.name}</h2>
                <p>{person.title || <em>no title</em>}</p>
                <dl>
                  {person.department && <><dt>Department</dt><dd>{person.department}</dd></>}
                  {person.location && <><dt>Office</dt><dd>{person.location}</dd></>}
                  {person.start_date && <><dt>Started</dt><dd>{person.start_date}</dd></>}
                  <dt>Read as</dt>
                  <dd>{[person.level, person.function?.replace('_', ' ')].filter(Boolean).join(', ') || 'unreadable'}</dd>
                  <dt>{person.placement === 'partial' ? 'Reports up to' : 'Manager'}</dt>
                  <dd>
                    {manager ? (
                      <button className="link" onClick={() => setSelected(manager.id)}>
                        {manager.name}, {manager.title}
                      </button>
                    ) : person.placement === 'root' ? 'Top of the company' : <span className="muted">{person.reason}</span>}
                    {manager && (
                      <span className={`conf ${confidenceBand(person.confidence)}`}>{(person.confidence * 100).toFixed(0)}%</span>
                    )}
                  </dd>
                </dl>
              </div>
            )}
          </aside>

          <section className="chart" aria-busy={loading}>
            <div className="chart-toolbar">
              <button onClick={expandAll} disabled={!tree}>Expand all</button>
              <button onClick={collapseAll} disabled={!tree}>Collapse</button>
              {loading && <span className="muted">Inferring…</span>}
            </div>
            {tree ? (
              <OrgTree tree={tree} expanded={expanded} selected={selected} onToggle={toggle} onSelect={setSelected}
                showUnplaced={showUnplaced} onToggleUnplaced={() => setShowUnplaced((s) => !s)} />
            ) : (
              !error && <p className="muted">Inferring the org chart…</p>
            )}
          </section>
        </main>
      )}
    </div>
  )
}
