import axios from 'axios'
import type { PO, StepApproval } from './types'

const BASE = import.meta.env.VITE_API_URL ?? ''

export async function fetchPOs(search = '', responsavel = ''): Promise<PO[]> {
  const params: Record<string, string> = {}
  if (search) params.search = search
  if (responsavel) params.responsavel = responsavel
  const { data } = await axios.get<PO[]>(`${BASE}/api/pos`, { params })
  return data
}

export async function verifyGoogleToken(credential: string) {
  const { data } = await axios.post<{ email: string; name: string; picture: string }>(
    `${BASE}/auth/google`,
    { credential },
  )
  return data
}

export async function updatePOStatus(id: number, status: string, motivo?: string, responsavel?: string) {
  await axios.patch(`${BASE}/api/pos/${id}/status`, {
    status,
    motivo_rejeicao: motivo,
    rejeitado_por: status === 'Rejeitado' ? responsavel : undefined,
    aprovado_por:  status === 'Validado'  ? responsavel : undefined,
  })
}

export async function approveStep(id: number, step: number, approver: string, date: string) {
  const { data } = await axios.patch<{ ok: boolean; status: string; step_approvals: (StepApproval | null)[] }>(
    `${BASE}/api/pos/${id}/approve-step`,
    { step, approver, date },
  )
  return data
}
