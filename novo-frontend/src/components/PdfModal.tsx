import type { PdfInfo } from '../types'

interface Props {
  info: PdfInfo | null
  onClose: () => void
}

export default function PdfModal({ info, onClose }: Props) {
  if (!info) return null

  return (
    <>
      <div className="modal fade show d-block" tabIndex={-1} onClick={onClose}>
        <div
          className="modal-dialog modal-xl modal-dialog-centered"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="modal-content">
            <div className="modal-header" style={{ background: 'var(--vtex-dark)', color: '#fff' }}>
              <h6 className="modal-title fw-bold">
                <i className="bi bi-file-earmark-pdf me-2" />
                {info.numeroPO}
              </h6>
              <div className="d-flex gap-2 ms-auto">
                <a href={info.url} target="_blank" rel="noreferrer" className="btn btn-sm btn-outline-light">
                  <i className="bi bi-download me-1" />
                  Baixar
                </a>
                <button type="button" className="btn-close btn-close-white" onClick={onClose} />
              </div>
            </div>
            <div className="modal-body p-2">
              <iframe className="pdf-frame" src={info.url} title={info.numeroPO} />
            </div>
          </div>
        </div>
      </div>
      <div className="modal-backdrop fade show" />
    </>
  )
}
