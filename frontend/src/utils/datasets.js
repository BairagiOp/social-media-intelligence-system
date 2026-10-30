/** Shared dataset helpers for the frontend. */

/**
 * Categorical series are drawn as tints of the single accent, from deep to
 * pale, so a chart reads as one family of values rather than a rainbow.
 * Keep these in step with --accent in styles.css.
 */
export const SERIES_RAMP = [
  '#0e3d47',
  '#15535f',
  '#2b7183',
  '#4a93a4',
  '#74b2bf',
  '#a3ccd4',
  '#c6dde2',
  '#e2ecee',
]

export const PLATFORM_COLORS = {
  x: SERIES_RAMP[0],
  reddit: SERIES_RAMP[1],
  mastodon: SERIES_RAMP[2],
  threads: SERIES_RAMP[3],
  youtube: SERIES_RAMP[4],
  unknown: '#9b958a',
}

export function platformColor(platform) {
  return PLATFORM_COLORS[platform] || PLATFORM_COLORS.unknown
}

const FALLBACK = SERIES_RAMP

export function categoricalColor(index, key = '') {
  if (key && PLATFORM_COLORS[key]) return PLATFORM_COLORS[key]
  return FALLBACK[index % FALLBACK.length]
}

export function pickPrimaryDataset(datasets) {
  if (!datasets || !datasets.length) return null
  return (
    datasets.find((d) => d.status === 'PREPROCESSED') ||
    datasets.find((d) => d.status !== 'DELETED') ||
    datasets[0]
  )
}

export const CANONICAL_LABELS = {
  user_id: 'User ID',
  username: 'Username / Handle',
  platform: 'Platform',
  text: 'Post Text',
  headline: 'Headline',
  timestamp: 'Timestamp',
  followers: 'Followers',
  following: 'Following',
  likes: 'Likes',
  comments: 'Comments',
  shares: 'Shares',
  account_age: 'Account Age (days)',
  post_count: 'Post Count',
  posting_frequency: 'Posting Frequency',
  label: 'Target Label',
  misinfo_label: 'Misinformation Label',
  is_automated: 'Automation Label',
  url: 'URL',
  domain: 'Domain',
  source: 'Source',
  language: 'Language',
  reply_to_username: 'Reply-To User',
  shared_from_username: 'Shared-From User',
}
