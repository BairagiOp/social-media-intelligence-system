export default function StatCard({ label, value, sub, subTone = '', icon: Icon }) {
  return (
    <div className="stat-card">
      {Icon && <Icon size={17} className="stat-icon" />}
      <span className="stat-label">{label}</span>
      <span className="stat-value">{value}</span>
      {sub && <span className={`stat-sub ${subTone}`}>{sub}</span>}
    </div>
  )
}
