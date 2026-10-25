import { memo } from 'react'
import type { ChartPerson } from './api'

const LEVEL_ORDER = ['CEO', 'C-suite', 'VP', 'Head / Director', 'Senior Manager', 'Manager', 'Senior IC', 'IC', 'Junior']
const rank = (p: ChartPerson) => (p.level ? LEVEL_ORDER.indexOf(p.level) : LEVEL_ORDER.length)

export interface Tree {
  byId: Map<string, ChartPerson>
  children: Map<string, ChartPerson[]>
  size: Map<string, number> // people in the subtree, excluding the person
  roots: ChartPerson[] // the top of the company
  orphanTeams: ChartPerson[] // unplaced people who still have people placed under them
  unplaced: ChartPerson[] // unplaced, nobody under them
}

export function buildTree(people: ChartPerson[]): Tree {
  const byId = new Map(people.map((p) => [p.id, p]))
  const children = new Map<string, ChartPerson[]>()
  for (const p of people) {
    if (p.manager_id) {
      const list = children.get(p.manager_id) ?? []
      list.push(p)
      children.set(p.manager_id, list)
    }
  }
  // Direct reports first, then "reports up to"; senior first; then by name.
  for (const list of children.values()) {
    list.sort((a, b) => Number(a.placement === 'partial') - Number(b.placement === 'partial') ||
      rank(a) - rank(b) || a.name.localeCompare(b.name))
  }
  const size = new Map<string, number>()
  const count = (id: string): number => {
    if (size.has(id)) return size.get(id)!
    const n = (children.get(id) ?? []).reduce((s, c) => s + 1 + count(c.id), 0)
    size.set(id, n)
    return n
  }
  people.forEach((p) => count(p.id))
  const top = people.filter((p) => !p.manager_id)
  const bySize = (a: ChartPerson, b: ChartPerson) => size.get(b.id)! - size.get(a.id)! || rank(a) - rank(b)
  return {
    byId,
    children,
    size,
    roots: top.filter((p) => p.placement === 'root').sort(bySize),
    orphanTeams: top.filter((p) => p.placement !== 'root' && size.get(p.id)! > 0).sort(bySize),
    unplaced: top.filter((p) => p.placement !== 'root' && size.get(p.id) === 0).sort((a, b) => rank(a) - rank(b)),
  }
}

export function confidenceBand(c: number): 'high' | 'mid' | 'low' {
  return c >= 0.9 ? 'high' : c >= 0.75 ? 'mid' : 'low'
}

interface NodeProps {
  person: ChartPerson
  tree: Tree
  expanded: Set<string>
  selected: string | null
  onToggle: (id: string) => void
  onSelect: (id: string) => void
  depth: number
}

const Node = memo(function Node({ person, tree, expanded, selected, onToggle, onSelect, depth }: NodeProps) {
  const kids = tree.children.get(person.id) ?? []
  const open = expanded.has(person.id)
  const placed = person.placement === 'exact' || person.placement === 'partial'
  return (
    <li className={`node ${person.placement}`}>
      <div
        id={`p-${person.id}`}
        className={`row${selected === person.id ? ' selected' : ''}`}
        style={{ paddingLeft: `${depth * 1.25}rem` }}
        onClick={() => onSelect(person.id)}
      >
        {kids.length > 0 ? (
          <button
            className="toggle"
            aria-expanded={open}
            aria-label={`${open ? 'Collapse' : 'Expand'} ${person.name}'s team`}
            onClick={(e) => {
              e.stopPropagation()
              onToggle(person.id)
            }}
          >
            {open ? '▾' : '▸'}
          </button>
        ) : (
          <span className="toggle-spacer" />
        )}
        <span className="who">
          <span className="name">{person.name}</span>
          <span className="title">{person.title || <em>no title</em>}</span>
        </span>
        {kids.length > 0 && <span className="team-size" title="People placed under them">{tree.size.get(person.id)}</span>}
        {placed && (
          <span
            className={`conf ${confidenceBand(person.confidence)}`}
            title={person.placement === 'partial'
              ? `Reports somewhere under this person (not necessarily directly): ${(person.confidence * 100).toFixed(0)}% confident`
              : `Direct manager: ${(person.confidence * 100).toFixed(0)}% confident`}
          >
            {person.placement === 'partial' && <span className="partial-tag">up to</span>}
            {(person.confidence * 100).toFixed(0)}%
          </span>
        )}
      </div>
      {open && kids.length > 0 && (
        <ul>
          {kids.map((k) => (
            <Node key={k.id} person={k} tree={tree} expanded={expanded} selected={selected}
              onToggle={onToggle} onSelect={onSelect} depth={depth + 1} />
          ))}
        </ul>
      )}
    </li>
  )
})

const UNPLACED_GROUPS = [
  { code: 'uncertain', title: 'Not sure enough',
    blurb: 'Our best guess is below this strictness setting, usually because several people fit. Sorted by best guess; a looser setting places the top ones.' },
  { code: 'ghost_like', title: 'Probably no boss in the data',
    blurb: 'Looks like a stale profile (someone who left) or their boss is missing from the data.' },
  { code: 'no_candidates', title: 'No possible boss',
    blurb: 'Nobody in the data reads as more senior: often a blank or unreadable title.' },
] as const

interface Props {
  tree: Tree
  expanded: Set<string>
  selected: string | null
  onToggle: (id: string) => void
  onSelect: (id: string) => void
  showUnplaced: boolean
  onToggleUnplaced: () => void
}

export function OrgTree({ tree, expanded, selected, onToggle, onSelect, showUnplaced, onToggleUnplaced }: Props) {
  const nodeProps = { tree, expanded, selected, onToggle, onSelect, depth: 0 }
  return (
    <div className="tree">
      <ul className="tree-root">
        {tree.roots.map((p) => <Node key={p.id} person={p} {...nodeProps} />)}
      </ul>
      {tree.orphanTeams.length > 0 && (
        <section className="tree-section">
          <h3>Teams we couldn't attach <span className="muted">({tree.orphanTeams.length})</span></h3>
          <p className="muted small">We know who reports to these people, but not who they report to.</p>
          <ul className="tree-root">
            {tree.orphanTeams.map((p) => <Node key={p.id} person={p} {...nodeProps} />)}
          </ul>
        </section>
      )}
      <section className="tree-section">
        <button className="section-toggle" aria-expanded={showUnplaced} onClick={onToggleUnplaced}>
          {showUnplaced ? '▾' : '▸'} Not placed <span className="muted">({tree.unplaced.length})</span>
        </button>
        <p className="muted small">Not sure enough to draw a line. A wrong line is worse than no line.</p>
        {showUnplaced && UNPLACED_GROUPS.map((g) => {
          const members = tree.unplaced.filter((p) => (p.reason_code ?? 'uncertain') === g.code)
            .sort((a, b) => (b.best_guess_p ?? 0) - (a.best_guess_p ?? 0))
          if (!members.length) return null
          return (
            <div key={g.code} className="unplaced-group">
              <h4>{g.title} <span className="muted">({members.length})</span></h4>
              <p className="muted small">{g.blurb}</p>
              <ul className="unplaced-list">
                {members.map((p) => {
                  const guess = p.best_guess_id ? tree.byId.get(p.best_guess_id) : undefined
                  return (
                    <li key={p.id} id={`p-${p.id}`} className={`row${selected === p.id ? ' selected' : ''}`}
                      onClick={() => onSelect(p.id)}>
                      <span className="toggle-spacer" />
                      <span className="who">
                        <span className="name">{p.name}</span>
                        <span className="title">{p.title || <em>no title</em>}</span>
                      </span>
                      {guess && p.best_guess_p !== undefined && (
                        <span className="reason" title={p.reason}>
                          best guess {guess.name}, {Math.round(p.best_guess_p * 100)}%
                        </span>
                      )}
                    </li>
                  )
                })}
              </ul>
            </div>
          )
        })}
      </section>
    </div>
  )
}
