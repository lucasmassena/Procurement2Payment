"""
Frontend Streamlit — MVP de Procurement
"""

from __future__ import annotations

import io
import sys
import uuid

# Força UTF-8 em stdout/stderr para evitar erros de encoding no Windows (CP1252)
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import pypdf
import streamlit as st
from langgraph.types import Command

from procurement_graph import AgentState, build_graph

# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURAÇÃO DA PÁGINA
# ══════════════════════════════════════════════════════════════════════════════

st.set_page_config(
    page_title="Procurement MVP",
    page_icon="🏢",
    layout="centered",
)

# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_resource
def get_graph():
    """
    O grafo é instanciado uma única vez e reutilizado em todos os reruns.
    O MemorySaver interno persiste o estado entre os interrupt() por thread_id.
    """
    return build_graph()


def extract_pdf_text(pdf_bytes: bytes) -> str:
    """
    Extrai texto de todas as paginas do PDF.
    Substitui caracteres fora do CP1252 (ex: setas, box-drawing) por '?'
    para evitar erros de encoding no Windows, preservando caracteres do
    portugues (a, c, e, etc.) que estao dentro do CP1252.
    """
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    pages = []
    for page in reader.pages:
        text = page.extract_text() or ""
        # Sanitiza: encode CP1252 substituindo o que nao couber, depois decodifica
        text = text.encode("cp1252", errors="replace").decode("cp1252")
        pages.append(text)
    return "\n\n".join(p for p in pages if p.strip())


def advance_graph(payload) -> None:
    """
    Chama graph.invoke() e atualiza st.session_state.stage de acordo com
    o resultado: interrupt de dados faltantes, interrupt de aprovação ou fim.
    """
    graph = get_graph()
    config = st.session_state.config

    try:
        graph.invoke(payload, config=config)
    except Exception as e:
        st.session_state.stage = "error"
        st.session_state.error_msg = str(e)
        return

    graph_state = graph.get_state(config)

    if not graph_state.next:
        st.session_state.stage = "done"
        st.session_state.final_values = graph_state.values
        return

    interrupts = graph_state.tasks[0].interrupts if graph_state.tasks else []
    if interrupts:
        prompt = interrupts[0].value
        st.session_state.interrupt_prompt = prompt
        # Detecta tipo de interrupt pelo conteúdo da mensagem
        if "APROVAÇÃO" in prompt.upper():
            st.session_state.stage = "manager_approval"
        else:
            st.session_state.stage = "missing_info"


def reset() -> None:
    """Limpa o session_state para reiniciar o fluxo."""
    for key in list(st.session_state.keys()):
        del st.session_state[key]


# ══════════════════════════════════════════════════════════════════════════════
# SESSION STATE — valores padrão
# ══════════════════════════════════════════════════════════════════════════════

DEFAULTS: dict = {
    "stage": "form",
    "config": None,
    "interrupt_prompt": "",
    "final_values": {},
    "error_msg": "",
}

for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR — barra de progresso
# ══════════════════════════════════════════════════════════════════════════════

STEPS = [
    "Recebimento da Solicitação",
    "Extração de Dados (IA)",
    "Verificação do Fornecedor",
    "Aprovação do Gerente",
    "PO Gerada",
]

STAGE_STEP: dict[str, int] = {
    "form": 0,
    "missing_info": 1,
    "manager_approval": 3,
    "done": 4,
    "error": 0,
}

current_step = STAGE_STEP.get(st.session_state.stage, 0)

with st.sidebar:
    st.header("Progresso")
    st.divider()
    icons = ["📥", "🔍", "🏢", "👔", "📄"]
    for i, (icon, label) in enumerate(zip(icons, STEPS)):
        if i < current_step:
            st.markdown(f"✅ &nbsp; ~~{label}~~", unsafe_allow_html=True)
        elif i == current_step:
            st.markdown(f"**{icon} &nbsp; {label}**")
        else:
            st.markdown(f"<span style='color:#888'>⬜ &nbsp; {label}</span>", unsafe_allow_html=True)

    st.divider()
    if st.session_state.stage != "form":
        if st.button("↩ Reiniciar", use_container_width=True):
            reset()
            st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# HEADER
# ══════════════════════════════════════════════════════════════════════════════

st.title("🏢 Sistema de Procurement")
st.caption("MVP de automação de Purchase Requisition com Gemini + LangGraph")
st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# STAGE: form — formulário inicial
# ══════════════════════════════════════════════════════════════════════════════

if st.session_state.stage == "form":
    st.subheader("Nova Solicitação de Compra")

    with st.form("procurement_form"):
        user_request = st.text_area(
            "Descreva sua solicitação",
            placeholder=(
                "Ex: Preciso contratar a empresa Fornecedor XYZ Ltda "
                "para fornecimento de licenças de software..."
            ),
            height=110,
        )

        pdf_file = st.file_uploader(
            "Contrato (PDF) *",
            type=["pdf"],
            help=(
                "O texto será extraído automaticamente pelo sistema. "
                "PDFs baseados apenas em imagem (escaneados) podem não funcionar."
            ),
        )

        submitted = st.form_submit_button(
            "📤 Enviar Solicitação",
            use_container_width=True,
            type="primary",
        )

    if submitted:
        errors = []
        if not user_request.strip():
            errors.append("Descreva sua solicitação antes de enviar.")
        if not pdf_file:
            errors.append("Anexe o contrato em PDF antes de enviar.")

        if errors:
            for msg in errors:
                st.error(msg)
            st.stop()

        with st.spinner("Lendo o PDF..."):
            contract_text = extract_pdf_text(pdf_file.read())

        if not contract_text.strip():
            st.error(
                "Não foi possível extrair texto do PDF. "
                "O arquivo pode ser baseado em imagens. "
                "Use um PDF com texto selecionável."
            )
            st.stop()

        st.session_state.config = {
            "configurable": {"thread_id": str(uuid.uuid4())}
        }

        initial_state: AgentState = {
            "messages": [],
            "user_request": user_request.strip(),
            "contract_text": contract_text,
            "contract_data": {},
            "missing_fields": [],
            "supplier_status": None,
            "approval_status": None,
            "po_id": None,
            "error_message": None,
        }

        with st.spinner("Analisando o contrato com Gemini..."):
            advance_graph(initial_state)

        st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# STAGE: missing_info — dados faltantes
# ══════════════════════════════════════════════════════════════════════════════

elif st.session_state.stage == "missing_info":
    st.subheader("⚠️ Informações Faltantes no Contrato")

    st.info(st.session_state.interrupt_prompt)

    st.markdown(
        "Forneça os dados no formato mais natural possível. "
        "Exemplos: `CNPJ: 12.345.678/0001-99` ou `Valor: R$ 80.000`"
    )

    with st.form("missing_info_form"):
        user_input = st.text_area(
            "Sua resposta",
            placeholder='CNPJ: 12345678000199 | Valor Total: 80000 | Pagamento: 30/60 dias',
            height=100,
        )
        col1, col2 = st.columns([4, 1])
        with col1:
            confirmed = st.form_submit_button(
                "✅ Confirmar e Continuar",
                use_container_width=True,
                type="primary",
            )
        with col2:
            cancelled = st.form_submit_button("✖ Cancelar", use_container_width=True)

    if cancelled:
        reset()
        st.rerun()

    if confirmed:
        if not user_input.strip():
            st.error("Forneça as informações antes de continuar.")
            st.stop()
        with st.spinner("Reprocessando com os dados fornecidos..."):
            advance_graph(Command(resume=user_input.strip()))
        st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# STAGE: manager_approval — aprovação do gerente
# ══════════════════════════════════════════════════════════════════════════════

elif st.session_state.stage == "manager_approval":
    st.subheader("👔 Aprovação do Gerente")
    st.warning("A solicitação abaixo aguarda aprovação.")

    # Extrai só o bloco do sumário (entre ╔ e ╝) para exibir formatado
    prompt_lines = st.session_state.interrupt_prompt.strip().split("\n")
    card_lines = [
        line for line in prompt_lines
        if line.strip() and "Digite" not in line and "Responda" not in line
    ]

    st.code("\n".join(card_lines), language=None)
    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        if st.button("✅ Aprovar", use_container_width=True, type="primary"):
            with st.spinner("Registrando aprovação e criando a PO..."):
                advance_graph(Command(resume="approved"))
            st.rerun()
    with col2:
        if st.button("❌ Rejeitar", use_container_width=True):
            with st.spinner("Registrando rejeição..."):
                advance_graph(Command(resume="rejected"))
            st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# STAGE: done — resultado final
# ══════════════════════════════════════════════════════════════════════════════

elif st.session_state.stage == "done":
    final = st.session_state.final_values
    data = final.get("contract_data", {})

    if final.get("po_id"):
        st.balloons()
        st.success("### ✅ Purchase Order Criada com Sucesso!")
        st.divider()

        col1, col2 = st.columns(2)
        with col1:
            st.metric("ID da PO", final["po_id"])
            st.metric("Razão Social", data.get("company_name", "—"))
            st.metric("CNPJ", data.get("cnpj", "—"))
        with col2:
            valor = float(data.get("total_value") or 0)
            valor_fmt = f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            st.metric("Valor Total", valor_fmt)
            st.metric("Condição de Pagamento", data.get("payment_condition", "—"))
    else:
        st.error("### ❌ Solicitação Encerrada sem Aprovação")
        st.write(final.get("error_message", "O fluxo foi finalizado sem aprovação."))

    st.divider()
    if st.button("🔄 Nova Solicitação", use_container_width=True):
        reset()
        st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# STAGE: error — erro inesperado
# ══════════════════════════════════════════════════════════════════════════════

elif st.session_state.stage == "error":
    st.error("### ⚠️ Erro Inesperado")
    st.code(st.session_state.error_msg)

    if st.button("🔄 Tentar Novamente", use_container_width=True):
        reset()
        st.rerun()
