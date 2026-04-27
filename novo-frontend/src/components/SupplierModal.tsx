import type { SupplierInfo } from '../types'

interface Props {
  info: SupplierInfo | null
  onClose: () => void
}

function Field({ label, value }: { label: string; value?: string | null }) {
  if (!value) return null
  return (
    <div className="mb-3">
      <div className="text-muted" style={{ fontSize: '.72rem', textTransform: 'uppercase', letterSpacing: '.5px' }}>
        {label}
      </div>
      <div style={{ fontSize: '.92rem', wordBreak: 'break-word' }}>{value}</div>
    </div>
  )
}

export default function SupplierModal({ info, onClose }: Props) {
  if (!info) return null

  return (
    <>
      <div className="modal fade show d-block" tabIndex={-1} onClick={onClose}>
        <div
          className="modal-dialog modal-dialog-centered"
          style={{ maxWidth: 420 }}
          onClick={(e) => e.stopPropagation()}
        >
          <div className="modal-content">
            <div className="modal-header" style={{ background: 'var(--vtex-dark)', color: '#fff' }}>
              <h6 className="modal-title fw-bold">
                <i className="bi bi-building me-2" />
                Dados do Fornecedor
              </h6>
              <button type="button" className="btn-close btn-close-white" onClick={onClose} />
            </div>

            <div className="modal-body p-4">
              {info.alertaPj && (
                <div className="alert alert-warning py-2 px-3 mb-3" style={{ fontSize: '.82rem' }}>
                  <i className="bi bi-exclamation-triangle-fill me-2" />
                  {info.alertaPj}
                </div>
              )}

              <div className="mb-3">
                <div className="text-muted" style={{ fontSize: '.72rem', textTransform: 'uppercase', letterSpacing: '.5px' }}>
                  Razão Social
                </div>
                <div className="fw-bold" style={{ fontSize: '1rem', color: 'var(--vtex-dark)' }}>
                  {info.razaoSocial || '—'}
                </div>
              </div>

              <div className="row g-0">
                <div className="col-7">
                  <div className="mb-3">
                    <div className="text-muted" style={{ fontSize: '.72rem', textTransform: 'uppercase', letterSpacing: '.5px' }}>
                      CNPJ / Tax ID
                    </div>
                    <div style={{ fontFamily: 'monospace', fontSize: '.92rem' }}>
                      {info.cnpj || '—'}
                    </div>
                  </div>
                </div>
                <div className="col-5">
                  <Field label="País" value={info.pais} />
                </div>
              </div>

              {(info.contatoNome || info.contatoEmail) && (
                <>
                  <hr className="my-2" />
                  <Field label="Contato" value={info.contatoNome} />
                  {info.contatoEmail && (
                    <div className="mb-1">
                      <div className="text-muted" style={{ fontSize: '.72rem', textTransform: 'uppercase', letterSpacing: '.5px' }}>
                        E-mail
                      </div>
                      <a href={`mailto:${info.contatoEmail}`} style={{ fontSize: '.88rem', color: 'var(--vtex-pink)' }}>
                        {info.contatoEmail}
                      </a>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      </div>
      <div className="modal-backdrop fade show" />
    </>
  )
}
