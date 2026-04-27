"""
MVP — Automação de Procurement (Purchase Requisition)
======================================================
Stack : LangGraph + Gemini 2.0 Flash (structured output) + SQLite + MemorySaver
"""

from __future__ import annotations

import io
import os
import sqlite3
import sys
import uuid
from typing import Annotated, Any, Literal, Optional

# Forca UTF-8 em stdout/stderr apenas quando rodando em terminal Windows (CP1252)
if sys.stdout.isatty() and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.isatty() and hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import pdfplumber
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
import sqlite3
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import interrupt
from pydantic import BaseModel, Field
from typing_extensions import TypedDict


# ==============================================================================
# CONFIGURAÇÃO
# ==============================================================================

# Em produção mova para variável de ambiente / .env
GEMINI_API_KEY = "GEMINI_KEY_REMOVED"
MODEL = "gemini-2.5-flash"

DB_PATH = os.path.join(os.path.dirname(__file__), "procurement.db")

REQUIRED_FIELDS: list[str] = [
    "razao_social",
    "cnpj",
    "moeda",
    "valor_total",
    "condicao_pagamento",
]


# ==============================================================================
# SCHEMA DE EXTRAÇÃO (Pydantic — usado com .with_structured_output())
# ==============================================================================

class ContractData(BaseModel):
    """
    Schema de extração estruturada do contrato de fornecimento.
    Todos os campos são Optional: o modelo preenche apenas o que encontrar
    explicitamente no texto. Se não encontrar, retorna None.
    """

    # ── Identificação do Fornecedor ─────────────────────────────────────────
    razao_social: Optional[str] = Field(
        None,
        description=(
            "Razão Social ou nome completo do FORNECEDOR/CONTRATADO — "
            "conforme consta no preâmbulo do contrato. "
            "Pode ser pessoa física ou jurídica."
        ),
    )
    cnpj: Optional[str] = Field(
        None,
        description=(
            "CNPJ ou CPF do fornecedor — apenas dígitos numéricos, sem pontos/traços/barras."
        ),
    )
    fornecedor_pais: Optional[str] = Field(
        None,
        description="País de origem do fornecedor, conforme consta no contrato.",
    )
    alerta_pj: Optional[str] = Field(
        None,
        description=(
            "Se a primeira palavra da Razão Social for um nome próprio humano "
            "(ex: 'Victor', 'Maria', 'João'), preencha com 'ALERTA: possível risco PJ/Contractor — "
            "fornecedor com nome de pessoa física'. Caso contrário, deixe vazio (None)."
        ),
    )

    # ── Contratante (VTEX) ───────────────────────────────────────────────────
    contratante_nome: Optional[str] = Field(
        None,
        description=(
            "Nome exato da entidade VTEX identificada como CONTRATANTE ou COMPRADORA "
            "no preâmbulo da primeira página."
        ),
    )
    contratante_cnpj: Optional[str] = Field(
        None,
        description="CNPJ/Tax ID da entidade VTEX contratante — apenas dígitos numéricos.",
    )

    # ── Valores e Moeda ──────────────────────────────────────────────────────
    moeda: Optional[str] = Field(
        None,
        description=(
            "Moeda EXPLICITAMENTE citada no corpo principal do contrato "
            "(ex: 'BRL', 'USD', 'EUR'). Proibido inferir pelo país."
        ),
    )
    valor_total: Optional[float] = Field(
        None,
        description=(
            "Valor total do contrato — número decimal sem símbolo de moeda. "
            "Converta abreviações: '90 mil' = 90000.0, '1,5 milhão' = 1500000.0."
        ),
    )
    descricao_itens: Optional[str] = Field(
        None,
        description=(
            "Descrição dos itens/serviços negociados com valores e quantidades. "
            "Indique se há menção explícita de inclusão ou exclusão de impostos."
        ),
    )

    # ── Datas e Vigência ─────────────────────────────────────────────────────
    data_inicio: Optional[str] = Field(
        None,
        description=(
            "Data de início do serviço exatamente como escrita no contrato. "
            "Se for 'data da assinatura', escreva isso. NÃO calcule nem infira."
        ),
    )
    data_termino: Optional[str] = Field(
        None,
        description=(
            "Data de término ou prazo de vigência exatamente como escrito. "
            "Se disser '12 meses', extraia '12 meses a partir do início'. NÃO calcule a data exata."
        ),
    )

    # ── Escopo ───────────────────────────────────────────────────────────────
    escopo: Optional[str] = Field(
        None,
        description="Escopo ou objeto do contrato — resumo claro e objetivo do que está sendo contratado.",
    )

    # ── Pagamento ────────────────────────────────────────────────────────────
    condicao_pagamento: Optional[str] = Field(
        None,
        description="Condição/prazo de pagamento (ex: '30 dias após fatura', 'a vista', '30/60/90 dias').",
    )
    frequencia_pagamento: Optional[str] = Field(
        None,
        description="Frequência de faturamento/pagamento (ex: mensal, anual, trimestral, parcela única).",
    )

    # ── Contato ──────────────────────────────────────────────────────────────
    contato_nome: Optional[str] = Field(
        None,
        description="Nome do contato/representante do fornecedor, se disponível no contrato.",
    )
    contato_email: Optional[str] = Field(
        None,
        description="E-mail do contato do fornecedor, se disponível.",
    )

    # ── Assinaturas ──────────────────────────────────────────────────────────
    assinaturas: Optional[str] = Field(
        None,
        description=(
            "Status das assinaturas no bloco final do contrato. "
            "Indique explicitamente: quem assinou (Contratante e/ou Fornecedor) "
            "e se há campos em branco para alguma das partes."
        ),
    )


# ==============================================================================
# UTILITÁRIO DE LEITURA DE PDF
# ==============================================================================

def extract_text_from_pdf(file_path: str) -> str:
    """
    Extrai o texto de todas as páginas de um PDF usando pdfplumber.

    pdfplumber lida melhor que pypdf com layouts complexos (tabelas, multi-coluna),
    sendo mais adequado para contratos comerciais.

    Args:
        file_path: Caminho local do arquivo PDF (ex: /tmp/contrato_slack.pdf).

    Returns:
        Texto concatenado de todas as páginas, ou string vazia se falhar.
    """
    texts: list[str] = []
    try:
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                # Sanitiza chars fora do CP1252 para evitar erros de encoding no Windows
                text = text.encode("cp1252", errors="replace").decode("cp1252")
                if text.strip():
                    texts.append(text)
    except Exception as e:
        print(f"  [AVISO] Falha ao extrair PDF '{file_path}': {e}")
    return "\n\n".join(texts)


# ==============================================================================
# STATE
# ==============================================================================

class AgentState(TypedDict):
    """Estado compartilhado entre todos os nós do grafo."""

    messages: Annotated[list[BaseMessage], add_messages]

    # Inputs
    user_request: str          # Mensagem do usuário no Slack / terminal
    pdf_path: Optional[str]    # Caminho local do PDF baixado do Slack (None se texto direto)
    contract_text: str         # Texto bruto extraído do PDF ou fornecido diretamente

    # Dados extraídos e validados
    contract_data: dict[str, Any]   # Campos do ContractData já extraídos (acumulados)
    missing_fields: list[str]       # Campos obrigatórios ainda ausentes

    # Controle de fluxo
    supplier_status:    Optional[str]   # "active" | "blocked" | "not_found"
    confirmation_status: Optional[str] # "confirmed" | "edit" | None
    approval_status:    Optional[str]   # "pending" | "approved" | "rejected"

    # Resultado
    po_id: Optional[str]
    error_message: Optional[str]

    # Rastreabilidade
    criado_por: Optional[str]        # Nome do solicitante no Slack
    criado_por_email: Optional[str]  # Email do solicitante no Slack
    thread_url: Optional[str]        # Link da thread do Slack onde a PO foi criada


# ==============================================================================
# NODES
# ==============================================================================

def receive_input_and_document(state: AgentState) -> dict[str, Any]:
    """
    Nó 1 — Ponto de entrada.
    Registra a solicitação e inicializa todos os campos de controle.
    """
    print("\n[NODE] receive_input_and_document")
    print(f"  Solicitação: {state['user_request'][:80]}...")

    return {
        "messages": [HumanMessage(content=state["user_request"])],
        "contract_data": {},
        "missing_fields": [],
        "contract_text": state.get("contract_text", ""),
        "supplier_status": None,
        "approval_status": "pending",
        "po_id": None,
        "error_message": None,
    }


SUPPLEMENT_MARKER = "\n\n[Complemento do usuário]\n"


def extract_and_validate_data(state: AgentState) -> dict[str, Any]:
    """
    Nó 2 — Extração estruturada via Gemini + validação dos campos obrigatórios.

    Dois modos de operação:
    - Primeira extração: processa o texto completo do PDF.
    - Follow-up (após resposta do usuário no Slack): extrai apenas os campos
      faltantes a partir da resposta do usuário, preservando o que já foi extraído.
    """
    print("\n[NODE] extract_and_validate_data")

    pdf_path: Optional[str] = state.get("pdf_path")
    contract_text: str = state.get("contract_text", "").strip()
    existing: dict[str, Any] = state.get("contract_data") or {}
    missing_before: list[str] = state.get("missing_fields") or []

    # ── 1. Resolução da fonte de texto e modo de extração ─────────────────────
    if SUPPLEMENT_MARKER in contract_text:
        # Follow-up: o usuário respondeu com os dados faltantes.
        # Extrai apenas da parte nova (resposta do usuário), preservando dados já coletados.
        source_text = contract_text.split(SUPPLEMENT_MARKER)[-1].strip()
        is_supplement = True
        print(f"  Modo follow-up. Extraindo da resposta do usuário: '{source_text[:80]}'")
    elif pdf_path and not contract_text:
        print(f"  Extraindo texto do PDF: {pdf_path}")
        contract_text = extract_text_from_pdf(pdf_path)
        if not contract_text:
            print("  [AVISO] PDF sem texto extraivel.")
            return {
                "contract_text": "",
                "contract_data": existing,
                "missing_fields": REQUIRED_FIELDS,
            }
        source_text = contract_text
        is_supplement = False
    else:
        source_text = contract_text
        is_supplement = False

    if not source_text:
        print("  [AVISO] Nenhum texto disponivel para extração.")
        return {
            "contract_data": existing,
            "missing_fields": REQUIRED_FIELDS,
        }

    # ── 2. Prompt adaptado ao modo ────────────────────────────────────────────
    llm = ChatGoogleGenerativeAI(model=MODEL, google_api_key=GEMINI_API_KEY, temperature=0)
    structured_llm = llm.with_structured_output(ContractData)

    SYSTEM_CONTEXT = (
        "Você é um Especialista em Extração de Dados de Contratos de Procurement da VTEX. "
        "Sua função é analisar detalhadamente o documento e extrair as informações chave com precisão absoluta.\n\n"
        "REGRAS ABSOLUTAS:\n"
        "1. FONTE ÚNICA DA VERDADE: O contrato/proposta principal é SEMPRE sua única fonte. "
        "É TERMINANTEMENTE PROIBIDO extrair valores de arquivos secundários (NF, invoice, boleto, recibo). "
        "Se uma informação não estiver explícita, retorne None.\n"
        "2. TOLERÂNCIA ZERO PARA INFERÊNCIAS: Proibido deduzir dados, calcular prazos ou assumir premissas. "
        "A extração deve ser LITERAL (exatamente como está escrito).\n"
        "3. CNPJ: apenas dígitos numéricos, sem pontos/traços/barras.\n"
        "4. valor_total: número decimal sem símbolo de moeda. Converta abreviações ('90 mil'=90000.0).\n"
        "5. Moeda: identifique EXPLICITAMENTE no corpo do contrato. Proibido inferir pelo país.\n"
        "6. Datas: extraia LITERALMENTE como escrito. NÃO calcule datas.\n"
        "7. Assinaturas: verifique o bloco final — informe quem assinou e se há campos em branco.\n"
        "8. Alerta PJ: se a primeira palavra do nome do fornecedor for nome próprio humano, gere o alerta.\n"
        "9. Contratante (VTEX): olhe EXCLUSIVAMENTE o preâmbulo da primeira página.\n"
    )

    if is_supplement:
        if missing_before:
            campos = ", ".join(f.replace("_", " ") for f in missing_before)
            context = f"Extraia especificamente os campos: {campos}."
        else:
            context = "Extraia todos os campos que o usuário mencionou."
        prompt = (
            f"{SYSTEM_CONTEXT}\n"
            f"O usuário forneceu os seguintes dados diretamente:\n\n"
            f'"{source_text}"\n\n'
            f"{context}\n"
            "Deixe None apenas campos que o usuário não mencionou."
        )
    else:
        prompt = (
            f"{SYSTEM_CONTEXT}\n"
            "Leia o texto abaixo e extraia todos os dados do contrato de fornecimento.\n"
            "Preencha APENAS campos explicitamente presentes no texto. "
            "Retorne None para campos ausentes ou ambíguos.\n\n"
            f"TEXTO DO CONTRATO:\n{source_text}"
        )

    result: ContractData = structured_llm.invoke(prompt)

    # ── 3. Merge incremental — dados anteriores nunca são sobrescritos por None ─
    newly_extracted: dict[str, Any] = {
        k: v for k, v in result.model_dump().items() if v is not None and v != ""
    }
    merged: dict[str, Any] = {**existing, **newly_extracted}

    # ── 4. Validação ──────────────────────────────────────────────────────────
    missing: list[str] = [f for f in REQUIRED_FIELDS if not merged.get(f)]

    if missing:
        print(f"  Campos ainda faltantes: {missing}")
    else:
        print(f"  Extração completa: razao_social={merged.get('razao_social')}, "
              f"cnpj={merged.get('cnpj')}, valor_total={merged.get('valor_total')}")

    return {
        "contract_text": contract_text,
        "contract_data": merged,
        "missing_fields": missing,
    }


def human_in_the_loop_missing_info(state: AgentState) -> dict[str, Any]:
    """
    Nó 3 — Interrupção para coletar informações faltantes do usuário.

    `interrupt()` pausa o grafo. Retoma via Command(resume=<resposta do usuário>).
    A resposta é anexada ao contract_text com SUPPLEMENT_MARKER para que
    extract_and_validate_data saiba que é um follow-up e use extração dirigida.
    """
    print("\n[NODE] human_in_the_loop_missing_info")

    campos_fmt = "\n".join(
        f"• {f.replace('_', ' ').title()}" for f in state["missing_fields"]
    )
    prompt = (
        f"Não consegui identificar os seguintes dados no contrato:\n{campos_fmt}\n\n"
        "Por favor, responda nesta thread com essas informações para continuar o processo."
    )
    print(f"  {prompt}")

    user_response: str = interrupt(prompt)

    return {
        "messages": [
            AIMessage(content=prompt),
            HumanMessage(content=user_response),
        ],
        "contract_text": state.get("contract_text", "") + SUPPLEMENT_MARKER + user_response,
    }


def confirm_with_requester(state: AgentState) -> dict[str, Any]:
    """
    Nó 3.5 — Mostra os dados extraídos ao solicitante para confirmação antes
    de enviar ao gerente. Permite correções via 'edit:<texto>'.
    """
    print("\n[NODE] confirm_with_requester")

    data = state["contract_data"]
    valor = float(data.get("valor_total") or 0)
    valor_fmt = f"{data.get('moeda', 'BRL')} {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def _f(key: str, default: str = "Não informado") -> str:
        return str(data.get(key) or default)

    summary = (
        "=== CONFIRMACAO DOS DADOS ===\n"
        f"  Fornecedor        : {_f('razao_social')}\n"
        f"  CNPJ Fornecedor   : {_f('cnpj')}\n"
        f"  Pais              : {_f('fornecedor_pais')}\n"
        f"  Contratante (VTEX): {_f('contratante_nome')}\n"
        f"  CNPJ Contratante  : {_f('contratante_cnpj')}\n"
        f"  Moeda             : {_f('moeda')}\n"
        f"  Valor Total       : {valor_fmt}\n"
        f"  Inicio            : {_f('data_inicio')}\n"
        f"  Termino           : {_f('data_termino')}\n"
        f"  Cond. Pagamento   : {_f('condicao_pagamento')}\n"
        f"  Frequencia        : {_f('frequencia_pagamento')}\n"
        f"  Escopo            : {_f('escopo')}\n"
        f"  Assinaturas       : {_f('assinaturas')}\n"
        + (f"  [ALERTA PJ] {data['alerta_pj']}\n" if data.get("alerta_pj") else "")
        + "=============================\n"
        "Os dados estao corretos?"
    )
    print(f"  {summary}")

    decision: str = interrupt(summary)

    if decision.strip().lower() == "confirmed":
        print("  Dados confirmados pelo solicitante.")
        return {"confirmation_status": "confirmed"}

    # Usuário quer editar: decision vem como "edit:<texto da correção>"
    edit_text = decision.removeprefix("edit:").strip()
    print(f"  Solicitante pediu alteração: {edit_text}")
    return {
        "confirmation_status": "edit",
        "contract_text": state.get("contract_text", "") + SUPPLEMENT_MARKER + edit_text,
        "missing_fields": [],
    }


def check_supplier(state: AgentState) -> dict[str, Any]:
    """
    Nó 4 — Consulta o cadastro de fornecedores no SQLite pelo CNPJ.
    Retorna: "active" | "blocked" | "not_found".
    """
    print("\n[NODE] check_supplier")

    cnpj = state["contract_data"].get("cnpj", "")
    print(f"  Consultando CNPJ {cnpj}...")

    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT status FROM suppliers WHERE cnpj = ?", (cnpj,)
        ).fetchone()

    supplier_status = row[0] if row else "not_found"
    print(f"  Status: {supplier_status}")

    return {"supplier_status": supplier_status}


def manager_approval(state: AgentState) -> dict[str, Any]:
    """
    Nó 5 — Solicita aprovação do gerente via interrupt().
    Aguarda 'approved' ou qualquer outra resposta (tratada como 'rejected').
    """
    print("\n[NODE] manager_approval")

    data = state["contract_data"]
    valor = float(data.get("valor_total") or 0)
    valor_fmt = f"{data.get('moeda', 'BRL')} {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def _f(key: str, default: str = "Não informado") -> str:
        return str(data.get(key) or default)

    summary = (
        "=== SOLICITACAO DE APROVACAO DE PO ===\n"
        f"  Fornecedor   : {_f('razao_social')}\n"
        f"  CNPJ         : {_f('cnpj')}\n"
        f"  Pais         : {_f('fornecedor_pais')}\n"
        f"  Moeda        : {_f('moeda')}\n"
        f"  Valor Total  : {valor_fmt}\n"
        f"  Vigencia     : {_f('data_inicio')} ate {_f('data_termino')}\n"
        f"  Pagamento    : {_f('condicao_pagamento')} / {_f('frequencia_pagamento')}\n"
        f"  Escopo       : {_f('escopo')}\n"
        f"  Assinaturas  : {_f('assinaturas')}\n"
        + (f"  [ALERTA PJ] {data['alerta_pj']}\n" if data.get("alerta_pj") else "")
        + "======================================\n"
        "Digite 'approved' para aprovar ou qualquer outra coisa para rejeitar."
    )
    print(f"\n{summary}")

    decision: str = interrupt(summary)
    approval_status = "approved" if decision.strip().lower() == "approved" else "rejected"
    print(f"  Decisão: {approval_status}")

    return {
        "approval_status": approval_status,
        "messages": [
            AIMessage(content=summary),
            HumanMessage(content=decision),
        ],
    }


def create_po(state: AgentState) -> dict[str, Any]:
    """
    Nó 6 — Grava a Purchase Order no SQLite e notifica o solicitante.
    """
    print("\n[NODE] create_po")

    data = state["contract_data"]

    pdf_filename = os.path.basename(state.get("pdf_path") or "")

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute(
            """
            INSERT INTO purchase_orders
                (numero_po, fornecedor, cnpj, valor_total, valor_utilizado,
                 condicao_pagamento, status, pdf_url, criado_por, criado_por_email, thread_url,
                 moeda, data_inicio, data_termino, descricao_itens, escopo,
                 contratante_nome, contratante_cnpj, fornecedor_pais, alerta_pj,
                 contato_nome, contato_email, frequencia_pagamento, assinaturas)
            VALUES (?, ?, ?, ?, 0, ?, 'Pendente validação', ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            ),
        )
        row_id = cursor.lastrowid
        po_id = f"PO-{row_id:06d}"
        conn.execute(
            "UPDATE purchase_orders SET numero_po = ? WHERE id = ?",
            (po_id, row_id),
        )

    confirmation = (
        f"Purchase Order criada com sucesso!\n"
        f"  ID    : {po_id}\n"
        f"  CNPJ  : {data['cnpj']}\n"
        f"  Valor : R$ {float(data['valor_total']):,.2f}"
    )
    print(f"  {confirmation}")

    return {
        "po_id": po_id,
        "messages": [AIMessage(content=confirmation)],
    }


def procurement_fallback(state: AgentState) -> dict[str, Any]:
    """
    Nó 7 — Tratativa de rejeição ou bloqueio. Sempre terminal (→ END).
    """
    print("\n[NODE] procurement_fallback")

    if state.get("supplier_status") == "blocked":
        reason = (
            f"Fornecedor com CNPJ {state['contract_data'].get('cnpj')} "
            "está bloqueado no sistema. Caso encaminhado ao time de Compliance."
        )
    else:
        reason = (
            f"Solicitação rejeitada pelo gerente "
            f"(status: {state.get('approval_status', 'desconhecido')})."
        )

    message = f"Fluxo encerrado — caso encaminhado para análise humana.\nMotivo: {reason}"
    print(f"  {message}")

    return {
        "error_message": reason,
        "messages": [AIMessage(content=message)],
    }


# ==============================================================================
# ROUTING (Conditional Edges)
# ==============================================================================

def route_after_extraction(
    state: AgentState,
) -> Literal["human_in_the_loop_missing_info", "check_supplier"]:
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
    Monta e compila o grafo com MemorySaver como checkpointer.

    O MemorySaver persiste o AgentState entre chamadas quando o grafo
    é pausado por interrupt(), permitindo que o fluxo retome exatamente
    de onde parou sem perder nenhum dado já coletado.

    Fluxo:
        START → receive_input_and_document
              → extract_and_validate_data ←────────────────────────┐
                    ├─(faltando)→ human_in_the_loop_missing_info ──┘
                    └─(completo)→ check_supplier
                                    ├─(blocked)→ procurement_fallback → END
                                    └─(ok)─────→ manager_approval
                                                    ├─(rejected)→ procurement_fallback → END
                                                    └─(approved)→ create_po → END
    """
    builder = StateGraph(AgentState)

    # Nodes
    builder.add_node("receive_input_and_document", receive_input_and_document)
    builder.add_node("extract_and_validate_data", extract_and_validate_data)
    builder.add_node("human_in_the_loop_missing_info", human_in_the_loop_missing_info)
    builder.add_node("check_supplier", check_supplier)
    builder.add_node("confirm_with_requester", confirm_with_requester)
    builder.add_node("manager_approval", manager_approval)
    builder.add_node("create_po", create_po)
    builder.add_node("procurement_fallback", procurement_fallback)

    # Edges diretos
    builder.add_edge(START, "receive_input_and_document")
    builder.add_edge("receive_input_and_document", "extract_and_validate_data")
    builder.add_edge("human_in_the_loop_missing_info", "extract_and_validate_data")
    builder.add_edge("create_po", END)
    builder.add_edge("procurement_fallback", END)

    # Conditional edges
    builder.add_conditional_edges(
        "extract_and_validate_data",
        route_after_extraction,
        {
            "human_in_the_loop_missing_info": "human_in_the_loop_missing_info",
            "check_supplier": "check_supplier",
        },
    )
    builder.add_conditional_edges(
        "check_supplier",
        route_after_supplier_check,
        {
            "confirm_with_requester": "confirm_with_requester",
            "procurement_fallback": "procurement_fallback",
        },
    )
    builder.add_conditional_edges(
        "confirm_with_requester",
        route_after_confirmation,
        {
            "manager_approval": "manager_approval",
            "extract_and_validate_data": "extract_and_validate_data",
        },
    )
    builder.add_conditional_edges(
        "manager_approval",
        route_after_approval,
        {
            "create_po": "create_po",
            "procurement_fallback": "procurement_fallback",
        },
    )

    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "langgraph.db")
    conn = sqlite3.connect(db_path, check_same_thread=False)
    checkpointer = SqliteSaver(conn)
    return builder.compile(checkpointer=checkpointer)


# ==============================================================================
# ENTRY POINT — execução interativa no terminal
# ==============================================================================

def run_interactive() -> None:
    """Loop de teste no terminal: submissão → cobrança de dados → aprovação → PO."""
    from langgraph.types import Command

    graph = build_graph()

    print("\n" + "=" * 60)
    print(" SISTEMA DE PROCUREMENT — MVP")
    print("=" * 60)

    config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    user_request = input("\nDescreva sua solicitação de compra:\n> ").strip()
    contract_text = input("\nCole o texto do contrato (Enter para usar só a solicitação):\n> ").strip()

    initial_state: AgentState = {
        "messages": [],
        "user_request": user_request,
        "contract_text": contract_text or user_request,
        "contract_data": {},
        "missing_fields": [],
        "supplier_status": None,
        "confirmation_status": None,
        "approval_status": None,
        "po_id": None,
        "error_message": None,
    }

    graph.invoke(initial_state, config=config)

    # Loop de resume para cada interrupt()
    while True:
        state = graph.get_state(config)
        if not state.next:
            break

        interrupts = state.tasks[0].interrupts if state.tasks else []
        if not interrupts:
            break

        print(f"\n{'─' * 60}")
        print(f"[AGUARDANDO INPUT]\n{interrupts[0].value}")
        user_input = input("\n> ").strip()

        graph.invoke(Command(resume=user_input), config=config)

    # Resultado final
    final = graph.get_state(config).values
    print("\n" + "=" * 60)
    if final.get("po_id"):
        print(f"CONCLUÍDO — PO gerada: {final['po_id']}")
    else:
        print(f"ENCERRADO — {final.get('error_message', 'Fluxo finalizado.')}")
    print("=" * 60)


if __name__ == "__main__":
    run_interactive()
