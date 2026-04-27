import type { PO } from '../types'

interface Props {
  po: PO | null
  onClose: () => void
}

export default function RejectionReasonModal({ po, onClose }: Props) {
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
            <div className="modal-header" style={{ background: '#dc3545', color: '#fff' }}>
              <h6 className="modal-title fw-bold">
                <i className="bi bi-x-circle-fill me-2" />
                PO Rejeitada — {po.numero_po || `#${po.id}`}
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
                    Rejeitado por
                  </div>
                  <div style={{ fontSize: '.88rem' }}>
                    {po.rejeitado_por || '—'}
                  </div>
                </div>
              </div>

              <div className="mb-1">
                <div className="text-muted" style={{ fontSize: '.72rem', textTransform: 'uppercase', letterSpacing: '.5px' }}>
                  Motivo da Rejeição
                </div>
              </div>
              <div
                className="p-3 rounded"
                style={{ background: '#fff3f3', border: '1px solid #f5c6cb', fontSize: '.9rem', lineHeight: 1.6 }}
              >
                {po.motivo_rejeicao
                  ? po.motivo_rejeicao
                  : <span className="text-muted fst-italic">Motivo não informado.</span>
                }
              </div>
            </div>
          </div>
        </div>
      </div>
      <div className="modal-backdrop fade show" />
    </>
  )
}
