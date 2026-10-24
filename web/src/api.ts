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
}

export interface Chart {
  company: CompanySummary
  preset: Preset
  counts: Record<Placement, number>
  people: ChartPerson[]
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
}
