import type { PO, SupplierInfo, PdfInfo } from '../types'
import type { SolicitanteInfo } from './SolicitanteModal'
import { fmt, fmtDate } from '../utils'

interface Props {
  pos: PO[]
  onOpenSupplier: (info: SupplierInfo) => void
  onOpenPdf: (info: PdfInfo) => void
  onValidate: (po: PO) => void
  onOpenDetail: (po: PO) => void
  onOpenRejection: (po: PO) => void
  onOpenApproval: (po: PO) => void
  onOpenSolicitante: (info: SolicitanteInfo) => void
}

function StatusBadge({ po, onValidate, onOpenRejection, onOpenApproval }: { po: PO; onValidate: (po: PO) => void; onOpenRejection: (po: PO) => void; onOpenApproval: (po: PO) => void }) {
  const status = po.status || 'Pendente validação'

  if (status === 'Validado') {
    return (
      <button className="badge-status-validado" onClick={() => onOpenApproval(po)}>
        <i className="bi bi-check-circle-fill me-1" />
        Validado
      </button>
    )
  }

  if (status === 'Rejeitado') {
    return (
      <button className="badge-status-rejeitado" onClick={() => onOpenRejection(po)}>
        <i className="bi bi-x-circle-fill me-1" />
        Rejeitado
      </button>
    )
  }

  const step1Approved = !!(po.step_approvals ?? [])[0]

  if (step1Approved) {
    return (
      <button className="badge-status-validado" onClick={() => onOpenApproval(po)}>
        <i className="bi bi-check-circle-fill me-1" />
        Validado
      </button>
    )
  }

  return (
    <button className="badge-status-pendente" onClick={() => onValidate(po)}>
      <i className="bi bi-hourglass-split me-1" />
      Pendente validação
    </button>
  )
}

export default function POTable({ pos, onOpenSupplier, onOpenPdf, onValidate, onOpenDetail, onOpenRejection, onOpenApproval, onOpenSolicitante }: Props) {
  if (!pos.length) {
    return (
      <tr>
        <td colSpan={13}>
          <div className="state-msg">
            <i className="bi bi-inbox" />
            Nenhuma PO encontrada.
          </div>
        </td>
      </tr>
    )
  }

  return (
    <>
      {pos.map((po) => {
        const saldoOk = po.saldo > 0
        const saldoClass = saldoOk ? 'badge-saldo-ok' : 'badge-saldo-zero'
        const saldoIcon = saldoOk ? 'bi-check-circle-fill' : 'bi-x-circle-fill'

        return (
          <tr key={po.id}>
            <td>
              {po.criado_por ? (
                <button
                  className="btn-fornecedor"
                  onClick={() => onOpenSolicitante({ nome: po.criado_por!, email: po.criado_por_email })}
                >
                  {po.criado_por}
                </button>
              ) : (
                <span style={{ fontSize: '.82rem', color: 'var(--vtex-gray)' }}>—</span>
              )}
            </td>
            <td style={{ fontSize: '.82rem', whiteSpace: 'nowrap' }}>
              {po.responsavel || '—'}
            </td>
            <td>
              <span
                style={{
                  fontFamily: 'monospace',
                  fontSize: '.8rem',
                  fontWeight: 700,
                  color: 'var(--vtex-dark)',
                  background: '#f1f3f5',
                  borderRadius: 6,
                  padding: '2px 8px',
                  letterSpacing: '.5px',
                }}
              >
                {po.purchase_number || '—'}
              </span>
            </td>
            <td style={{ fontSize: '.82rem' }}>{po.area_solicitante || '—'}</td>
            <td style={{ fontSize: '.82rem' }}>{po.centro_custo || '—'}</td>
            <td>
              <button className="btn-fornecedor" style={{ color: 'var(--vtex-pink)' }} onClick={() => onOpenDetail(po)}>
                {po.numero_po || po.id}
              </button>
            </td>
            <td>
              <button
                className="btn-fornecedor"
                onClick={() => onOpenSupplier({
                  razaoSocial: po.fornecedor,
                  cnpj: po.cnpj,
                  pais: po.fornecedor_pais,
                  alertaPj: po.alerta_pj,
                  contatoNome: po.contato_nome,
                  contatoEmail: po.contato_email,
                })}
              >
                {po.fornecedor || '—'}
              </button>
            </td>
            <td>{fmt(po.valor_total)}</td>
            <td>
              <span className={saldoClass}>
                <i className={`bi ${saldoIcon} me-1`} />
                {fmt(po.saldo)}
              </span>
            </td>
            <td style={{ fontSize: '.82rem' }}>{po.condicao_pagamento || '—'}</td>
            <td style={{ fontSize: '.82rem' }}>{fmtDate(po.data_criacao)}</td>
            <td>
              {po.pdf_url ? (
                <button
                  className="btn-ver"
                  onClick={() => onOpenPdf({ url: po.pdf_url!, numeroPO: po.numero_po })}
                >
                  <i className="bi bi-file-earmark-pdf me-1" />
                  Ver Contrato
                </button>
              ) : (
                <span className="text-muted" style={{ fontSize: '.8rem' }}>
                  Sem PDF
                </span>
              )}
            </td>
            <td>
              <StatusBadge po={po} onValidate={onValidate} onOpenRejection={onOpenRejection} onOpenApproval={onOpenApproval} />
            </td>
          </tr>
        )
      })}
    </>
  )
}
