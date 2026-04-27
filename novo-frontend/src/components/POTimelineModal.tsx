import type { PO } from '../types'
import { fmt, fmtDate } from '../utils'

interface Props {
  po: PO | null
  onClose: () => void
}

const STEPS = [
  'Review - Procurement Leader',
  'Approval - CC Owner Appointed',
  'Approval - CC Owner',
  'Review - Business',
  'Review - Finance Leaders',
]

type StepStatus = 'pending' | 'done' | 'rejected'

const STEP_STYLES: Record<StepStatus, { dot: string; line: string; label: string; icon: string }> = {
  pending: {
    dot: '#f59e0b',
    line: '#fde68a',
    label: '#92400e',
    icon: 'bi-hourglass-split',
  },
  done: {
    dot: '#16a34a',
    line: '#bbf7d0',
    label: '#14532d',
    icon: 'bi-check-lg',
  },
  rejected: {
    dot: '#dc2626',
    line: '#fecaca',
    label: '#7f1d1d',
    icon: 'bi-x-lg',
  },
}

export default function POTimelineModal({ po, onClose }: Props) {
  if (!po) return null

  const approvals = po.step_approvals ?? Array(5).fill(null)

  function getStepStatus(i: number): StepStatus {
    if (po!.status === 'Rejeitado') return 'rejected'
    return approvals[i] ? 'done' : 'pending'
  }

  return (
    <>
      <div className="modal fade show d-block" tabIndex={-1} onClick={onClose}>
        <div
          className="modal-dialog modal-dialog-centered"
          style={{ maxWidth: 460 }}
          onClick={(e) => e.stopPropagation()}
        >
          <div className="modal-content">
            <div className="modal-header" style={{ background: 'var(--vtex-dark)', color: '#fff' }}>
              <h6 className="modal-title fw-bold">
                <i className="bi bi-diagram-3 me-2" />
                Fluxo de Aprovação — {po.numero_po || `#${po.id}`}
              </h6>
              <button type="button" className="btn-close btn-close-white" onClick={onClose} />
            </div>

            <div className="modal-body p-4">
              {/* PO summary */}
              <div className="d-flex gap-3 mb-4 p-3 rounded" style={{ background: '#f8f9fc', fontSize: '.82rem' }}>
                <div>
                  <div className="text-muted" style={{ fontSize: '.68rem', textTransform: 'uppercase', letterSpacing: '.5px' }}>Fornecedor</div>
                  <div className="fw-bold" style={{ color: 'var(--vtex-dark)' }}>{po.fornecedor || '—'}</div>
                </div>
                <div className="ms-auto text-end">
                  <div className="text-muted" style={{ fontSize: '.68rem', textTransform: 'uppercase', letterSpacing: '.5px' }}>Valor</div>
                  <div className="fw-bold" style={{ color: 'var(--vtex-dark)' }}>{fmt(po.valor_total)}</div>
                </div>
                <div className="text-end">
                  <div className="text-muted" style={{ fontSize: '.68rem', textTransform: 'uppercase', letterSpacing: '.5px' }}>Criação</div>
                  <div style={{ color: 'var(--vtex-dark)' }}>{fmtDate(po.data_criacao)}</div>
                </div>
              </div>

              {/* Timeline */}
              <div className="po-timeline">
                {STEPS.map((step, i) => {
                  const s = getStepStatus(i)
                  const style = STEP_STYLES[s]
                  const approval = approvals[i]
                  const isLast = i === STEPS.length - 1

                  return (
                    <div key={i} className="po-timeline-step">
                      {/* Dot + connector */}
                      <div className="po-timeline-track">
                        <div
                          className="po-timeline-dot"
                          style={{
                            background: style.dot,
                            boxShadow: s === 'pending' ? `0 0 0 4px ${style.line}` : undefined,
                          }}
                        >
                          <i
                            className={`bi ${style.icon}`}
                            style={{ fontSize: '.6rem', color: '#fff', lineHeight: 1 }}
                          />
                        </div>
                        {!isLast && (
                          <div
                            className="po-timeline-line"
                            style={{ background: style.line }}
                          />
                        )}
                      </div>

                      {/* Label */}
                      <div className="po-timeline-label" style={{ color: style.label }}>
                        <span className="po-timeline-step-num">Etapa {i + 1}</span>
                        <span className="po-timeline-step-name">{step}</span>
                        <span
                          className="po-timeline-status-tag"
                          style={{ background: style.line, color: style.label }}
                        >
                          {s === 'pending' ? 'Aguardando' : s === 'done' ? 'Concluído' : 'Rejeitado'}
                        </span>
                        {s === 'done' && approval && (
                          <span className="po-timeline-approver">
                            <i className="bi bi-person-check me-1" />
                            {approval.approver}
                            <span className="po-timeline-approver-date">
                              {new Date(approval.date).toLocaleDateString('pt-BR', {
                                day: '2-digit', month: '2-digit', year: 'numeric',
                              })}
                            </span>
                          </span>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          </div>
        </div>
      </div>
      <div className="modal-backdrop fade show" />
    </>
  )
}
