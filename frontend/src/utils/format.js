/** Formatting helpers shared across the dashboard. */

export function formatNumber(n) {
  if (n === null || n === undefined || Number.isNaN(n)) return ', '
  if (typeof n !== 'number') return String(n)
  if (Math.abs(n) >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (Math.abs(n) >= 1_000) return `${(n / 1_000).toFixed(1)}k`
  return Number.isInteger(n) ? String(n) : n.toFixed(2)
}

export function formatPercent(x, digits = 1) {
  if (x === null || x === undefined || Number.isNaN(x)) return ', '
  return `${(x * 100).toFixed(digits)}%`
}

export function formatDate(value) {
  if (!value) return ', '
  try {
    const d = new Date(value)
    if (Number.isNaN(d.getTime())) return String(value)
    return d.toISOString().slice(0, 10)
  } catch {
    return String(value)
  }
}

export function formatDateTime(value) {
  if (!value) return ', '
  try {
    const d = new Date(value)
    if (Number.isNaN(d.getTime())) return String(value)
    return d.toISOString().replace('T', ' ').slice(0, 19)
  } catch {
    return String(value)
  }
}

export function formatBytes(bytes) {
  if (!bytes && bytes !== 0) return ', '
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`
}

export function shortHash(hash) {
  if (!hash) return ', '
  return `${hash.slice(0, 10)}...${hash.slice(-8)}`
}

export function scoreColor(score) {
  if (score >= 0.6) return 'var(--bad)'
  if (score >= 0.4) return 'var(--warn)'
  return 'var(--ok)'
}

export function sentimentColor(label) {
  if (label === 'positive') return 'var(--ok)'
  if (label === 'negative') return 'var(--bad)'
  return 'var(--ink-soft)'
}

export function truncate(text, max = 220) {
  if (!text) return ''
  return text.length > max ? `${text.slice(0, max)}...` : text
}
