import type { PO } from '../types'
import { fmtDate } from '../utils'

interface Props {
  po: PO | null
  onClose: () => void
}

export default function ApprovalInfoModal({ po, onClose }: Props) {
  if (!po) return null

  return (
    <>
      <div className="modal fade show d-block" tabIndex={-1} onClick={onClose}>
        <div
          className="modal-dialog modal-dialog-centered"
          style={{ maxWidth: 440 }}
          onClick={(e) => e.stopPropagation()}
        >
          <div className="modal-content">
            <div className="modal-header" style={{ background: '#198754', color: '#fff' }}>
              <h6 className="modal-title fw-bold">
                <i className="bi bi-check-circle-fill me-2" />
                PO Validada — {po.numero_po || `#${po.id}`}
              </h6>
              <button type="button" className="btn-close btn-close-white" onClick={onClose} />
            </div>

            <div className="modal-body p-4">
              <div className="row g-3 mb-3">
                <div className="col-7">
                  <div className="text-muted" style={{ fontSize: '.72rem', textTransform: 'uppercase', letterSpacing: '.5px' }}>
                    Fornecedor
                  </div>
                  <div className="fw-bold" style={{ color: 'var(--vtex-dark)' }}>
                    {po.fornecedor || '—'}
                  </div>
                </div>
                <div className="col-5">
                  <div className="text-muted" style={{ fontSize: '.72rem', textTransform: 'uppercase', letterSpacing: '.5px' }}>
                    Data de Criação
                  </div>
                  <div style={{ fontSize: '.88rem' }}>{fmtDate(po.data_criacao)}</div>
                </div>
              </div>

              <div
                className="p-3 rounded d-flex align-items-center gap-3"
                style={{ background: '#f0fff4', border: '1px solid #b7dfcb' }}
              >
                <i className="bi bi-person-check-fill" style={{ fontSize: '1.6rem', color: '#198754' }} />
                <div>
                  <div className="text-muted" style={{ fontSize: '.72rem', textTransform: 'uppercase', letterSpacing: '.5px' }}>
                    Aprovado por
                  </div>
                  <div className="fw-bold" style={{ fontSize: '.95rem', color: '#198754' }}>
                    {po.aprovado_por || '—'}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
      <div className="modal-backdrop fade show" />
    </>
  )
}
