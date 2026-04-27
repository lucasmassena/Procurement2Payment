"""
Procurement Bot — Regularização e Parcerias VTEX
=================================================
Stack: LangGraph + Gemini 2.0 Flash (structured output) + SQLite + SqliteSaver
"""

from __future__ import annotations

import io
import json
import os
import sqlite3
import sys
import uuid
from typing import Annotated, Any, Literal, Optional

if sys.stdout.isatty() and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.isatty() and hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import pdfplumber
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import interrupt
from pydantic import BaseModel, Field
from typing_extensions import TypedDict


# ==============================================================================
# CONFIGURAÇÃO
# ==============================================================================

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "GEMINI_KEY_REMOVED")
MODEL = "gemini-2.0-flash"

DB_PATH = os.path.join(os.path.dirname(__file__), "procurement.db")

REQUIRED_FIELDS: list[str] = [
    "razao_social",
    "cnpj",
    "moeda",
    "valor_total",
    "condicao_pagamento",
]

CATEGORIES: list[str] = [
    "Vendor/Supplier",
    "Partnership - SIs implementing POC",
    "Partnership - commission payment",
    "Partnership - Prime",
    "Partnership - others",
    "Sponsorship",
    "Legal and Litigation Service Providers/Law Firms",
]

# Documentos obrigatórios adicionais por categoria
DOCS_REQUIRED_BY_CATEGORY: dict[str, list[str]] = {
    "Partnership - commission payment": ["MPA - Master Partner Agreement"],
}

# Tipos de documento que sozinhos não servem como base para uma PO
DISCARD_DOC_TYPES: set[str] = {"invoice", "nota_fiscal", "recibo", "boleto"}


# ==============================================================================
# SCHEMA DE EXTRAÇÃO (Pydantic)
# ==============================================================================

class ContractData(BaseModel):
    """Schema de extração estruturada — Gemini preenche apenas o que encontrar explicitamente."""

    # ── Identificação do Fornecedor ──────────────────────────────────────────
    razao_social: Optional[str] = Field(
        None, description="Razão Social ou nome completo do FORNECEDOR/CONTRATADO conforme preâmbulo do contrato.",
    )
    cnpj: Optional[str] = Field(
        None, description="CNPJ ou CPF do fornecedor — apenas dígitos numéricos, sem pontos/traços/barras.",
    )
    fornecedor_pais: Optional[str] = Field(None, description="País de origem do fornecedor conforme consta no contrato.")
    alerta_pj: Optional[str] = Field(
        None,
        description=(
            "Se a primeira palavra da Razão Social for nome próprio humano (ex: 'Victor', 'Maria'), "
            "preencha com 'ALERTA: possível risco PJ/Contractor'. Caso contrário, None."
        ),
    )

    # ── Contratante (VTEX) ───────────────────────────────────────────────────
    contratante_nome: Optional[str] = Field(
        None, description="Nome exato da entidade VTEX identificada como CONTRATANTE no preâmbulo.",
    )
    contratante_cnpj: Optional[str] = Field(
        None, description="CNPJ/Tax ID da entidade VTEX contratante — apenas dígitos numéricos.",
    )

    # ── Valores e Moeda ──────────────────────────────────────────────────────
    moeda: Optional[str] = Field(
        None, description="Moeda EXPLICITAMENTE citada no contrato (ex: BRL, USD, EUR). Nunca inferir pelo país.",
    )
    valor_total: Optional[float] = Field(
        None, description="Valor total do contrato — número decimal sem símbolo. '90 mil' = 90000.0.",
    )
    descricao_itens: Optional[str] = Field(
        None, description="Descrição dos itens/serviços com valores e quantidades.",
    )

    # ── Datas e Vigência ─────────────────────────────────────────────────────
    data_inicio: Optional[str] = Field(
        None, description="Data de início exatamente como escrita no contrato. Nunca calcule.",
    )
    data_termino: Optional[str] = Field(
        None, description="Data de término ou prazo de vigência exatamente como escrito.",
    )

    # ── Escopo e Pagamento ───────────────────────────────────────────────────
    escopo: Optional[str] = Field(None, description="Escopo ou objeto do contrato — resumo do que está sendo contratado.")
    condicao_pagamento: Optional[str] = Field(None, description="Condição/prazo de pagamento.")
    frequencia_pagamento: Optional[str] = Field(None, description="Frequência de faturamento (ex: mensal, anual).")

    # ── Contato ──────────────────────────────────────────────────────────────
    contato_nome: Optional[str] = Field(None, description="Nome do contato/representante do fornecedor.")
    contato_email: Optional[str] = Field(None, description="E-mail do contato do fornecedor.")

    # ── Classificação e Compliance ───────────────────────────────────────────
    categoria: Optional[str] = Field(
        None,
        description=(
            "Categoria da solicitação. Escolha EXATAMENTE UMA entre: "
            "Vendor/Supplier | Partnership - SIs implementing POC | "
            "Partnership - commission payment | Partnership - Prime | "
            "Partnership - others | Sponsorship | "
            "Legal and Litigation Service Providers/Law Firms"
        ),
    )
    categoria_confianca: Optional[int] = Field(
        None, description="Confiança na classificação da categoria, de 0 a 100.",
    )
    documentos_identificados: Optional[list[str]] = Field(
        None,
        description=(
            "Lista de tipos de documentos identificados no conjunto enviado. "
            "Valores possíveis: contrato | proposta_comercial | mpa | invoice | nota_fiscal | recibo | boleto | outro"
        ),
    )
    assinaturas: Optional[str] = Field(
        None, description="Status das assinaturas: quem assinou e se há campos em branco.",
    )
    assinaturas_ok: Optional[bool] = Field(
        None,
        description="True somente se AMBAS as partes (VTEX e Fornecedor) assinaram. False se qualquer campo estiver em branco.",
    )
    signatario_vtex: Optional[str] = Field(
        None, description="Nome do signatário do lado da VTEX identificado no bloco de assinaturas.",
    )
    tem_poderes_procuracao: Optional[str] = Field(
        None,
        description=(
            "Se o signatário VTEX possui poderes de procuração nos documentos analisados. "
            "Valores: 'sim' | 'nao' | 'nao_verificavel'"
        ),
    )
    pontos_atencao: Optional[list[str]] = Field(
        None,
        description=(
            "Lista de pontos de atenção identificados. Ex: campo de assinatura em branco, "
            "MPA ausente para comissão, signatário sem procuração verificável, risco PJ."
        ),
    )


# ==============================================================================
# UTILITÁRIOS DE PDF
# ==============================================================================

def extract_text_from_pdf(file_path: str) -> str:
    texts: list[str] = []
    try:
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                text = text.encode("cp1252", errors="replace").decode("cp1252")
                if text.strip():
                    texts.append(text)
    except Exception as e:
        print(f"  [AVISO] Falha ao extrair PDF '{file_path}': {e}")
    return "\n\n".join(texts)


def extract_texts_from_pdfs(pdf_paths: list[str]) -> str:
    """Extrai e combina texto de múltiplos PDFs com separador indicando cada documento."""
    all_texts: list[str] = []
    for i, path in enumerate(pdf_paths, 1):
        text = extract_text_from_pdf(path)
        if text:
            filename = os.path.basename(path)
            all_texts.append(f"=== DOCUMENTO {i}: {filename} ===\n{text}")
    return "\n\n".join(all_texts)


# ==============================================================================
# STATE
# ==============================================================================

class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]

    # Inputs
    user_request: str
    pdf_paths: list[str]        # Suporta múltiplos documentos
    contract_text: str

    # Dados extraídos
    contract_data: dict[str, Any]
    missing_fields: list[str]

    # Campos de compliance (persistidos no banco)
    tipo_regularizacao: Optional[str]
    assinaturas_ok: Optional[bool]
    pontos_atencao: Optional[str]           # JSON list serializado
    documentos_identificados: Optional[str] # JSON list serializado
    is_discarded: bool

    # Controle de fluxo
    supplier_status:     Optional[str]   # "active" | "blocked" | "not_found"
    confirmation_status: Optional[str]   # "confirmed" | "edit"
    approval_status:     Optional[str]   # "pending" | "approved" | "rejected"

    # Resultado
    po_id: Optional[str]
    error_message: Optional[str]

    # Rastreabilidade
    criado_por: Optional[str]
    criado_por_email: Optional[str]
    thread_url: Optional[str]


# ==============================================================================
# NODES
# ==============================================================================

def receive_input_and_document(state: AgentState) -> dict[str, Any]:
    print("\n[NODE] receive_input_and_document")
    return {
        "messages": [HumanMessage(content=state["user_request"])],
        "contract_data": {},
        "missing_fields": [],
        "contract_text": state.get("contract_text", ""),
        "supplier_status": None,
        "approval_status": "pending",
        "po_id": None,
        "error_message": None,
        "is_discarded": False,
        "tipo_regularizacao": None,
        "assinaturas_ok": None,
        "pontos_atencao": None,
        "documentos_identificados": None,
    }


SUPPLEMENT_MARKER = "\n\n[Complemento do usuário]\n"


def extract_and_validate_data(state: AgentState) -> dict[str, Any]:
    """
    Extração estruturada via Gemini + classificação de categoria + validação de compliance.
    Suporta múltiplos PDFs e modo follow-up para campos faltantes.
    """
    print("\n[NODE] extract_and_validate_data")

    pdf_paths: list[str] = state.get("pdf_paths") or []
    contract_text: str = state.get("contract_text", "").strip()
    existing: dict[str, Any] = state.get("contract_data") or {}
    missing_before: list[str] = state.get("missing_fields") or []

    # ── Resolução da fonte de texto ───────────────────────────────────────────
    if SUPPLEMENT_MARKER in contract_text:
        source_text = contract_text.split(SUPPLEMENT_MARKER)[-1].strip()
        is_supplement = True
        print(f"  Modo follow-up: '{source_text[:80]}'")
    elif pdf_paths and not contract_text:
        print(f"  Extraindo texto de {len(pdf_paths)} PDF(s)...")
        contract_text = extract_texts_from_pdfs(pdf_paths)
        if not contract_text:
            print("  [AVISO] PDFs sem texto extraível.")
            return {
                "contract_text": "",
                "contract_data": existing,
                "missing_fields": REQUIRED_FIELDS,
                "is_discarded": False,
            }
        source_text = contract_text
        is_supplement = False
    else:
        source_text = contract_text
        is_supplement = False

    if not source_text:
        return {"contract_data": existing, "missing_fields": REQUIRED_FIELDS, "is_discarded": False}

    # ── Prompt ────────────────────────────────────────────────────────────────
    llm = ChatGoogleGenerativeAI(model=MODEL, google_api_key=GEMINI_API_KEY, temperature=0)
    structured_llm = llm.with_structured_output(ContractData)

    SYSTEM_CONTEXT = (
        "Você é um Especialista em Compliance e Extração de Dados de Contratos da VTEX.\n"
        "Analise os documentos e execute TODAS as tarefas abaixo:\n\n"
        "TAREFA 1 — CLASSIFICAÇÃO DE CATEGORIA\n"
        "Classifique em UMA categoria (campo `categoria`):\n"
        "  Vendor/Supplier | Partnership - SIs implementing POC | "
        "Partnership - commission payment | Partnership - Prime | "
        "Partnership - others | Sponsorship | "
        "Legal and Litigation Service Providers/Law Firms\n"
        "Indique a confiança (0-100) em `categoria_confianca`.\n\n"
        "TAREFA 2 — IDENTIFICAÇÃO DE DOCUMENTOS\n"
        "Liste todos os documentos em `documentos_identificados`:\n"
        "  contrato | proposta_comercial | mpa | invoice | nota_fiscal | recibo | boleto | outro\n\n"
        "TAREFA 3 — VALIDAÇÃO DE ASSINATURAS\n"
        "Para contratos e propostas comerciais:\n"
        "  - `assinaturas_ok` = true somente se AMBAS as partes (VTEX e Fornecedor) assinaram.\n"
        "  - `assinaturas_ok` = false se qualquer campo de assinatura estiver em branco.\n"
        "  - Identifique o signatário VTEX em `signatario_vtex`.\n\n"
        "TAREFA 4 — VERIFICAÇÃO DE PROCURAÇÃO VTEX\n"
        "Com base nos documentos, indique em `tem_poderes_procuracao`:\n"
        "  'sim' | 'nao' | 'nao_verificavel'\n\n"
        "TAREFA 5 — PONTOS DE ATENÇÃO\n"
        "Liste em `pontos_atencao` todos os alertas encontrados:\n"
        "  assinaturas em branco, documentos obrigatórios ausentes, risco PJ, etc.\n\n"
        "REGRAS ABSOLUTAS:\n"
        "1. FONTE ÚNICA: Extraia valores APENAS do contrato/proposta principal. "
        "NUNCA de NF, invoice, recibo ou boleto.\n"
        "2. SEM INFERÊNCIAS: Extraia literalmente. Nunca calcule datas ou deduza dados.\n"
        "3. CNPJ: apenas dígitos numéricos.\n"
        "4. Moeda: identifique EXPLICITAMENTE no corpo do contrato.\n"
    )

    if is_supplement:
        campos = ", ".join(f.replace("_", " ") for f in missing_before) if missing_before else "todos os campos"
        prompt = (
            f"{SYSTEM_CONTEXT}\n"
            f"O usuário forneceu dados diretamente:\n\n\"{source_text}\"\n\n"
            f"Extraia especificamente: {campos}. Deixe None para campos não mencionados."
        )
    else:
        prompt = (
            f"{SYSTEM_CONTEXT}\n"
            "Leia os documentos abaixo e extraia todos os dados.\n"
            "Preencha APENAS campos explicitamente presentes. Retorne None para ausentes.\n\n"
            f"DOCUMENTOS:\n{source_text}"
        )

    result: ContractData = structured_llm.invoke(prompt)

    # ── Merge incremental ─────────────────────────────────────────────────────
    newly = {k: v for k, v in result.model_dump().items() if v is not None and v != "" and v != []}
    merged: dict[str, Any] = {**existing, **newly}

    # ── Verificação de descarte ───────────────────────────────────────────────
    docs: list[str] = merged.get("documentos_identificados") or []
    is_discarded = bool(docs) and all(d in DISCARD_DOC_TYPES for d in docs)

    # ── Pontos de atenção adicionais por categoria ────────────────────────────
    pontos: list[str] = list(merged.get("pontos_atencao") or [])
    categoria = merged.get("categoria", "")
    for req_doc in DOCS_REQUIRED_BY_CATEGORY.get(categoria, []):
        has_doc = any("mpa" in d.lower() for d in docs) if "mpa" in req_doc.lower() else False
        if not has_doc:
            warning = f"Documento obrigatório ausente para '{categoria}': {req_doc}"
            if warning not in pontos:
                pontos.append(warning)
    if pontos:
        merged["pontos_atencao"] = pontos

    # ── Validação de campos obrigatórios ──────────────────────────────────────
    missing: list[str] = [] if is_discarded else [f for f in REQUIRED_FIELDS if not merged.get(f)]

    print(f"  Categoria: {merged.get('categoria')} ({merged.get('categoria_confianca')}%)")
    print(f"  Docs: {docs} | Descarte: {is_discarded} | Assinaturas OK: {merged.get('assinaturas_ok')}")
    if missing:
        print(f"  Campos faltantes: {missing}")

    return {
        "contract_text": contract_text,
        "contract_data": merged,
        "missing_fields": missing,
        "is_discarded": is_discarded,
        "tipo_regularizacao": merged.get("categoria"),
        "assinaturas_ok": merged.get("assinaturas_ok"),
        "pontos_atencao": json.dumps(merged.get("pontos_atencao") or [], ensure_ascii=False),
        "documentos_identificados": json.dumps(docs, ensure_ascii=False),
    }


def discard_documents(_state: AgentState) -> dict[str, Any]:
    """Descarta fluxo quando os documentos enviados são apenas NF/invoice/recibo."""
    print("\n[NODE] discard_documents")
    reason = "Documentos enviados são apenas NF/invoice/recibo — não são aceitos como base para PO."
    return {
        "error_message": reason,
        "messages": [AIMessage(content=reason)],
    }


def human_in_the_loop_missing_info(state: AgentState) -> dict[str, Any]:
    print("\n[NODE] human_in_the_loop_missing_info")
    campos_fmt = "\n".join(f"• {f.replace('_', ' ').title()}" for f in state["missing_fields"])
    prompt = (
        f"Não consegui identificar os seguintes dados no contrato:\n{campos_fmt}\n\n"
        "Por favor, responda nesta thread com essas informações para continuar o processo."
    )
    user_response: str = interrupt(prompt)
    return {
        "messages": [AIMessage(content=prompt), HumanMessage(content=user_response)],
        "contract_text": state.get("contract_text", "") + SUPPLEMENT_MARKER + user_response,
    }


def confirm_with_requester(state: AgentState) -> dict[str, Any]:
    """
    Interrompe o fluxo para exibir o Pro-forma ao solicitante.
    Serializa os dados como JSON com type='PROFORMA' para o bot construir o card rico.
    """
    print("\n[NODE] confirm_with_requester")

    data = state["contract_data"]
    valor = float(data.get("valor_total") or 0)
    moeda = data.get("moeda", "BRL")
    valor_fmt = f"{moeda} {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def _f(key: str, default: str = "Não informado") -> str:
        return str(data.get(key) or default)

    # Documentos
    try:
        docs_list: list[str] = json.loads(state.get("documentos_identificados") or "[]")
    except Exception:
        docs_list = []

    docs_validados = [d for d in docs_list if d not in DISCARD_DOC_TYPES]
    docs_faltantes: list[str] = []
    for req_doc in DOCS_REQUIRED_BY_CATEGORY.get(data.get("categoria", ""), []):
        has_doc = any("mpa" in d.lower() for d in docs_list) if "mpa" in req_doc.lower() else False
        if not has_doc:
            docs_faltantes.append(req_doc)

    # Pontos de atenção
    try:
        pontos: list[str] = json.loads(state.get("pontos_atencao") or "[]")
    except Exception:
        pontos = []

    proforma = {
        "type": "PROFORMA",
        "categoria": data.get("categoria") or "Não classificado",
        "categoria_confianca": data.get("categoria_confianca") or 0,
        "dados": {
            "Fornecedor": _f("razao_social"),
            "CNPJ": _f("cnpj"),
            "País": _f("fornecedor_pais"),
            "Contratante (VTEX)": _f("contratante_nome"),
            "Moeda": _f("moeda"),
            "Valor Total": valor_fmt,
            "Início": _f("data_inicio"),
            "Término": _f("data_termino"),
            "Pagamento": _f("condicao_pagamento"),
            "Frequência": _f("frequencia_pagamento"),
            "Escopo": _f("escopo"),
        },
        "assinaturas_ok": data.get("assinaturas_ok"),
        "signatario_vtex": data.get("signatario_vtex"),
        "tem_poderes_procuracao": data.get("tem_poderes_procuracao"),
        "documentos_validados": docs_validados,
        "documentos_faltantes": docs_faltantes,
        "pontos_atencao": pontos,
        "alerta_pj": data.get("alerta_pj"),
    }

    decision: str = interrupt(json.dumps(proforma, ensure_ascii=False))

    if decision.strip().lower() == "confirmed":
        print("  Dados confirmados pelo solicitante.")
        return {"confirmation_status": "confirmed"}

    edit_text = decision.removeprefix("edit:").strip()
    print(f"  Solicitante pediu alteração: {edit_text}")
    return {
        "confirmation_status": "edit",
        "contract_text": state.get("contract_text", "") + SUPPLEMENT_MARKER + edit_text,
        "missing_fields": [],
    }


def check_supplier(state: AgentState) -> dict[str, Any]:
    print("\n[NODE] check_supplier")
    cnpj = state["contract_data"].get("cnpj", "")
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute("SELECT status FROM suppliers WHERE cnpj = ?", (cnpj,)).fetchone()
    supplier_status = row[0] if row else "not_found"
    print(f"  CNPJ {cnpj} → {supplier_status}")
    return {"supplier_status": supplier_status}


def manager_approval(state: AgentState) -> dict[str, Any]:
    print("\n[NODE] manager_approval")
    data = state["contract_data"]
    valor = float(data.get("valor_total") or 0)
    moeda = data.get("moeda", "BRL")
    valor_fmt = f"{moeda} {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def _f(key: str, default: str = "Não informado") -> str:
        return str(data.get(key) or default)

    try:
        pontos: list[str] = json.loads(state.get("pontos_atencao") or "[]")
    except Exception:
        pontos = []

    summary = (
        "=== SOLICITACAO DE APROVACAO DE PO ===\n"
        f"  Categoria    : {state.get('tipo_regularizacao', 'N/A')}\n"
        f"  Fornecedor   : {_f('razao_social')}\n"
        f"  CNPJ         : {_f('cnpj')}\n"
        f"  Pais         : {_f('fornecedor_pais')}\n"
        f"  Moeda        : {_f('moeda')}\n"
        f"  Valor Total  : {valor_fmt}\n"
        f"  Vigencia     : {_f('data_inicio')} ate {_f('data_termino')}\n"
        f"  Pagamento    : {_f('condicao_pagamento')} / {_f('frequencia_pagamento')}\n"
        f"  Escopo       : {_f('escopo')}\n"
        f"  Assinaturas  : {_f('assinaturas')} (OK: {state.get('assinaturas_ok')})\n"
        + (f"  [ALERTA PJ] {data['alerta_pj']}\n" if data.get("alerta_pj") else "")
        + ("  Pontos de Atencao:\n" + "\n".join(f"    - {p}" for p in pontos) + "\n" if pontos else "")
        + "======================================\n"
        "APROVACAO"
    )
    decision: str = interrupt(summary)
    approval_status = "approved" if decision.strip().lower() == "approved" else "rejected"
    print(f"  Decisão: {approval_status}")
    return {
        "approval_status": approval_status,
        "messages": [AIMessage(content=summary), HumanMessage(content=decision)],
    }


def create_po(state: AgentState) -> dict[str, Any]:
    print("\n[NODE] create_po")
    data = state["contract_data"]
    pdf_paths = state.get("pdf_paths") or []
    pdf_filename = ",".join(os.path.basename(p) for p in pdf_paths) if pdf_paths else ""

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute(
            """
            INSERT INTO purchase_orders
                (numero_po, fornecedor, cnpj, valor_total, valor_utilizado,
                 condicao_pagamento, status, pdf_url, criado_por, criado_por_email, thread_url,
                 moeda, data_inicio, data_termino, descricao_itens, escopo,
                 contratante_nome, contratante_cnpj, fornecedor_pais, alerta_pj,
                 contato_nome, contato_email, frequencia_pagamento, assinaturas,
                 tipo_regularizacao, assinaturas_ok, pontos_atencao, documentos_identificados)
            VALUES (?, ?, ?, ?, 0, ?, 'Pendente validação', ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "PO-TMP",
                data.get("razao_social"),
                data.get("cnpj"),
                data.get("valor_total") or 0,
                data.get("condicao_pagamento"),
                pdf_filename or None,
                state.get("criado_por"),
                state.get("criado_por_email"),
                state.get("thread_url"),
                data.get("moeda"),
                data.get("data_inicio"),
                data.get("data_termino"),
                data.get("descricao_itens"),
                data.get("escopo"),
                data.get("contratante_nome"),
                data.get("contratante_cnpj"),
                data.get("fornecedor_pais"),
                data.get("alerta_pj"),
                data.get("contato_nome"),
                data.get("contato_email"),
                data.get("frequencia_pagamento"),
                data.get("assinaturas"),
                state.get("tipo_regularizacao"),
                1 if state.get("assinaturas_ok") else 0,
                state.get("pontos_atencao"),
                state.get("documentos_identificados"),
            ),
        )
        row_id = cursor.lastrowid
        po_id = f"PO-{row_id:06d}"
        conn.execute("UPDATE purchase_orders SET numero_po = ? WHERE id = ?", (po_id, row_id))

    confirmation = (
        f"Purchase Order criada com sucesso!\n"
        f"  ID       : {po_id}\n"
        f"  Categoria: {state.get('tipo_regularizacao', 'N/A')}\n"
        f"  CNPJ     : {data.get('cnpj')}\n"
        f"  Valor    : {data.get('moeda', 'BRL')} {float(data.get('valor_total') or 0):,.2f}"
    )
    print(f"  {confirmation}")
    return {"po_id": po_id, "messages": [AIMessage(content=confirmation)]}


def procurement_fallback(state: AgentState) -> dict[str, Any]:
    print("\n[NODE] procurement_fallback")
    if state.get("supplier_status") == "blocked":
        reason = f"Fornecedor CNPJ {state['contract_data'].get('cnpj')} está bloqueado. Caso encaminhado ao Compliance."
    else:
        reason = f"Solicitação rejeitada pelo gerente (status: {state.get('approval_status', 'desconhecido')})."
    message = f"Fluxo encerrado — caso encaminhado para análise humana.\nMotivo: {reason}"
    return {"error_message": reason, "messages": [AIMessage(content=message)]}


# ==============================================================================
# ROUTING
# ==============================================================================

def route_after_extraction(
    state: AgentState,
) -> Literal["discard_documents", "human_in_the_loop_missing_info", "check_supplier"]:
    if state.get("is_discarded"):
        return "discard_documents"
    if state["missing_fields"]:
        return "human_in_the_loop_missing_info"
    return "check_supplier"


def route_after_supplier_check(
    state: AgentState,
) -> Literal["confirm_with_requester", "procurement_fallback"]:
    if state.get("supplier_status") == "blocked":
        return "procurement_fallback"
    return "confirm_with_requester"


def route_after_confirmation(
    state: AgentState,
) -> Literal["manager_approval", "extract_and_validate_data"]:
    if state.get("confirmation_status") == "confirmed":
        return "manager_approval"
    return "extract_and_validate_data"


def route_after_approval(
    state: AgentState,
) -> Literal["create_po", "procurement_fallback"]:
    if state.get("approval_status") == "approved":
        return "create_po"
    return "procurement_fallback"


# ==============================================================================
# GRAPH ASSEMBLY
# ==============================================================================

def build_graph():
    """
    Fluxo:
        START → receive_input_and_document
              → extract_and_validate_data ←──────────────────────────────────┐
                    ├─(descarte)──→ discard_documents → END                  │
                    ├─(faltando)──→ human_in_the_loop_missing_info ──────────┘
                    └─(completo)──→ check_supplier
                                        ├─(blocked)→ procurement_fallback → END
                                        └─(ok)─────→ confirm_with_requester (pro-forma)
                                                          ├─(confirmed)→ manager_approval
                                                          │                ├─(approved)→ create_po → END
                                                          │                └─(rejected)→ procurement_fallback → END
                                                          └─(edit)──────→ extract_and_validate_data
    """
    builder = StateGraph(AgentState)

    builder.add_node("receive_input_and_document", receive_input_and_document)
    builder.add_node("extract_and_validate_data", extract_and_validate_data)
    builder.add_node("human_in_the_loop_missing_info", human_in_the_loop_missing_info)
    builder.add_node("discard_documents", discard_documents)
    builder.add_node("check_supplier", check_supplier)
    builder.add_node("confirm_with_requester", confirm_with_requester)
    builder.add_node("manager_approval", manager_approval)
    builder.add_node("create_po", create_po)
    builder.add_node("procurement_fallback", procurement_fallback)

    builder.add_edge(START, "receive_input_and_document")
    builder.add_edge("receive_input_and_document", "extract_and_validate_data")
    builder.add_edge("human_in_the_loop_missing_info", "extract_and_validate_data")
    builder.add_edge("discard_documents", END)
    builder.add_edge("create_po", END)
    builder.add_edge("procurement_fallback", END)

    builder.add_conditional_edges(
        "extract_and_validate_data",
        route_after_extraction,
        {
            "discard_documents": "discard_documents",
            "human_in_the_loop_missing_info": "human_in_the_loop_missing_info",
            "check_supplier": "check_supplier",
        },
    )
    builder.add_conditional_edges(
        "check_supplier",
        route_after_supplier_check,
        {"confirm_with_requester": "confirm_with_requester", "procurement_fallback": "procurement_fallback"},
    )
    builder.add_conditional_edges(
        "confirm_with_requester",
        route_after_confirmation,
        {"manager_approval": "manager_approval", "extract_and_validate_data": "extract_and_validate_data"},
    )
    builder.add_conditional_edges(
        "manager_approval",
        route_after_approval,
        {"create_po": "create_po", "procurement_fallback": "procurement_fallback"},
    )

    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "langgraph.db")
    conn = sqlite3.connect(db_path, check_same_thread=False)
    checkpointer = SqliteSaver(conn)
    return builder.compile(checkpointer=checkpointer)


# ==============================================================================
# ENTRY POINT — terminal interativo
# ==============================================================================

def run_interactive() -> None:
    from langgraph.types import Command
    graph = build_graph()
    print("\n" + "=" * 60)
    print(" SISTEMA DE PROCUREMENT — Regularização e Parcerias VTEX")
    print("=" * 60)
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    user_request = input("\nDescreva sua solicitação:\n> ").strip()
    contract_text = input("\nCole o texto do contrato (Enter para pular):\n> ").strip()
    initial_state: AgentState = {
        "messages": [],
        "user_request": user_request,
        "pdf_paths": [],
        "contract_text": contract_text or user_request,
        "contract_data": {},
        "missing_fields": [],
        "supplier_status": None,
        "confirmation_status": None,
        "approval_status": None,
        "po_id": None,
        "error_message": None,
        "is_discarded": False,
        "tipo_regularizacao": None,
        "assinaturas_ok": None,
        "pontos_atencao": None,
        "documentos_identificados": None,
    }
    graph.invoke(initial_state, config=config)
    while True:
        state = graph.get_state(config)
        if not state.next:
            break
        interrupts = list(state.interrupts) if state.interrupts else []
        if not interrupts and state.tasks:
            interrupts = list(state.tasks[0].interrupts)
        if not interrupts:
            break
        print(f"\n{'─' * 60}\n[AGUARDANDO INPUT]\n{interrupts[0].value}")
        user_input = input("\n> ").strip()
        graph.invoke(Command(resume=user_input), config=config)
    final = graph.get_state(config).values
    print("\n" + "=" * 60)
    if final.get("po_id"):
        print(f"CONCLUÍDO — PO: {final['po_id']}")
    else:
        print(f"ENCERRADO — {final.get('error_message', 'Fluxo finalizado.')}")
    print("=" * 60)


if __name__ == "__main__":
    run_interactive()
