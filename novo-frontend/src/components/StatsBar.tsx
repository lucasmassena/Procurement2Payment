import type { PO } from '../types'
import { fmt } from '../utils'

interface Props {
  pos: PO[]
}

export default function StatsBar({ pos }: Props) {
  const total = pos.length
  const valor = pos.reduce((s, p) => s + (p.valor_total || 0), 0)
  const saldo = pos.reduce((s, p) => s + (p.saldo || 0), 0)
  const zeros = pos.filter((p) => p.saldo <= 0).length

  return (
    <div className="row g-3 mb-4">
      <div className="col-12 col-sm-6 col-xl-3">
        <div className="stat-box">
          <div className="label">Total de POs</div>
          <div className="value">{total}</div>
        </div>
      </div>
      <div className="col-12 col-sm-6 col-xl-3">
        <div className="stat-box">
          <div className="label">Valor Comprometido</div>
          <div className="value">{fmt(valor)}</div>
        </div>
      </div>
      <div className="col-12 col-sm-6 col-xl-3">
        <div className="stat-box">
          <div className="label">Saldo Total Disponível</div>
          <div className="value">{fmt(saldo)}</div>
        </div>
      </div>
      <div className="col-12 col-sm-6 col-xl-3">
        <div className="stat-box">
          <div className="label">POs com Saldo Zero</div>
          <div className="value">{zeros}</div>
        </div>
      </div>
    </div>
  )
}
