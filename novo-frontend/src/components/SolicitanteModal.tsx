interface SolicitanteInfo {
  nome: string
  email: string | null
}

interface Props {
  info: SolicitanteInfo | null
  onClose: () => void
}

export type { SolicitanteInfo }

export default function SolicitanteModal({ info, onClose }: Props) {
  if (!info) return null

  return (
    <>
      <div className="modal fade show d-block" tabIndex={-1} onClick={onClose}>
        <div
          className="modal-dialog modal-dialog-centered"
          style={{ maxWidth: 360 }}
          onClick={(e) => e.stopPropagation()}
        >
          <div className="modal-content">
            <div className="modal-header" style={{ background: 'var(--vtex-dark)', color: '#fff' }}>
              <h6 className="modal-title fw-bold">
                <i className="bi bi-person-circle me-2" />
                Solicitante
              </h6>
              <button type="button" className="btn-close btn-close-white" onClick={onClose} />
            </div>
            <div className="modal-body p-4">
              <div className="mb-3">
                <div className="text-muted" style={{ fontSize: '.72rem', textTransform: 'uppercase', letterSpacing: '.5px' }}>
                  Nome
                </div>
                <div className="fw-semibold" style={{ fontSize: '.95rem', color: 'var(--vtex-dark)' }}>
                  {info.nome}
                </div>
              </div>
              {info.email ? (
                <div>
                  <div className="text-muted" style={{ fontSize: '.72rem', textTransform: 'uppercase', letterSpacing: '.5px' }}>
                    E-mail
                  </div>
                  <a
                    href={`mailto:${info.email}`}
                    style={{ fontSize: '.9rem', color: 'var(--vtex-pink)', wordBreak: 'break-all' }}
                  >
                    {info.email}
                  </a>
                </div>
              ) : (
                <div className="text-muted" style={{ fontSize: '.85rem' }}>E-mail não disponível</div>
              )}
            </div>
          </div>
        </div>
      </div>
      <div className="modal-backdrop fade show" />
    </>
  )
}
