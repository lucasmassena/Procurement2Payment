"""
Slack Bot — Procurement P2P (fluxo em thread no canal)
=======================================================
Fluxo:
  1. Usuário menciona o bot ou envia PDF no canal
  2. Bot responde na thread do canal
  3. Dados faltantes → bot pede na thread, usuário responde na thread
  4. Confirmação → card com botões na thread (Confirmar / Alterar Dados)
  5. Confirmado → card de aprovação no canal de managers
  6. Manager aprova/rejeita → bot notifica na thread original
"""

from __future__ import annotations

import logging
import os
import re
import sqlite3
import threading
import traceback
from dataclasses import dataclass, field
from typing import Any, Optional

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bot_debug.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("bot")

import requests
from dotenv import load_dotenv
from langgraph.types import Command
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

load_dotenv()

from procurement_graph import AgentState, build_graph

# ==============================================================================
# CONFIGURAÇÃO
# ==============================================================================

SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_APP_TOKEN = os.environ["SLACK_APP_TOKEN"]
MANAGER_CHANNEL = os.environ.get("SLACK_MANAGER_CHANNEL", "#procurement-aprovacoes")

app   = App(token=SLACK_BOT_TOKEN)
graph = build_graph()

# ==============================================================================
# PERSISTÊNCIA DE SESSÕES
# ==============================================================================

_SESSIONS_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sessions.db")


def _init_session_store() -> None:
    with sqlite3.connect(_SESSIONS_DB) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                thread_ts  TEXT PRIMARY KEY,
                channel    TEXT NOT NULL,
                user       TEXT NOT NULL,
                waiting_for TEXT
            )
        """)


def _persist_session(session: "ProcurementSession") -> None:
    with sqlite3.connect(_SESSIONS_DB) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO sessions (thread_ts, channel, user, waiting_for) VALUES (?,?,?,?)",
            (session.thread_ts, session.channel, session.user, session.waiting_for),
        )


def _forget_session(thread_ts: str) -> None:
    with sqlite3.connect(_SESSIONS_DB) as conn:
        conn.execute("DELETE FROM sessions WHERE thread_ts = ?", (thread_ts,))


def _restore_sessions() -> None:
    try:
        with sqlite3.connect(_SESSIONS_DB) as conn:
            rows = conn.execute(
                "SELECT thread_ts, channel, user, waiting_for FROM sessions"
            ).fetchall()
        for thread_ts, channel, user, waiting_for in rows:
            session = ProcurementSession(
                config={"configurable": {"thread_id": f"slack-{channel}-{thread_ts}"}},
                channel=channel,
                thread_ts=thread_ts,
                user=user,
                waiting_for=waiting_for,
            )
            _sessions[thread_ts] = session
        if rows:
            log.info("Sessões restauradas do disco: %d", len(rows))
    except Exception:
        log.warning("Não foi possível restaurar sessões do disco", exc_info=True)


# ==============================================================================
# SESSÃO
# Chave: thread_ts do canal (ts da mensagem original que iniciou o fluxo)
# ==============================================================================

@dataclass
class ProcurementSession:
    config: dict         # LangGraph thread config
    channel: str         # Canal Slack onde a thread vive
    thread_ts: str       # Ts da mensagem raiz da thread (chave de sessão)
    user: str            # Slack user ID do solicitante
    waiting_for: Optional[str] = None
    # "missing_info"            → aguardando dados faltantes na thread
    # "edit_data"               → aguardando correção digitada na thread
    # "requester_confirmation"  → aguardando clique confirm/edit
    # "manager_approval"        → aguardando decisão do manager
    lock: threading.Lock = field(default_factory=threading.Lock)


# thread_ts → ProcurementSession
_sessions: dict[str, ProcurementSession] = {}

# Timestamps já processados — evita processar app_mention + message em duplicata
_processed: set[str] = set()
_processed_lock = threading.Lock()


def _find_session_by_channel_user(channel: str, user: str) -> Optional[ProcurementSession]:
    """Fallback: acha sessão ativa pelo canal + usuário."""
    for sess in _sessions.values():
        if (sess.channel == channel and sess.user == user
                and sess.waiting_for in ("missing_info", "edit_data")):
            return sess
    return None


# ==============================================================================
# HELPERS
# ==============================================================================

def _post(client, channel: str, thread_ts: str, **kwargs):
    """Envia mensagem sempre na thread do canal."""
    return client.chat_postMessage(channel=channel, thread_ts=thread_ts, **kwargs)


def _get_user_name(user: str, client) -> str:
    try:
        info    = client.users_info(user=user)
        u       = info["user"]
        profile = u.get("profile", {})
        return (
            profile.get("real_name_normalized")
            or profile.get("real_name")
            or profile.get("display_name_normalized")
            or profile.get("display_name")
            or u.get("real_name")
            or u.get("name")
            or user
        )
    except Exception:
        return user


def _get_user_email(user: str, client) -> Optional[str]:
    try:
        info    = client.users_info(user=user)
        profile = info["user"].get("profile", {})
        return profile.get("email") or None
    except Exception:
        return None



# ==============================================================================
# ORQUESTRAÇÃO DO GRAFO
# ==============================================================================

def _run_step(session: ProcurementSession, payload: Any, client) -> None:
    """
    Executa um passo do grafo e interpreta o resultado para responder na thread.
    Sempre roda em thread separada para não bloquear o Bolt.
    """
    with session.lock:
        try:
            graph.invoke(payload, config=session.config)
        except Exception as e:
            log.error("_run_step ERRO: %s\n%s", e, traceback.format_exc())
            _post(client, session.channel, session.thread_ts,
                  text=f":x: Erro interno: `{e}`")
            _forget_session(session.thread_ts)
            _sessions.pop(session.thread_ts, None)
            return

        try:
            state = graph.get_state(session.config)
            log.debug("_run_step next=%s interrupts=%s", state.next, state.interrupts)

            # Grafo concluído
            if not state.next:
                _notify_completion(session, state.values, client)
                _forget_session(session.thread_ts)
                _sessions.pop(session.thread_ts, None)
                return

            # Lê interrupt
            interrupts = list(state.interrupts) if state.interrupts else []
            if not interrupts and state.tasks:
                interrupts = list(state.tasks[0].interrupts)

            if not interrupts:
                return

            prompt: str = interrupts[0].value
            log.debug("_run_step prompt=%s", repr(prompt[:80]))

            if "CONFIRMACAO" in prompt.upper():
                session.waiting_for = "requester_confirmation"
                _persist_session(session)
                _send_confirmation_card(session, prompt, client)
            elif "APROVACAO" in prompt.upper():
                session.waiting_for = "manager_approval"
                _persist_session(session)
                _send_approval_card(session, prompt, client)
            else:
                session.waiting_for = "missing_info"
                _persist_session(session)
                _post(client, session.channel, session.thread_ts,
                      text=(
                          ":warning: *Informações faltantes no contrato:*\n\n"
                          f"{prompt}\n\n_Responda nesta thread com os dados solicitados._"
                      ))

        except Exception as e:
            log.error("_run_step pós-invoke ERRO: %s\n%s", e, traceback.format_exc())
            _post(client, session.channel, session.thread_ts,
                  text=f":x: Erro ao processar resposta: `{e}`")
            _forget_session(session.thread_ts)
            _sessions.pop(session.thread_ts, None)


def _notify_completion(session: ProcurementSession, values: dict, client) -> None:
    if values.get("po_id"):
        data  = values.get("contract_data", {})
        valor = float(data.get("valor_total") or 0)
        valor_fmt = f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        _post(client, session.channel, session.thread_ts,
              text=(
                  f":white_check_mark: *Purchase Order criada com sucesso!*\n"
                  f">*ID da PO:* `{values['po_id']}`\n"
                  f">*Razão Social:* {data.get('razao_social', '-')}\n"
                  f">*CNPJ:* `{data.get('cnpj', '-')}`\n"
                  f">*Valor Total:* {valor_fmt}\n"
                  f">*Condição de Pagamento:* {data.get('condicao_pagamento', '-')}"
              ))
    else:
        _post(client, session.channel, session.thread_ts,
              text=(
                  f":no_entry: *Solicitação encerrada sem aprovação.*\n"
                  f"_{values.get('error_message', 'Sem detalhes disponíveis.')}_"
              ))


def _send_confirmation_card(session: ProcurementSession, prompt: str, client) -> None:
    """Card de confirmação dos dados — botões Confirmar / Alterar Dados."""
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "Confirmação dos Dados do Contrato"},
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"```{prompt}```"},
        },
        {"type": "divider"},
        {
            "type": "actions",
            "block_id": f"confirmation_{session.thread_ts}",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Confirmar e Enviar"},
                    "style": "primary",
                    "action_id": "confirm_data_po",
                    "value": session.thread_ts,
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Alterar Dados"},
                    "style": "danger",
                    "action_id": "edit_data_po",
                    "value": session.thread_ts,
                },
            ],
        },
    ]
    _post(client, session.channel, session.thread_ts,
          text="Confirme os dados extraídos do contrato.", blocks=blocks)


def _send_approval_card(session: ProcurementSession, prompt: str, client) -> None:
    """Posta card de aprovação no canal de managers."""
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "Solicitação de Aprovação de PO"},
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"```{prompt}```"},
        },
        {"type": "divider"},
        {
            "type": "actions",
            "block_id": f"approval_{session.thread_ts}",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Aprovar"},
                    "style": "primary",
                    "action_id": "approve_po",
                    "value": session.thread_ts,
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Rejeitar"},
                    "style": "danger",
                    "action_id": "reject_po",
                    "value": session.thread_ts,
                },
            ],
        },
    ]
    client.chat_postMessage(
        channel=MANAGER_CHANNEL,
        text="Nova solicitação de PO aguardando aprovação.",
        blocks=blocks,
    )
    _post(client, session.channel, session.thread_ts,
          text=(":hourglass_flowing_sand: Dados confirmados! "
                "Solicitação enviada para aprovação do gerente. Aguardando decisão..."))


# ==============================================================================
# DOWNLOAD DE PDF
# ==============================================================================

PDF_DIR = os.path.join(os.path.dirname(__file__), "PDF")
os.makedirs(PDF_DIR, exist_ok=True)


class _SlackAuthSession(requests.Session):
    def __init__(self, token: str):
        super().__init__()
        self.slack_token = token
        self.headers.update({"Authorization": f"Bearer {token}"})

    def rebuild_auth(self, prepared_request, _response):
        prepared_request.headers["Authorization"] = f"Bearer {self.slack_token}"


def _download_pdf(file_info: dict, client) -> str:
    import time
    file_id = file_info.get("id")
    fresh   = client.files_info(file=file_id)["file"]
    url     = fresh.get("url_private_download") or fresh.get("url_private")
    original_name = fresh.get("name", "contrato.pdf")

    log.debug("Baixando PDF: %s", url)
    sess     = _SlackAuthSession(SLACK_BOT_TOKEN)
    response = sess.get(url, stream=True, timeout=60)
    response.raise_for_status()

    content_type = response.headers.get("Content-Type", "")
    if "html" in content_type:
        preview = response.content[:300].decode("utf-8", errors="replace")
        raise ValueError(f"Slack retornou HTML (autenticação falhou). Preview: {preview}")

    timestamp = int(time.time())
    file_path = os.path.join(PDF_DIR, f"{timestamp}_{original_name}")
    with open(file_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)

    log.debug("PDF salvo: %s (%d bytes)", file_path, os.path.getsize(file_path))
    return file_path


# ==============================================================================
# INÍCIO DO FLUXO
# ==============================================================================

def _start_flow(event: dict, client, logger) -> None:
    """
    Inicia um novo fluxo de procurement na thread do canal.
    Chamado quando o usuário menciona o bot ou envia PDF no canal.
    """
    channel  = event.get("channel", "")
    user     = event.get("user", "")
    text     = event.get("text", "").strip()
    msg_ts   = event.get("ts", "")
    files    = event.get("files", [])
    pdf_files = [f for f in files if f.get("name", "").lower().endswith(".pdf")]

    # Deduplica (app_mention + message disparam para o mesmo evento)
    with _processed_lock:
        if msg_ts in _processed:
            return
        _processed.add(msg_ts)

    # Sem PDF → mostra card de escolha
    if not pdf_files:
        if msg_ts in _sessions:
            return
        encoded = f"{channel}|{msg_ts}|{user}"
        _post(client, channel, msg_ts,
              text="Como você gostaria de iniciar a solicitação de compra?",
              blocks=[
                  {
                      "type": "section",
                      "text": {
                          "type": "mrkdwn",
                          "text": (
                              ":wave: Olá! Como você gostaria de iniciar a solicitação de compra?\n\n"
                              ":page_facing_up: *Enviar PDF* — anexe o contrato e extraio os dados automaticamente.\n"
                              ":pencil: *Preencher Manualmente* — forneça os dados agora mesmo."
                          ),
                      },
                  },
                  {
                      "type": "actions",
                      "block_id": f"start_flow_{msg_ts}",
                      "elements": [
                          {
                              "type": "button",
                              "text": {"type": "plain_text", "text": "Enviar PDF"},
                              "action_id": "send_pdf_choice",
                              "value": encoded,
                          },
                          {
                              "type": "button",
                              "text": {"type": "plain_text", "text": "Preencher Manualmente"},
                              "style": "primary",
                              "action_id": "manual_fill_po",
                              "value": encoded,
                          },
                      ],
                  },
              ])
        return

    # Com PDF → inicia grafo
    if msg_ts in _sessions:
        return

    _post(client, channel, msg_ts,
          text=":mag: Recebi o contrato! Estou analisando o PDF... aguarde.")

    try:
        pdf_path = _download_pdf(pdf_files[0], client)
    except Exception as e:
        logger.exception("Falha ao baixar PDF")
        _post(client, channel, msg_ts,
              text=f":x: Não consegui baixar o arquivo: `{e}`")
        return

    session = ProcurementSession(
        config={"configurable": {"thread_id": f"slack-{channel}-{msg_ts}"}},
        channel=channel,
        thread_ts=msg_ts,
        user=user,
    )
    _sessions[msg_ts] = session
    _persist_session(session)

    criado_por       = _get_user_name(user, client)
    criado_por_email = _get_user_email(user, client)

    thread_url = None
    try:
        permalink  = client.chat_getPermalink(channel=channel, message_ts=msg_ts)
        thread_url = permalink.get("permalink")
    except Exception:
        pass

    initial_state: AgentState = {
        "messages": [],
        "user_request": text or f"Contrato enviado via Slack: {pdf_files[0]['name']}",
        "pdf_path": pdf_path,
        "contract_text": "",
        "contract_data": {},
        "missing_fields": [],
        "supplier_status": None,
        "confirmation_status": None,
        "approval_status": None,
        "po_id": None,
        "error_message": None,
        "criado_por": criado_por,
        "criado_por_email": criado_por_email,
        "thread_url": thread_url,
    }

    threading.Thread(
        target=_run_step,
        args=(session, initial_state, client),
        daemon=True,
    ).start()


# ==============================================================================
# EVENT HANDLERS
# ==============================================================================

@app.event("app_mention")
def handle_app_mention(event: dict, client, logger) -> None:
    """Menção ao bot no canal — inicia novo fluxo ou encaminha resposta."""
    thread_ts = event.get("thread_ts")
    channel   = event.get("channel", "")
    user      = event.get("user", "")

    # Se há sessão ativa esperando input → encaminha texto
    session = _sessions.get(thread_ts) if thread_ts else None
    if session is None:
        session = _find_session_by_channel_user(channel, user)

    if session and session.waiting_for in ("missing_info", "edit_data"):
        raw_text = event.get("text", "")
        text = re.sub(r"<@[A-Z0-9]+>", "", raw_text).strip()
        if text:
            is_edit = session.waiting_for == "edit_data"
            session.waiting_for = None
            resume_text = f"edit:{text}" if is_edit else text
            log.debug("[MENTION] Resumindo com: %s", repr(resume_text[:60]))
            threading.Thread(
                target=_run_step,
                args=(session, Command(resume=resume_text), client),
                daemon=True,
            ).start()
        return

    if session:
        return  # sessão ativa mas não aguarda input

    # Nenhuma sessão → inicia novo fluxo
    _start_flow(event, client, logger)


@app.event("message")
def handle_message(event: dict, client, logger) -> None:
    """
    A) PDF enviado no canal → inicia fluxo
    B) Resposta na thread aguardando input → retoma grafo
    """
    if event.get("bot_id") or event.get("subtype") == "bot_message":
        return

    channel   = event.get("channel", "")
    user      = event.get("user", "")
    text      = event.get("text", "").strip()
    files     = event.get("files", [])
    thread_ts = event.get("thread_ts")

    # Cenário A: PDF enviado no canal
    if any(f.get("name", "").lower().endswith(".pdf") for f in files):
        _start_flow(event, client, logger)
        return

    # Cenário B: resposta em thread aguardando input
    session = _sessions.get(thread_ts) if thread_ts else None
    if session is None:
        session = _find_session_by_channel_user(channel, user)

    if session and session.waiting_for in ("missing_info", "edit_data") and text:
        is_edit = session.waiting_for == "edit_data"
        session.waiting_for = None
        resume_text = f"edit:{text}" if is_edit else text
        log.debug("[MSG] Resumindo com: %s", repr(resume_text[:60]))
        threading.Thread(
            target=_run_step,
            args=(session, Command(resume=resume_text), client),
            daemon=True,
        ).start()


# ==============================================================================
# ACTIONS: escolha inicial
# ==============================================================================

@app.action("send_pdf_choice")
def handle_send_pdf_choice(ack, client, body) -> None:
    ack()
    client.chat_update(
        channel=body["channel"]["id"],
        ts=body["message"]["ts"],
        text="Aguardando PDF.",
        blocks=[{
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": ":page_facing_up: Pode enviar o contrato em PDF nesta thread. Vou extrair os dados automaticamente.",
            },
        }],
    )


@app.action("manual_fill_po")
def handle_manual_fill(ack, action: dict, client, body) -> None:
    ack()
    channel, msg_ts, user = action["value"].split("|", 2)

    if msg_ts in _sessions:
        return

    client.chat_update(
        channel=body["channel"]["id"],
        ts=body["message"]["ts"],
        text="Preenchimento manual iniciado.",
        blocks=[{
            "type": "section",
            "text": {"type": "mrkdwn", "text": ":pencil: Ótimo! Vou te pedir as informações necessárias."},
        }],
    )

    session = ProcurementSession(
        config={"configurable": {"thread_id": f"slack-{channel}-{msg_ts}"}},
        channel=channel,
        thread_ts=msg_ts,
        user=user,
    )
    _sessions[msg_ts] = session
    _persist_session(session)

    criado_por       = _get_user_name(user, client)
    criado_por_email = _get_user_email(user, client)

    thread_url = None
    try:
        permalink  = client.chat_getPermalink(channel=channel, message_ts=msg_ts)
        thread_url = permalink.get("permalink")
    except Exception:
        pass

    initial_state: AgentState = {
        "messages": [],
        "user_request": "Solicitação de compra manual via Slack",
        "pdf_path": None,
        "contract_text": "",
        "contract_data": {},
        "missing_fields": [],
        "supplier_status": None,
        "confirmation_status": None,
        "approval_status": None,
        "po_id": None,
        "error_message": None,
        "criado_por": criado_por,
        "criado_por_email": criado_por_email,
        "thread_url": thread_url,
    }

    threading.Thread(
        target=_run_step,
        args=(session, initial_state, client),
        daemon=True,
    ).start()


# ==============================================================================
# ACTIONS: confirmação do solicitante
# ==============================================================================

@app.action("confirm_data_po")
def handle_confirm_data(ack, action: dict, client, body) -> None:
    ack()
    thread_ts = action["value"]
    session   = _sessions.get(thread_ts)

    log.debug("[ACTION confirm] thread_ts=%s found=%s", thread_ts, session is not None)

    if not session:
        client.chat_postMessage(
            channel=body["channel"]["id"],
            text=":warning: Esta solicitação não está mais ativa (bot reiniciado). Envie o PDF novamente.",
        )
        return

    client.chat_update(
        channel=body["channel"]["id"],
        ts=body["message"]["ts"],
        text="Dados confirmados.",
        blocks=[{
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": ":white_check_mark: *Dados confirmados* por <@" + body["user"]["id"] + ">. Enviando para aprovação...",
            },
        }],
    )

    session.waiting_for = None
    _persist_session(session)
    threading.Thread(
        target=_run_step,
        args=(session, Command(resume="confirmed"), client),
        daemon=True,
    ).start()


@app.action("edit_data_po")
def handle_edit_data(ack, action: dict, client, body) -> None:
    ack()
    thread_ts = action["value"]
    session   = _sessions.get(thread_ts)

    log.debug("[ACTION edit] thread_ts=%s found=%s", thread_ts, session is not None)

    if not session:
        client.chat_postMessage(
            channel=body["channel"]["id"],
            text=":warning: Esta solicitação não está mais ativa (bot reiniciado). Envie o PDF novamente.",
        )
        return

    client.chat_update(
        channel=body["channel"]["id"],
        ts=body["message"]["ts"],
        text="Alteração solicitada.",
        blocks=[{
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": ":pencil: *Alteração solicitada* por <@" + body["user"]["id"] + ">",
            },
        }],
    )

    session.waiting_for = "edit_data"
    _persist_session(session)
    _post(client, session.channel, session.thread_ts,
          text=":pencil: Quais dados precisam ser alterados? Responda nesta thread.")


# ==============================================================================
# ACTIONS: aprovação do manager
# ==============================================================================

@app.action("approve_po")
def handle_approve(ack, action: dict, client, body) -> None:
    ack()
    thread_ts = action["value"]
    session   = _sessions.get(thread_ts)

    if not session:
        client.chat_postMessage(
            channel=body["channel"]["id"],
            text=":warning: Sessão expirada. Solicite ao usuário que envie o PDF novamente.",
        )
        return

    client.chat_update(
        channel=body["channel"]["id"],
        ts=body["message"]["ts"],
        text="PO aprovada.",
        blocks=[{
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": ":white_check_mark: *Aprovado* por <@" + body["user"]["id"] + ">",
            },
        }],
    )

    session.waiting_for = None
    _persist_session(session)
    threading.Thread(
        target=_run_step,
        args=(session, Command(resume="approved"), client),
        daemon=True,
    ).start()


@app.action("reject_po")
def handle_reject(ack, action: dict, client, body) -> None:
    ack()
    thread_ts = action["value"]
    session   = _sessions.get(thread_ts)

    if not session:
        client.chat_postMessage(
            channel=body["channel"]["id"],
            text=":warning: Sessão expirada. Solicite ao usuário que envie o PDF novamente.",
        )
        return

    client.chat_update(
        channel=body["channel"]["id"],
        ts=body["message"]["ts"],
        text="PO rejeitada.",
        blocks=[{
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": ":no_entry: *Rejeitado* por <@" + body["user"]["id"] + ">",
            },
        }],
    )

    session.waiting_for = None
    _persist_session(session)
    threading.Thread(
        target=_run_step,
        args=(session, Command(resume="rejected"), client),
        daemon=True,
    ).start()


# ==============================================================================
# ENTRY POINT
# ==============================================================================

if __name__ == "__main__":
    _init_session_store()
    _restore_sessions()
    print("Iniciando bot de Procurement no Slack (Socket Mode)...")
    SocketModeHandler(app, SLACK_APP_TOKEN).start()
