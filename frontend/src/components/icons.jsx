/**
 * Minimal inline icon set.
 *
 * Icons appear only where they clarify an action (close, search, run, refresh,
 * paginate, upload, download, delete, open externally, save, confirm, reject).
 * Names that were previously decorative resolve to `Blank`, which renders
 * nothing, so labels carry the meaning on their own.
 *
 * Every icon is a 24x24 stroked path set, inherits `currentColor`, and is
 * hidden from assistive technology because the adjacent text is the label.
 */

function Svg({ size = 16, className = '', style, children, title }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      style={style}
      role={title ? 'img' : undefined}
      aria-hidden={title ? undefined : true}
      focusable="false"
    >
      {title ? <title>{title}</title> : null}
      {children}
    </svg>
  )
}

/** Renders nothing. Used for former decorative icons. */
export function Blank() {
  return null
}

export function X(props) {
  return (
    <Svg {...props}>
      <path d="M18 6 6 18M6 6l12 12" />
    </Svg>
  )
}

export function Search(props) {
  return (
    <Svg {...props}>
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.6-3.6" />
    </Svg>
  )
}

export function Plus(props) {
  return (
    <Svg {...props}>
      <path d="M12 5v14M5 12h14" />
    </Svg>
  )
}

export function Upload(props) {
  return (
    <Svg {...props}>
      <path d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5" />
      <path d="M4 17v2a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-2" />
    </Svg>
  )
}

export function Download(props) {
  return (
    <Svg {...props}>
      <path d="M12 4v12m0 0 4.5-4.5M12 16l-4.5-4.5" />
      <path d="M4 17v2a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-2" />
    </Svg>
  )
}
export const FileDown = Download

export function RefreshCw(props) {
  return (
    <Svg {...props}>
      <path d="M20 11a8 8 0 0 0-13.7-5.3L4 8" />
      <path d="M4 4v4h4" />
      <path d="M4 13a8 8 0 0 0 13.7 5.3L20 16" />
      <path d="M20 20v-4h-4" />
    </Svg>
  )
}
export const RotateCw = RefreshCw

export function Play(props) {
  return (
    <Svg {...props}>
      <path d="M7 4.5 19 12 7 19.5z" />
    </Svg>
  )
}

export function Trash2(props) {
  return (
    <Svg {...props}>
      <path d="M4 7h16M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
      <path d="M6 7l1 12a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1l1-12" />
      <path d="M10 11v6M14 11v6" />
    </Svg>
  )
}

export function ChevronLeft(props) {
  return (
    <Svg {...props}>
      <path d="M14.5 5 7.5 12l7 7" />
    </Svg>
  )
}

export function ChevronRight(props) {
  return (
    <Svg {...props}>
      <path d="M9.5 5l7 7-7 7" />
    </Svg>
  )
}

export function ArrowLeft(props) {
  return (
    <Svg {...props}>
      <path d="M19 12H5m0 0 6-6m-6 6 6 6" />
    </Svg>
  )
}

export function ExternalLink(props) {
  return (
    <Svg {...props}>
      <path d="M14 5h5v5" />
      <path d="M19 5l-8 8" />
      <path d="M18 14v4a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h4" />
    </Svg>
  )
}

export function Save(props) {
  return (
    <Svg {...props}>
      <path d="M5 4h11l3 3v13a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1z" />
      <path d="M8 4v5h7V4" />
      <path d="M8 14h8v6H8z" />
    </Svg>
  )
}

export function CheckCircle2(props) {
  return (
    <Svg {...props}>
      <circle cx="12" cy="12" r="8.5" />
      <path d="m8.5 12 2.5 2.5 4.5-5" />
    </Svg>
  )
}

export function XCircle(props) {
  return (
    <Svg {...props}>
      <circle cx="12" cy="12" r="8.5" />
      <path d="m9 9 6 6m0-6-6 6" />
    </Svg>
  )
}

export function Eye(props) {
  return (
    <Svg {...props}>
      <path d="M2.5 12S6 6 12 6s9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6z" />
      <circle cx="12" cy="12" r="2.75" />
    </Svg>
  )
}

export function Filter(props) {
  return (
    <Svg {...props}>
      <path d="M4 6h16l-6 7v6l-4-2v-4z" />
    </Svg>
  )
}

export function Menu(props) {
  return (
    <Svg {...props}>
      <path d="M4 7h16M4 12h16M4 17h16" />
    </Svg>
  )
}

/**
 * In-flight indicator. Keeps the `spinner` class so the CSS circle renders,
 * and collapses to a static ring under `prefers-reduced-motion`.
 */
export function Loader({ size = 16, className = '', style }) {
  return (
    <span
      className={className.includes('spinner') ? className : `spinner ${className}`}
      style={{ width: size, height: size, ...style }}
      aria-hidden="true"
    />
  )
}

/* ---------------------------------------------------------------------------
   Former decorative icons. Text labels carry the meaning instead.
   --------------------------------------------------------------------------- */
export const Activity = Blank
export const AlertTriangle = Blank
export const Archive = Blank
export const ArrowUpRight = Blank
export const Bot = Blank
export const Columns3 = Blank
export const Crown = Blank
export const Database = Blank
export const FilePlus2 = Blank
export const FileSpreadsheet = Blank
export const FileText = Blank
export const FileWarning = Blank
export const FlaskConical = Blank
export const Frown = Blank
export const Globe = Blank
export const GraduationCap = Blank
export const HardDriveDownload = Blank
export const History = Blank
export const KeyRound = Blank
export const Layers = Blank
export const LayoutDashboard = Blank
export const Link2 = Blank
export const Radar = Blank
export const Rss = Blank
export const Server = Blank
export const Settings = Blank
export const Share2 = Blank
export const ShieldCheck = Blank
export const ShieldQuestion = Blank
export const SmilePlus = Blank
export const Star = Blank
export const Table2 = Blank
export const Tags = Blank
export const Target = Blank
export const Users = Blank
export const Wifi = Blank
export const WifiOff = Blank
