import { useState, useEffect, useCallback, useRef } from 'react'
import type { AuthUser, PO, SupplierInfo, PdfInfo } from './types'
import type { SolicitanteInfo } from './components/SolicitanteModal'
import { fetchPOs, updatePOStatus, approveStep } from './api'
import LoginOverlay from './components/LoginOverlay'
import Topbar from './components/Topbar'
import StatsBar from './components/StatsBar'
import POTable from './components/POTable'
import SupplierModal from './components/SupplierModal'
import PdfModal from './components/PdfModal'
import ValidationModal from './components/ValidationModal'
import PODetailModal from './components/PODetailModal'
import RejectionReasonModal from './components/RejectionReasonModal'
import ApprovalInfoModal from './components/ApprovalInfoModal'
import Sidebar from './components/Sidebar'
import POTracking from './components/POTracking'
import SolicitanteModal from './components/SolicitanteModal'

const SESSION_KEY = 'procurement_auth'

function loadSession(): AuthUser | null {
  try {
    const stored = JSON.parse(localStorage.getItem(SESSION_KEY) || 'null')
    if (stored && stored.exp > Date.now()) return stored
  } catch {}
  localStorage.removeItem(SESSION_KEY)
  return null
}

export default function App() {
  const [user, setUser] = useState<AuthUser | null>(loadSession)
  const [pos, setPos] = useState<PO[]>([])
  const [search, setSearch] = useState('')
  const [responsavel, setResponsavel] = useState('')
  const responsavelRef = useRef('')
  const [loading, setLoading] = useState(false)
  const [apiError, setApiError] = useState(false)
  const [supplierInfo, setSupplierInfo] = useState<SupplierInfo | null>(null)
  const [pdfInfo, setPdfInfo] = useState<PdfInfo | null>(null)
  const [validationPO, setValidationPO] = useState<PO | null>(null)
  const [detailPO, setDetailPO] = useState<PO | null>(null)
  const [rejectionPO, setRejectionPO] = useState<PO | null>(null)
  const [approvalPO, setApprovalPO] = useState<PO | null>(null)
  const [solicitanteInfo, setSolicitanteInfo] = useState<SolicitanteInfo | null>(null)
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [activePage, setActivePage] = useState('procurement')
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const load = useCallback(async (q = '', resp = '') => {
    setLoading(true)
    setApiError(false)
    try {
      const data = await fetchPOs(q, resp)
      setPos(data)
    } catch {
      setApiError(true)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (user) load()
  }, [user, load])

  function handleSearchChange(e: React.ChangeEvent<HTMLInputElement>) {
    const val = e.target.value
    setSearch(val)
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => load(val.trim(), responsavelRef.current), 350)
  }

  function handleClear() {
    setSearch('')
    load('', responsavelRef.current)
  }

  function handleResponsavelChange(val: string) {
    setResponsavel(val)
    responsavelRef.current = val
    load(search.trim(), val)
  }

  function handleLogout() {
    localStorage.removeItem(SESSION_KEY)
    setUser(null)
    setPos([])
  }

  async function handleApprove(id: number) {
    const result = await approveStep(id, 0, user?.name ?? '', new Date().toISOString())
    setPos((prev) => prev.map((p) => {
      if (p.id !== id) return p
      return {
        ...p,
        step_approvals: result.step_approvals,
        status: result.status,
        aprovado_por: result.step_approvals[0]?.approver ?? p.aprovado_por,
      }
    }))
    setValidationPO(null)
  }

  async function handleReject(id: number, motivo: string) {
    await updatePOStatus(id, 'Rejeitado', motivo, user?.name)
    setPos((prev) => prev.map((p) => (p.id === id ? { ...p, status: 'Rejeitado', motivo_rejeicao: motivo, rejeitado_por: user?.name ?? null } : p)))
    setValidationPO(null)
  }

  if (!user) {
    return <LoginOverlay onLogin={setUser} />
  }

  const RESPONSAVEIS = ['Laurie', 'Julia', 'Fernanda', 'Emily', 'Aylton', 'Ana Caroline', 'Alyne']
  const [filtersOpen, setFiltersOpen] = useState(false)
  const activeFilters = (search ? 1 : 0) + (responsavel ? 1 : 0)
  const colSpan = 13

  return (
    <div className="app-shell">
      <Topbar user={user} onLogout={handleLogout} />

      <div className="app-body">
        <Sidebar
          open={sidebarOpen}
          onToggle={() => setSidebarOpen((v) => !v)}
          active={activePage}
          onNavigate={setActivePage}
        />

        <div className="app-main">
          {activePage === 'po-tracking' ? (
            <POTracking
              pos={pos}
              onOpenDetail={setDetailPO}
              onOpenRejection={setRejectionPO}
              onOpenApproval={setApprovalPO}
            />
          ) : (
            <div className="container-fluid px-4 py-4">
              <StatsBar pos={pos} />

              <div className="main-card">
                <div className="d-flex justify-content-between align-items-center mb-2 flex-wrap gap-2">
                  <h5 className="m-0 fw-semibold" style={{ color: 'var(--vtex-dark)', fontSize: '1rem' }}>
                    Purchase Orders
                  </h5>
                  <button
                    className="btn btn-sm d-flex align-items-center gap-2"
                    style={{
                      border: `1px solid ${filtersOpen || activeFilters > 0 ? 'var(--vtex-pink)' : '#dee2e6'}`,
                      color: filtersOpen || activeFilters > 0 ? 'var(--vtex-pink)' : 'var(--vtex-gray)',
                      background: activeFilters > 0 ? 'var(--vtex-pink-bg)' : '#fff',
                      borderRadius: 8,
                      fontSize: '.82rem',
                      padding: '5px 12px',
                    }}
                    onClick={() => setFiltersOpen((v) => !v)}
                  >
                    <i className="bi bi-funnel" />
                    Filtros
                    {activeFilters > 0 && (
                      <span
                        style={{
                          background: 'var(--vtex-pink)',
                          color: '#fff',
                          borderRadius: 10,
                          fontSize: '.68rem',
                          fontWeight: 700,
                          padding: '1px 7px',
                        }}
                      >
                        {activeFilters}
                      </span>
                    )}
                    <i className={`bi bi-chevron-${filtersOpen ? 'up' : 'down'}`} style={{ fontSize: '.7rem' }} />
                  </button>
                </div>

                {filtersOpen && (
                  <div
                    className="d-flex gap-3 flex-wrap align-items-end mb-3 p-3 rounded"
                    style={{ background: '#f8f9fc', border: '1px solid #e9ecef' }}
                  >
                    <div style={{ flex: '1 1 220px' }}>
                      <label className="form-label mb-1" style={{ fontSize: '.72rem', fontWeight: 600, color: 'var(--vtex-gray)', textTransform: 'uppercase', letterSpacing: '.5px' }}>
                        Fornecedor
                      </label>
                      <div className="input-group input-group-sm">
                        <span className="input-group-text bg-white border-end-0">
                          <i className="bi bi-search text-muted" />
                        </span>
                        <input
                          type="text"
                          className="form-control border-start-0 ps-0"
                          placeholder="Buscar por fornecedor..."
                          value={search}
                          onChange={handleSearchChange}
                        />
                        {search && (
                          <button className="btn btn-outline-secondary btn-sm" onClick={handleClear} title="Limpar">
                            <i className="bi bi-x" />
                          </button>
                        )}
                      </div>
                    </div>
                    <div style={{ flex: '1 1 180px' }}>
                      <label className="form-label mb-1" style={{ fontSize: '.72rem', fontWeight: 600, color: 'var(--vtex-gray)', textTransform: 'uppercase', letterSpacing: '.5px' }}>
                        Responsável
                      </label>
                      <select
                        className="form-select form-select-sm"
                        value={responsavel}
                        onChange={(e) => handleResponsavelChange(e.target.value)}
                      >
                        <option value="">Todos</option>
                        {RESPONSAVEIS.map((r) => (
                          <option key={r} value={r}>{r}</option>
                        ))}
                      </select>
                    </div>
                    {activeFilters > 0 && (
                      <button
                        className="btn btn-sm btn-outline-secondary"
                        style={{ height: 31, alignSelf: 'flex-end' }}
                        onClick={() => { handleClear(); handleResponsavelChange('') }}
                      >
                        <i className="bi bi-x-circle me-1" />Limpar filtros
                      </button>
                    )}
                  </div>
                )}

                <div className="table-responsive">
                  <table className="table po-table mb-0">
                    <thead>
                      <tr>
                        <th>Solicitante</th>
                        <th>Responsável</th>
                        <th>Purchase Number</th>
                        <th>Área Solicitante</th>
                        <th>Centro de Custo</th>
                        <th>ID da PO</th>
                        <th>Fornecedor</th>
                        <th>Valor Total</th>
                        <th>Saldo Disponível</th>
                        <th>Pagamento</th>
                        <th>Data</th>
                        <th>Contrato</th>
                        <th>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {loading ? (
                        <tr>
                          <td colSpan={colSpan}>
                            <div className="state-msg">
                              <i className="bi bi-arrow-repeat" />
                              Carregando...
                            </div>
                          </td>
                        </tr>
                      ) : apiError ? (
                        <tr>
                          <td colSpan={colSpan}>
                            <div className="state-msg text-danger">
                              <i className="bi bi-wifi-off" />
                              Não foi possível conectar à API.
                              <br />
                              <small>Verifique se o servidor está rodando em http://localhost:8000</small>
                            </div>
                          </td>
                        </tr>
                      ) : (
                        <POTable
                          pos={pos}
                          onOpenSupplier={setSupplierInfo}
                          onOpenPdf={setPdfInfo}
                          onValidate={setValidationPO}
                          onOpenDetail={setDetailPO}
                          onOpenRejection={setRejectionPO}
                          onOpenApproval={setApprovalPO}
                          onOpenSolicitante={setSolicitanteInfo}
                        />
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}
        </div>{/* app-main */}
      </div>{/* app-body */}

      <SupplierModal info={supplierInfo} onClose={() => setSupplierInfo(null)} />
      <PdfModal info={pdfInfo} onClose={() => setPdfInfo(null)} />
      <ValidationModal
        po={validationPO}
        onClose={() => setValidationPO(null)}
        onApprove={handleApprove}
        onReject={handleReject}
      />
      <PODetailModal po={detailPO} onClose={() => setDetailPO(null)} />
      <RejectionReasonModal po={rejectionPO} onClose={() => setRejectionPO(null)} />
      <ApprovalInfoModal po={approvalPO} onClose={() => setApprovalPO(null)} />
      <SolicitanteModal info={solicitanteInfo} onClose={() => setSolicitanteInfo(null)} />
    </div>
  )
}
