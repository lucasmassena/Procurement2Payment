interface NavItem {
  id: string
  label: string
  icon: string
}

const NAV_ITEMS: NavItem[] = [
  { id: 'procurement', label: 'PO Approvals', icon: 'bi-receipt-cutoff' },
  { id: 'po-tracking', label: 'PO Tracking', icon: 'bi-kanban' },
]

interface Props {
  open: boolean
  onToggle: () => void
  active: string
  onNavigate: (id: string) => void
}

export default function Sidebar({ open, onToggle, active, onNavigate }: Props) {
  return (
    <aside className={`sidebar ${open ? 'sidebar-open' : 'sidebar-closed'}`}>
      {/* Toggle button */}
      <button className="sidebar-toggle" onClick={onToggle} title={open ? 'Recolher menu' : 'Expandir menu'}>
        <i className={`bi ${open ? 'bi-chevron-left' : 'bi-chevron-right'}`} />
      </button>

      <nav className="sidebar-nav">
        {NAV_ITEMS.map((item) => (
          <button
            key={item.id}
            className={`sidebar-item ${active === item.id ? 'sidebar-item-active' : ''}`}
            onClick={() => onNavigate(item.id)}
            title={!open ? item.label : undefined}
          >
            <i className={`bi ${item.icon} sidebar-item-icon`} />
            {open && <span className="sidebar-item-label">{item.label}</span>}
          </button>
        ))}
      </nav>
    </aside>
  )
}
