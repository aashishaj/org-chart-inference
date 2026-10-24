import type { Preset, PresetName } from './api'

interface Props {
  presets: Preset[]
  value: PresetName
  onChange: (p: PresetName) => void
}

const BLURB: Record<PresetName, string> = {
  strict: 'Only lines we can trust',
  balanced: 'More lines, a few more mistakes',
  broad: 'Most lines, verify before you act',
}

const pct = (x: number) => `${(x * 100).toFixed(1)}%`

export function StrictnessSlider({ presets, value, onChange }: Props) {
  const i = Math.max(0, presets.findIndex((p) => p.name === value))
  const p = presets[i]
  if (!p) return null
  return (
    <div className="slider">
      <div className="slider-head">
        <label htmlFor="strictness">Strictness</label>
        <span className="slider-blurb">{BLURB[p.name]}</span>
      </div>
      <input
        id="strictness"
        type="range"
        min={0}
        max={presets.length - 1}
        step={1}
        value={i}
        onChange={(e) => onChange(presets[Number(e.target.value)].name)}
        aria-valuetext={p.name}
      />
      <div className="slider-stops">
        {presets.map((s) => (
          <button key={s.name} className={s.name === value ? 'on' : ''} onClick={() => onChange(s.name)}>
            {s.name}
          </button>
        ))}
      </div>
      <dl className="slider-stats" title={`Measured on the ${p.measured_on} split: companies the model never trained on`}>
        <div>
          <dt>Lines right</dt>
          <dd>{pct(p.precision)}</dd>
        </div>
        <div>
          <dt>Wrong per 1,000</dt>
          <dd>{p.wrong_per_1k.toFixed(1)}</dd>
        </div>
        <div>
          <dt>Useful coverage</dt>
          <dd>{pct(p.useful_coverage)}</dd>
        </div>
      </dl>
    </div>
  )
}
