import { useState, useEffect, useRef } from 'react'

interface DateInputProps {
  value: string
  onChange: (value: string) => void
  required?: boolean
  className?: string
  min?: string
  max?: string
}

function isoToGerman(iso: string): string {
  if (!iso || !/^\d{4}-\d{2}-\d{2}$/.test(iso)) return ''
  return `${iso.slice(8, 10)}.${iso.slice(5, 7)}.${iso.slice(0, 4)}`
}

function germanToIso(s: string): string {
  const m = s.match(/^(\d{1,2})\.(\d{1,2})\.(\d{2}|\d{4})$/)
  if (!m) return ''
  const dd = m[1].padStart(2, '0')
  const mm = m[2].padStart(2, '0')
  const y = m[3].length === 2 ? `20${m[3]}` : m[3]
  if (parseInt(mm) < 1 || parseInt(mm) > 12) return ''
  if (parseInt(dd) < 1 || parseInt(dd) > 31) return ''
  const iso = `${y}-${mm}-${dd}`
  const dt = new Date(iso + 'T00:00:00')
  if (isNaN(dt.getTime())) return ''
  if (dt.getFullYear() !== parseInt(y) || dt.getMonth() + 1 !== parseInt(mm) || dt.getDate() !== parseInt(dd)) return ''
  return iso
}

function heuteIso(): string {
  const h = new Date()
  return `${h.getFullYear()}-${String(h.getMonth() + 1).padStart(2, '0')}-${String(h.getDate()).padStart(2, '0')}`
}

const WOCHENTAGE = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']
const MONATSNAMEN = [
  'Januar', 'Februar', 'März', 'April', 'Mai', 'Juni',
  'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember',
]

// ---------------------------------------------------------------------------
// Eigener Kalender-Dropdown statt nativem <input type="date">/showPicker()
// ---------------------------------------------------------------------------
// Unter WebKitGTK (Tauri auf Linux) blieb der native Picker nach der Auswahl offen
// stehen (Issue #384/#386) - unter Windows (WebView2) trat der Fehler nicht auf. Zwei
// gezielte Fixversuche (Anker-Größe, blur()) haben das nicht behoben, einer davon sogar
// eine Regression verursacht (Popup ragte über den Bildschirmrand). Ein rein selbst
// gerenderter Dropdown umgeht das Problem strukturell, da kein natives OS-Popup mehr
// im Spiel ist - Verhalten ist damit auf allen Plattformen identisch.

interface KalenderDropdownProps {
  value: string
  min?: string
  max?: string
  onSelect: (iso: string) => void
  onClose: () => void
}

function KalenderDropdown({ value, min, max, onSelect, onClose }: KalenderDropdownProps) {
  const basis = /^\d{4}-\d{2}-\d{2}$/.test(value) ? new Date(`${value}T00:00:00`) : new Date()
  const [anzeigeJahr, setAnzeigeJahr] = useState(basis.getFullYear())
  const [anzeigeMonat, setAnzeigeMonat] = useState(basis.getMonth())
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose()
    }
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('mousedown', onDocClick)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('mousedown', onDocClick)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [onClose])

  function vorMonat() {
    if (anzeigeMonat === 0) { setAnzeigeMonat(11); setAnzeigeJahr(j => j - 1) }
    else setAnzeigeMonat(m => m - 1)
  }
  function naechsterMonat() {
    if (anzeigeMonat === 11) { setAnzeigeMonat(0); setAnzeigeJahr(j => j + 1) }
    else setAnzeigeMonat(m => m + 1)
  }

  const anzahlTage = new Date(anzeigeJahr, anzeigeMonat + 1, 0).getDate()
  const ersterWochentag = (new Date(anzeigeJahr, anzeigeMonat, 1).getDay() + 6) % 7 // 0=Mo
  const zellen: (number | null)[] = [
    ...Array(ersterWochentag).fill(null),
    ...Array.from({ length: anzahlTage }, (_, i) => i + 1),
  ]
  const heute = heuteIso()

  return (
    <div
      ref={ref}
      className="absolute z-50 right-0 mt-1 w-64 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-600 rounded-lg shadow-lg p-3"
    >
      <div className="flex items-center justify-between mb-2">
        <button type="button" onClick={vorMonat} tabIndex={-1} className="p-1 rounded text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-700">‹</button>
        <span className="text-sm font-medium text-slate-700 dark:text-slate-200">{MONATSNAMEN[anzeigeMonat]} {anzeigeJahr}</span>
        <button type="button" onClick={naechsterMonat} tabIndex={-1} className="p-1 rounded text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-700">›</button>
      </div>
      <div className="grid grid-cols-7 gap-0.5 text-center text-[11px] text-slate-400 dark:text-slate-500 mb-1">
        {WOCHENTAGE.map(w => <div key={w}>{w}</div>)}
      </div>
      <div className="grid grid-cols-7 gap-0.5">
        {zellen.map((tag, i) => {
          if (tag === null) return <div key={`leer-${i}`} />
          const iso = `${anzeigeJahr}-${String(anzeigeMonat + 1).padStart(2, '0')}-${String(tag).padStart(2, '0')}`
          const gesperrt = (!!min && iso < min) || (!!max && iso > max)
          const ausgewaehlt = iso === value
          const istHeute = iso === heute
          return (
            <button
              key={iso}
              type="button"
              tabIndex={-1}
              disabled={gesperrt}
              onClick={() => onSelect(iso)}
              className={`text-xs rounded py-1 transition-colors ${
                ausgewaehlt
                  ? 'bg-blue-600 text-white'
                  : istHeute
                    ? 'border border-blue-400 dark:border-blue-500 text-blue-600 dark:text-blue-400'
                    : 'text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-700'
              } ${gesperrt ? 'opacity-30 cursor-not-allowed hover:bg-transparent dark:hover:bg-transparent' : ''}`}
            >
              {tag}
            </button>
          )
        })}
      </div>
    </div>
  )
}

export function DateInput({ value, onChange, required, className, min, max }: DateInputProps) {
  const [text, setText] = useState(() => isoToGerman(value))
  const [invalid, setInvalid] = useState(false)
  const [pickerOffen, setPickerOffen] = useState(false)
  const prevValue = useRef(value)

  useEffect(() => {
    if (value !== prevValue.current) {
      prevValue.current = value
      setText(isoToGerman(value))
      setInvalid(false)
    }
  }, [value])

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const raw = e.target.value
    const adding = raw.length >= text.length

    let s = raw.replace(/[^0-9.]/g, '').replace(/\.{2,}/g, '.')

    if (adding) {
      const digits = s.replace(/\./g, '')
      if (digits.length === 2 && !s.includes('.')) {
        s = s + '.'
      } else if (digits.length === 4 && s.split('.').length === 2 && !s.endsWith('.')) {
        s = s + '.'
      }
    }

    const parts = s.split('.')
    if (parts.length === 3 && parts[2].length > 4) {
      s = `${parts[0]}.${parts[1]}.${parts[2].slice(0, 4)}`
    }

    setText(s)
    setInvalid(false)

    if (!s) {
      prevValue.current = ''
      onChange('')
      return
    }

    const iso = germanToIso(s)
    if (iso && (!min || iso >= min) && (!max || iso <= max)) {
      prevValue.current = iso
      onChange(iso)
    }
  }

  function handleBlur() {
    if (!text) { setInvalid(false); return }
    const iso = germanToIso(text)
    if (iso) {
      setInvalid(false)
      setText(isoToGerman(iso))
    } else {
      setInvalid(true)
    }
  }

  function handlePickerSelect(iso: string) {
    prevValue.current = iso
    setText(isoToGerman(iso))
    setInvalid(false)
    onChange(iso)
    setPickerOffen(false)
  }

  return (
    <div className="relative">
      <input
        type="text"
        inputMode="numeric"
        value={text}
        onChange={handleChange}
        onBlur={handleBlur}
        required={required}
        placeholder="TT.MM.JJJJ"
        maxLength={10}
        className={`${className ?? ''}${invalid ? ' !border-red-400 dark:!border-red-500' : ''} pr-8`}
      />
      <button
        type="button"
        onClick={() => setPickerOffen(o => !o)}
        tabIndex={-1}
        title="Kalender öffnen"
        className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 dark:text-slate-500 dark:hover:text-slate-300 focus:outline-none"
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/>
          <line x1="16" y1="2" x2="16" y2="6"/>
          <line x1="8" y1="2" x2="8" y2="6"/>
          <line x1="3" y1="10" x2="21" y2="10"/>
        </svg>
      </button>
      {pickerOffen && (
        <KalenderDropdown
          value={value}
          min={min}
          max={max}
          onSelect={handlePickerSelect}
          onClose={() => setPickerOffen(false)}
        />
      )}
    </div>
  )
}
