import { useState } from 'react'
import type { PO } from '../types'
import { fmt, fmtDate } from '../utils'
import POTimelineModal from './POTimelineModal'

interface Props {
  pos: PO[]
  onOpenDetail: (po: PO) => void
  onOpenRejection: (po: PO) => void
  onOpenApproval: (po: PO) => void
}

const COLUMNS = [
  {
    status: 'Pendente validação',
    label: 'Pendente',
    icon: 'bi-hourglass-split',
    color: '#b45309',
    bg: '#fffbeb',
    border: '#fde68a',
  },
  {
    status: 'Validado',
    label: 'Validado',
    icon: 'bi-check-circle-fill',
    color: '#16a34a',
    bg: '#f0fdf4',
    border: '#bbf7d0',
  },
  {
    status: 'Rejeitado',
    label: 'Rejeitado',
    icon: 'bi-x-circle-fill',
    color: '#dc2626',
    bg: '#fef2f2',
    border: '#fecaca',
  },
]

function KanbanCard({ po, col, onCardClick, onOpenDetail, onOpenRejection, onOpenApproval }: {
  po: PO
  col: typeof COLUMNS[0]
  onCardClick: (po: PO) => void
  onOpenDetail: (po: PO) => void
  onOpenRejection: (po: PO) => void
  onOpenApproval: (po: PO) => void
}) {
  const isPending = !po.status || po.status === 'Pendente validação'

  function handleBadgeClick(e: React.MouseEvent) {
    e.stopPropagation()
    if (po.status === 'Validado') onOpenApproval(po)
    else if (po.status === 'Rejeitado') onOpenRejection(po)
    else onCardClick(po)
  }

  return (
    <div
      className={`kanban-card${isPending ? ' kanban-card-clickable' : ''}`}
      style={{ borderLeft: `3px solid ${col.color}` }}
      onClick={isPending ? () => onCardClick(po) : undefined}
      title={isPending ? 'Ver fluxo de aprovação' : undefined}
    >
      <div className="d-flex justify-content-between align-items-start mb-1">
        <button
          className="kanban-po-id"
          style={{ color: col.color }}
          onClick={(e) => { e.stopPropagation(); onOpenDetail(po) }}
        >
          {po.numero_po || `#${po.id}`}
        </button>
        <span className="kanban-date">{fmtDate(po.data_criacao)}</span>
      </div>

      <div className="kanban-supplier">{po.fornecedor || '—'}</div>
      <div className="kanban-value">{fmt(po.valor_total)}</div>

      {po.data_inicio && (
        <div className="kanban-meta">
          <i className="bi bi-calendar-event me-1" />
          {po.data_inicio}
          {po.data_termino ? ` → ${po.data_termino}` : ''}
        </div>
      )}
      {po.condicao_pagamento && (
        <div className="kanban-meta">
          <i className="bi bi-credit-card me-1" />
          {po.condicao_pagamento}
        </div>
      )}

      <div className="mt-2 d-flex align-items-center gap-2">
        <button
          className="kanban-badge"
          style={{ color: col.color, background: col.bg, borderColor: col.border }}
          onClick={handleBadgeClick}
        >
          <i className={`bi ${col.icon} me-1`} />
          {col.label}
        </button>
        {isPending && (
          <span style={{ fontSize: '.68rem', color: 'var(--vtex-gray)' }}>
            <i className="bi bi-diagram-3 me-1" />
            Ver fluxo
          </span>
        )}
      </div>
    </div>
  )
}

export default function POTracking({ pos, onOpenDetail, onOpenRejection, onOpenApproval }: Props) {
  const [timelinePO, setTimelinePO] = useState<PO | null>(null)

  const byStatus = (s: string) => pos.filter((p) => (p.status || 'Pendente validação') === s)
  const valorTotal = (list: PO[]) => list.reduce((s, p) => s + (p.valor_total || 0), 0)

  return (
    <div className="container-fluid px-4 py-4">

      {/* ── Resumo por status ── */}
      <div className="row g-3 mb-4">
        {COLUMNS.map((col) => {
          const list = byStatus(col.status)
          return (
            <div key={col.status} className="col-12 col-md-4">
              <div className="stat-box" style={{ borderLeftColor: col.color }}>
                <div className="label" style={{ color: col.color }}>
                  <i className={`bi ${col.icon} me-1`} />
                  {col.label}
                </div>
                <div className="value" style={{ color: col.color }}>{list.length}</div>
                <div style={{ fontSize: '.78rem', color: 'var(--vtex-gray)', marginTop: 2 }}>
                  {fmt(valorTotal(list))}
                </div>
              </div>
            </div>
          )
        })}
      </div>

      {/* ── Board Kanban ── */}
      <div className="main-card">
        <h5 className="m-0 fw-semibold mb-3" style={{ color: 'var(--vtex-dark)', fontSize: '1rem' }}>
          <i className="bi bi-kanban me-2" style={{ color: 'var(--vtex-pink)' }} />
          Board
        </h5>
        <div className="kanban-board">
          {COLUMNS.map((col) => {
            const list = byStatus(col.status)
            return (
              <div key={col.status} className="kanban-col">
                <div className="kanban-col-header" style={{ borderBottom: `2px solid ${col.color}` }}>
                  <span style={{ color: col.color, fontWeight: 700 }}>
                    <i className={`bi ${col.icon} me-1`} />
                    {col.label}
                  </span>
                  <span className="kanban-col-count" style={{ background: col.bg, color: col.color, border: `1px solid ${col.border}` }}>
                    {list.length}
                  </span>
                </div>
                <div className="kanban-cards">
                  {list.length === 0 ? (
                    <div className="kanban-empty">Nenhuma PO</div>
                  ) : (
                    list.map((po) => (
                      <KanbanCard
                        key={po.id}
                        po={po}
                        col={col}
                        onCardClick={setTimelinePO}
                        onOpenDetail={onOpenDetail}
                        onOpenRejection={onOpenRejection}
                        onOpenApproval={onOpenApproval}
                      />
                    ))
                  )}
                </div>
              </div>
            )
          })}
        </div>
      </div>

      <POTimelineModal po={timelinePO} onClose={() => setTimelinePO(null)} />
    </div>
  )
}
