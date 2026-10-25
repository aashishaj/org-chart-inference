// Types and calls for the FastAPI backend (orgchart/api/app.py).

export type PresetName = 'strict' | 'balanced' | 'broad'

export interface Preset {
  name: PresetName
  exact_threshold: number
  partial_threshold: number
  measured_on: string
  precision: number
  wrong_per_1k: number
  exact_coverage: number
  useful_coverage: number
  ece: number
}

export interface CompanySummary {
  company_id: string
  name: string
  industry: string
  headcount_band: string
  hq: string
  records?: number
}

export type Placement = 'exact' | 'partial' | 'root' | 'unplaced'

export interface ChartPerson {
  id: string
  name: string
  title: string
  department: string
  location: string
  start_date: string
  level: string | null
  function: string | null
  manager_id: string | null
  placement: Placement
  confidence: number
  reason: string
  reason_code?: 'ghost_like' | 'uncertain' | 'no_candidates'
  best_guess_id?: string
  best_guess_p?: number
}

export interface Chart {
  company: CompanySummary
  preset: Preset
  counts: Record<Placement, number>
  people: ChartPerson[]
}

export interface PersonBrief {
  id: string
  name: string
  title: string
}

export interface Why {
  person: PersonBrief & { department: string; location: string; start_date: string; prev_employer: string }
  read_as: {
    level: string | null
    department: string | null
    team: string | null
    office: string | null
    confidence: number
    rule: string
    flags: string[]
  }
  decision: { kind: 'exact' | 'partial' | 'none'; manager: PersonBrief | null; confidence: number; reason: string }
  candidates: (PersonBrief & { probability: number; clues: { clue: string; effect: number }[] })[]
  probability_no_boss_here: number
  reports_up_to: (PersonBrief & { probability: number })[]
}

export type Outcome =
  | 'exact_correct' | 'exact_wrong' | 'partial_correct' | 'partial_to_top' | 'partial_wrong'
  | 'false_claim' | 'abstain' | 'correct_none'

export interface GradeLine {
  outcome: Outcome
  wrong: boolean
  levels_above_manager: number | null
  kind: 'employee' | 'ghost' | 'duplicate'
  correct_manager: PersonBrief | null
}

export interface Grade {
  mess_level: string
  split: 'train' | 'dev' | 'test'
  scorecard: {
    records: number
    claims: number
    wrong: number
    precision: number
    wrong_per_1k: number
    exact_coverage: number
    useful_coverage: number
    attached_to_ghost: number
    outcomes: Partial<Record<Outcome, number>>
  }
  lines: Record<string, GradeLine>
}

async function get<T>(path: string, params: Record<string, string> = {}): Promise<T> {
  const qs = new URLSearchParams(params).toString()
  const res = await fetch(`/api${path}${qs ? `?${qs}` : ''}`)
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`)
  return res.json() as Promise<T>
}

export const api = {
  presets: () => get<Preset[]>('/presets'),
  companies: () => get<CompanySummary[]>('/companies'),
  chart: (id: string, preset: PresetName) => get<Chart>(`/companies/${id}/chart`, { preset }),
  why: (id: string, person: string, preset: PresetName) =>
    get<Why>(`/companies/${id}/people/${person}/why`, { preset }),
  grade: (id: string, preset: PresetName) => get<Grade>(`/companies/${id}/grade`, { preset }),
}
