import type { PO } from '../types'
import { fmt, fmtDate } from '../utils'

interface Props {
  po: PO | null
  onClose: () => void
}

function Field({ label, value }: { label: string; value?: string | number | null }) {
  if (!value && value !== 0) return null
  return (
    <div className="mb-2">
      <div className="text-muted" style={{ fontSize: '.7rem', textTransform: 'uppercase', letterSpacing: '.5px' }}>
        {label}
      </div>
      <div style={{ fontSize: '.88rem', wordBreak: 'break-word' }}>{value}</div>
    </div>
  )
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="fw-semibold mt-3 mb-2 pb-1"
      style={{ fontSize: '.72rem', textTransform: 'uppercase', letterSpacing: '.8px', color: 'var(--vtex-pink)', borderBottom: '1px solid #f0f0f0' }}
    >
      {children}
    </div>
  )
}

export default function PODetailModal({ po, onClose }: Props) {
  if (!po) return null

  const valor = po.valor_total ?? 0
  const moeda = po.moeda || 'BRL'

  return (
    <>
      <div className="modal fade show d-block" tabIndex={-1} onClick={onClose}>
        <div
          className="modal-dialog modal-dialog-centered modal-lg"
          style={{ maxWidth: 640 }}
          onClick={(e) => e.stopPropagation()}
        >
          <div className="modal-content">
            {/* Header */}
            <div className="modal-header" style={{ background: 'var(--vtex-dark)', color: '#fff' }}>
              <h6 className="modal-title fw-bold">
                <i className="bi bi-receipt me-2" />
                {po.numero_po || `PO #${po.id}`}
              </h6>
              <button type="button" className="btn-close btn-close-white" onClick={onClose} />
            </div>

            {/* Body — scrollable */}
            <div className="modal-body p-4" style={{ maxHeight: '75vh', overflowY: 'auto' }}>

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
                <div className="col-6"><Field label="País" value={po.fornecedor_pais} /></div>
                <div className="col-6"><Field label="Contato" value={po.contato_nome} /></div>
                <div className="col-12"><Field label="E-mail do Contato" value={po.contato_email} /></div>
              </div>

              {/* ── Contratante (VTEX) ── */}
              <SectionTitle>Contratante (VTEX)</SectionTitle>
              <div className="row g-2">
                <div className="col-8"><Field label="Entidade VTEX" value={po.contratante_nome} /></div>
                <div className="col-4"><Field label="CNPJ VTEX" value={po.contratante_cnpj} /></div>
              </div>

              {/* ── Valores e Moeda ── */}
              <SectionTitle>Valores & Moeda</SectionTitle>
              <div className="row g-2">
                <div className="col-4"><Field label="Moeda" value={moeda} /></div>
                <div className="col-4">
                  <div className="mb-2">
                    <div className="text-muted" style={{ fontSize: '.7rem', textTransform: 'uppercase', letterSpacing: '.5px' }}>Valor Total</div>
                    <div className="fw-bold" style={{ fontSize: '.92rem', color: 'var(--vtex-dark)' }}>{moeda} {fmt(valor)}</div>
                  </div>
                </div>
                <div className="col-4">
                  <div className="mb-2">
                    <div className="text-muted" style={{ fontSize: '.7rem', textTransform: 'uppercase', letterSpacing: '.5px' }}>Saldo</div>
                    <div style={{ fontSize: '.88rem' }}>{moeda} {fmt(po.saldo)}</div>
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

              {/* ── Status & Rastreabilidade ── */}
              <SectionTitle>Status & Rastreabilidade</SectionTitle>
              <div className="row g-2">
                <div className="col-6"><Field label="Status" value={po.status || 'Pendente validação'} /></div>
                <div className="col-6"><Field label="Criado por" value={po.criado_por} /></div>
                <div className="col-6"><Field label="E-mail do Solicitante" value={po.criado_por_email} /></div>
                <div className="col-6"><Field label="Data de Criação" value={fmtDate(po.data_criacao)} /></div>
              </div>
              {po.motivo_rejeicao && (
                <div className="alert alert-danger py-2 px-3 mt-2" style={{ fontSize: '.82rem' }}>
                  <strong>Motivo da rejeição:</strong> {po.motivo_rejeicao}
                </div>
              )}
              {po.thread_url && (
                <a
                  href={po.thread_url}
                  target="_blank"
                  rel="noreferrer"
                  className="d-inline-flex align-items-center gap-1 mt-2"
                  style={{ color: 'var(--vtex-pink)', fontSize: '.85rem' }}
                >
                  <i className="bi bi-slack" />
                  Abrir conversa no Slack
                </a>
              )}
            </div>
          </div>
        </div>
      </div>
      <div className="modal-backdrop fade show" />
    </>
  )
}
