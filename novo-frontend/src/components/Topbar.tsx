import type { AuthUser } from '../types'

interface Props {
  user: AuthUser
  onLogout: () => void
}

export default function Topbar({ user, onLogout }: Props) {
  return (
    <div className="topbar">
      <img src="/vtex-logo-white.svg" className="topbar-logo" alt="VTEX" />
      <span className="topbar-divider" />
      <span className="brand">PO Orders</span>
      <div className="user-section">
        {user.picture && (
          <img src={user.picture} className="user-avatar" alt={user.name} />
        )}
        <span className="user-name">{user.name || user.email}</span>
        <button className="btn-logout" onClick={onLogout}>
          <i className="bi bi-box-arrow-right me-1" />
          Sair
        </button>
      </div>
    </div>
  )
}
