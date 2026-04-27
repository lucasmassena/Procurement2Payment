import { useState } from 'react'
import type { PO } from '../types'
import { fmt } from '../utils'

interface Props {
  po: PO | null
  onClose: () => void
  onApprove: (id: number) => Promise<void>
  onReject: (id: number, motivo: string) => Promise<void>
}

function Field({ label, value }: { label: string; value?: string | number | null }) {
  if (!value && value !== 0) return null
  return (
    <div className="mb-2">
      <div className="text-muted" style={{ fontSize: '.68rem', textTransform: 'uppercase', letterSpacing: '.5px' }}>
        {label}
      </div>
      <div style={{ fontSize: '.85rem', wordBreak: 'break-word' }}>{value}</div>
    </div>
  )
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="fw-semibold mt-3 mb-2 pb-1"
      style={{ fontSize: '.68rem', textTransform: 'uppercase', letterSpacing: '.8px', color: 'var(--vtex-pink)', borderBottom: '1px solid #f0f0f0' }}
    >
      {children}
    </div>
  )
}

export default function ValidationModal({ po, onClose, onApprove, onReject }: Props) {
  const [loading, setLoading]     = useState(false)
  const [rejecting, setRejecting] = useState(false)
  const [motivo, setMotivo]       = useState('')
  const [error, setError]         = useState<string | null>(null)

  if (!po) return null

  const moeda = po.moeda || 'BRL'

  function handleClose() {
    setRejecting(false)
    setMotivo('')
    setError(null)
    onClose()
  }

  async function handleApprove() {
    setLoading(true)
    setError(null)
    try {
      await onApprove(po!.id)
    } catch {
      setError('Erro ao registrar aprovação. Verifique se o servidor está rodando.')
    } finally {
      setLoading(false)
    }
  }

  async function handleConfirmReject() {
    if (!motivo.trim()) return
    setLoading(true)
    setError(null)
    try {
      await onReject(po!.id, motivo.trim())
      setRejecting(false)
      setMotivo('')
    } catch {
      setError('Erro ao rejeitar. Verifique se o servidor está rodando.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      <div className="modal fade show d-block" tabIndex={-1} onClick={handleClose}>
        <div
          className="modal-dialog modal-dialog-centered modal-lg"
          style={{ maxWidth: 640 }}
          onClick={(e) => e.stopPropagation()}
        >
          <div className="modal-content">
            {/* Header */}
            <div className="modal-header" style={{ background: rejecting ? '#dc3545' : 'var(--vtex-dark)', color: '#fff' }}>
              <h6 className="modal-title fw-bold">
                {rejecting
                  ? <><i className="bi bi-x-octagon me-2" />Motivo da Rejeição</>
                  : <><i className="bi bi-clipboard-check me-2" />Validação da PO — {po.numero_po || po.id}</>
                }
              </h6>
              <div className="d-flex gap-2 ms-auto align-items-center">
                {!rejecting && po.pdf_url && (
                  <a href={po.pdf_url} target="_blank" rel="noreferrer" className="btn btn-sm btn-outline-light">
                    <i className="bi bi-file-earmark-pdf me-1" />Ver Contrato
                  </a>
                )}
                <button type="button" className="btn-close btn-close-white" onClick={handleClose} />
              </div>
            </div>

            {/* Body — step 1: dados completos da PO */}
            {!rejecting && (
              <div className="modal-body p-4" style={{ maxHeight: '65vh', overflowY: 'auto' }}>

                {/* Alerta PJ */}
                {po.alerta_pj && (
                  <div className="alert alert-warning py-2 px-3 mb-3" style={{ fontSize: '.82rem' }}>
                    <i className="bi bi-exclamation-triangle-fill me-2" />
                    {po.alerta_pj}
                  </div>
                )}

                {/* ── Fornecedor ── */}
                <SectionTitle>Fornecedor</SectionTitle>
                <div className="row g-2">
                  <div className="col-6"><Field label="Razão Social" value={po.fornecedor} /></div>
                  <div className="col-6"><Field label="CNPJ / Tax ID" value={po.cnpj} /></div>
                  <div className="col-4"><Field label="País" value={po.fornecedor_pais} /></div>
                  <div className="col-4"><Field label="Contato" value={po.contato_nome} /></div>
                  <div className="col-4"><Field label="E-mail" value={po.contato_email} /></div>
                </div>

                {/* ── Contratante (VTEX) ── */}
                <SectionTitle>Contratante (VTEX)</SectionTitle>
                <div className="row g-2">
                  <div className="col-8"><Field label="Entidade VTEX" value={po.contratante_nome} /></div>
                  <div className="col-4"><Field label="CNPJ VTEX" value={po.contratante_cnpj} /></div>
                </div>

                {/* ── Valores ── */}
                <SectionTitle>Valores & Moeda</SectionTitle>
                <div className="row g-2">
                  <div className="col-4"><Field label="Moeda" value={moeda} /></div>
                  <div className="col-4">
                    <div className="mb-2">
                      <div className="text-muted" style={{ fontSize: '.68rem', textTransform: 'uppercase', letterSpacing: '.5px' }}>Valor Total</div>
                      <div className="fw-bold" style={{ color: 'var(--vtex-dark)', fontSize: '.9rem' }}>{moeda} {fmt(po.valor_total)}</div>
                    </div>
                  </div>
                  <div className="col-12"><Field label="Descrição dos Itens / Impostos" value={po.descricao_itens} /></div>
                </div>

                {/* ── Vigência ── */}
                <SectionTitle>Vigência</SectionTitle>
                <div className="row g-2">
                  <div className="col-6"><Field label="Data de Início" value={po.data_inicio} /></div>
                  <div className="col-6"><Field label="Data de Término" value={po.data_termino} /></div>
                </div>

                {/* ── Escopo ── */}
                <SectionTitle>Escopo / Objeto</SectionTitle>
                <Field label="" value={po.escopo} />

                {/* ── Pagamento ── */}
                <SectionTitle>Pagamento</SectionTitle>
                <div className="row g-2">
                  <div className="col-6"><Field label="Condição de Pagamento" value={po.condicao_pagamento} /></div>
                  <div className="col-6"><Field label="Frequência" value={po.frequencia_pagamento} /></div>
                </div>

                {/* ── Assinaturas ── */}
                {po.assinaturas && (
                  <>
                    <SectionTitle>Assinaturas</SectionTitle>
                    <Field label="" value={po.assinaturas} />
                  </>
                )}
              </div>
            )}

            {/* Body — step 2: motivo da rejeição */}
            {rejecting && (
              <div className="modal-body p-4">
                <p className="text-muted mb-3" style={{ fontSize: '.88rem' }}>
                  Escreva o motivo da rejeição. Uma mensagem será enviada automaticamente para o solicitante no Slack.
                </p>
                <textarea
                  className="form-control"
                  rows={4}
                  placeholder="Ex: O contrato está faltando assinatura do responsável legal..."
                  value={motivo}
                  onChange={(e) => setMotivo(e.target.value)}
                  autoFocus
                  style={{ resize: 'none', fontSize: '.9rem' }}
                />
                <div className="text-muted mt-1" style={{ fontSize: '.75rem' }}>
                  {motivo.trim().length === 0 && 'O motivo é obrigatório para rejeitar.'}
                </div>
              </div>
            )}

            {/* Footer */}
            {error && (
              <div className="px-4 pt-2">
                <div className="alert alert-danger py-2 px-3 mb-0" style={{ fontSize: '.82rem' }}>
                  <i className="bi bi-exclamation-circle me-2" />{error}
                </div>
              </div>
            )}
            <div className="modal-footer justify-content-end gap-2" style={{ borderTop: '1px solid #e9ecef' }}>
              {!rejecting ? (
                <>
                  <button className="btn btn-danger" onClick={() => setRejecting(true)} disabled={loading} style={{ minWidth: 110 }}>
                    <i className="bi bi-x-circle me-1" />Rejeitar
                  </button>
                  <button className="btn btn-success" onClick={handleApprove} disabled={loading} style={{ minWidth: 110 }}>
                    <i className="bi bi-check-circle me-1" />Aprovar
                  </button>
                </>
              ) : (
                <>
                  <button className="btn btn-outline-secondary" onClick={() => setRejecting(false)} disabled={loading}>
                    Voltar
                  </button>
                  <button
                    className="btn btn-danger"
                    onClick={handleConfirmReject}
                    disabled={loading || !motivo.trim()}
                    style={{ minWidth: 160 }}
                  >
                    <i className="bi bi-send me-1" />
                    {loading ? 'Enviando...' : 'Confirmar Rejeição'}
                  </button>
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
