export interface StepApproval {
  approver: string
  date: string
}

export interface PO {
  id: number
  numero_po: string
  fornecedor: string
  cnpj: string
  valor_total: number
  valor_utilizado: number
  saldo: number
  condicao_pagamento: string | null
  status: string | null
  pdf_url: string | null
  criado_por: string | null
  criado_por_email: string | null
  thread_url: string | null
  motivo_rejeicao: string | null
  rejeitado_por: string | null
  aprovado_por: string | null
  data_criacao: string
  // Novos campos de extração
  moeda: string | null
  data_inicio: string | null
  data_termino: string | null
  descricao_itens: string | null
  escopo: string | null
  contratante_nome: string | null
  contratante_cnpj: string | null
  fornecedor_pais: string | null
  alerta_pj: string | null
  contato_nome: string | null
  contato_email: string | null
  frequencia_pagamento: string | null
  assinaturas: string | null
  step_approvals: (StepApproval | null)[]
  responsavel: string | null
  purchase_number: string | null
  area_solicitante: string | null
  centro_custo: string | null
}

export interface AuthUser {
  email: string
  name: string
  picture: string
  exp: number
}

export interface SupplierInfo {
  razaoSocial: string
  cnpj: string
  pais?: string | null
  alertaPj?: string | null
  contatoNome?: string | null
  contatoEmail?: string | null
}

export interface PdfInfo {
  url: string
  numeroPO: string
}
