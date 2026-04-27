"""
API REST de Procurement — FastAPI + SQLite
==========================================
Endpoints:
  GET  /auth/config      Retorna o Google Client ID para o frontend
  POST /auth/google      Valida token Google e verifica domínio corporativo
  GET  /api/pos          Lista todas as POs (com filtro opcional por fornecedor)
  GET  /api/pos/{id}     Detalhe de uma PO
  GET  /static/pdf/...   Serve os arquivos PDF da pasta PDF/
"""

import json
import os
import sqlite3
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from urllib.parse import urlparse, parse_qs
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from slack_sdk import WebClient as SlackClient

load_dotenv()

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

BASE_DIR       = os.path.dirname(__file__)
DB_PATH        = os.path.join(BASE_DIR, "procurement.db")
PDF_DIR        = os.path.join(BASE_DIR, "PDF")
BASE_URL       = os.getenv("BASE_URL", "http://localhost:8000")
GOOGLE_CLIENT_ID  = os.getenv("GOOGLE_CLIENT_ID", "")
ALLOWED_DOMAIN    = os.getenv("ALLOWED_DOMAIN", "vtex.com")
SLACK_BOT_TOKEN   = os.getenv("SLACK_BOT_TOKEN", "")
_raw_emails      = os.getenv("ALLOWED_EMAILS", "")
ALLOWED_EMAILS   = {e.strip().lower() for e in _raw_emails.split(",") if e.strip()}

app = FastAPI(title="Procurement API", version="1.0.0")


# CORS — frontend local (porta 3000) e eventuais outros origins de dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve os PDFs como arquivos estáticos: GET /static/pdf/{filename}
os.makedirs(PDF_DIR, exist_ok=True)
app.mount("/static/pdf", StaticFiles(directory=PDF_DIR), name="pdf")

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class GoogleAuthRequest(BaseModel):
    credential: str


@app.get("/auth/config")
def auth_config():
    """Retorna o Google Client ID público para o frontend inicializar o GIS."""
    return {"client_id": GOOGLE_CLIENT_ID}


@app.post("/auth/google")
def google_auth(body: GoogleAuthRequest):
    """
    Valida o ID token emitido pelo Google.
    Rejeita com 403 se o domínio do e-mail não for o corporativo permitido.
    """
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=500, detail="GOOGLE_CLIENT_ID não configurado no servidor.")

    try:
        idinfo = id_token.verify_oauth2_token(
            body.credential,
            google_requests.Request(),
            GOOGLE_CLIENT_ID,
        )
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=f"Token inválido: {exc}")

    email  = idinfo.get("email", "").lower()
    domain = email.split("@")[-1] if "@" in email else ""

    if ALLOWED_EMAILS:
        if email not in ALLOWED_EMAILS:
            raise HTTPException(status_code=403, detail="Seu e-mail não está na lista de acesso autorizado.")
    elif domain != ALLOWED_DOMAIN:
        raise HTTPException(
            status_code=403,
            detail=f"Domínio '{domain}' não autorizado. Acesso restrito ao domínio '{ALLOWED_DOMAIN}'.",
        )

    return {
        "email":   email,
        "name":    idinfo.get("name", ""),
        "picture": idinfo.get("picture", ""),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _migrate_db() -> None:
    new_cols = [
        "criado_por TEXT",
        "criado_por_email TEXT",
        "thread_url TEXT",
        "motivo_rejeicao TEXT",
        "rejeitado_por TEXT",
        "aprovado_por TEXT",
        "moeda TEXT",
        "data_inicio TEXT",
        "data_termino TEXT",
        "descricao_itens TEXT",
        "escopo TEXT",
        "contratante_nome TEXT",
        "contratante_cnpj TEXT",
        "fornecedor_pais TEXT",
        "alerta_pj TEXT",
        "contato_nome TEXT",
        "contato_email TEXT",
        "frequencia_pagamento TEXT",
        "assinaturas TEXT",
        "step_approvals TEXT",
        "responsavel TEXT",
        "purchase_number TEXT",
        "area_solicitante TEXT",
        "centro_custo TEXT",
    ]
    with get_conn() as conn:
        for col_def in new_cols:
            try:
                conn.execute(f"ALTER TABLE purchase_orders ADD COLUMN {col_def}")
            except sqlite3.OperationalError:
                pass


_RESPONSAVEIS = ["Laurie", "Julia", "Fernanda", "Emily", "Aylton", "Ana Caroline", "Alyne"]


def _seed_responsaveis() -> None:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id FROM purchase_orders WHERE responsavel IS NULL"
        ).fetchall()
        for row in rows:
            name = _RESPONSAVEIS[row["id"] % len(_RESPONSAVEIS)]
            conn.execute(
                "UPDATE purchase_orders SET responsavel = ? WHERE id = ?",
                (name, row["id"]),
            )


def _next_purchase_number(conn: sqlite3.Connection) -> str:
    """Gera o próximo purchase number no formato Pxxxxx (sequencial)."""
    row = conn.execute(
        "SELECT purchase_number FROM purchase_orders "
        "WHERE purchase_number IS NOT NULL ORDER BY id DESC LIMIT 1"
    ).fetchone()
    last_num = int(row["purchase_number"][1:]) if row and row["purchase_number"] else 0
    return f"P{last_num + 1:05d}"


def _seed_purchase_numbers() -> None:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id FROM purchase_orders WHERE purchase_number IS NULL ORDER BY id"
        ).fetchall()
        for i, row in enumerate(rows, start=1):
            conn.execute(
                "UPDATE purchase_orders SET purchase_number = ? WHERE id = ?",
                (f"P{i:05d}", row["id"]),
            )


_migrate_db()
_seed_responsaveis()
_seed_purchase_numbers()


def _notify_rejeicao_slack(thread_url: str, motivo: str, numero_po: str) -> None:
    print(f"[SLACK] token presente={bool(SLACK_BOT_TOKEN)} thread_url={thread_url}")
    if not SLACK_BOT_TOKEN or not thread_url:
        print("[SLACK] Abortando: token ou thread_url ausente.")
        return
    try:
        parsed  = urlparse(thread_url)
        parts   = parsed.path.rstrip("/").split("/")
        channel = parts[-2]
        qs      = parse_qs(parsed.query)
        ts      = qs.get("thread_ts", [""])[0]
        if not ts:
            # fallback: extrai do path p1777060433017619 → 1777060433.017619
            ts_raw = parts[-1]
            ts     = ts_raw[1:-6] + "." + ts_raw[-6:]
        print(f"[SLACK] Enviando para channel={channel} thread_ts={ts}")
        resp = SlackClient(token=SLACK_BOT_TOKEN).chat_postMessage(
            channel=channel,
            thread_ts=ts,
            text=(
                f":x: Sua PO *{numero_po}* foi *rejeitada*.\n\n"
                f"*Motivo:* {motivo}"
            ),
        )
        print(f"[SLACK] Resposta: ok={resp.get('ok')} error={resp.get('error')}")
    except Exception as e:
        print(f"[SLACK] Exceção: {e}")


def row_to_po(row: sqlite3.Row) -> dict:
    """Converte uma linha do banco em dict enriquecido com saldo e pdf_url completa."""
    d = dict(row)

    # Saldo calculado dinamicamente
    d["saldo"] = round(d.get("valor_total", 0) - d.get("valor_utilizado", 0), 2)

    # Garante que pdf_url seja uma URL completa acessível pelo frontend
    pdf = d.get("pdf_url") or ""
    if pdf:
        filename = os.path.basename(pdf)   # aceita tanto path absoluto quanto só o nome
        d["pdf_url"] = f"{BASE_URL}/static/pdf/{filename}"
    else:
        d["pdf_url"] = None

    # Deserializa step_approvals de JSON para lista
    raw = d.get("step_approvals") or "[]"
    try:
        approvals = json.loads(raw)
    except Exception:
        approvals = []
    while len(approvals) < 5:
        approvals.append(None)
    d["step_approvals"] = approvals

    return d


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/pos")
def list_pos(
    search:     Optional[str] = Query(None, description="Filtrar por fornecedor"),
    responsavel: Optional[str] = Query(None, description="Filtrar por responsável"),
):
    conditions, params = [], []
    if search:
        conditions.append("fornecedor LIKE ?")
        params.append(f"%{search}%")
    if responsavel:
        conditions.append("responsavel = ?")
        params.append(responsavel)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM purchase_orders {where} ORDER BY data_criacao DESC",
            params,
        ).fetchall()

    return [row_to_po(r) for r in rows]


@app.get("/api/pos/{po_id}")
def get_po(po_id: int):
    """Retorna o detalhe de uma PO específica pelo ID."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM purchase_orders WHERE id = ?", (po_id,)
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="PO não encontrada.")

    return row_to_po(row)


class StatusUpdate(BaseModel):
    status: str
    motivo_rejeicao: Optional[str] = None
    rejeitado_por: Optional[str] = None
    aprovado_por: Optional[str] = None


@app.patch("/api/pos/{po_id}/status")
def update_po_status(po_id: int, body: StatusUpdate):
    allowed = {"Pendente validação", "Validado", "Rejeitado"}
    if body.status not in allowed:
        raise HTTPException(status_code=400, detail="Status inválido.")

    with get_conn() as conn:
        updated = conn.execute(
            "UPDATE purchase_orders SET status = ?, motivo_rejeicao = ?, rejeitado_por = ?, aprovado_por = ? WHERE id = ?",
            (body.status, body.motivo_rejeicao, body.rejeitado_por, body.aprovado_por, po_id),
        ).rowcount
        if not updated:
            raise HTTPException(status_code=404, detail="PO não encontrada.")
        if body.status == "Rejeitado" and body.motivo_rejeicao:
            row = conn.execute(
                "SELECT thread_url, numero_po FROM purchase_orders WHERE id = ?", (po_id,)
            ).fetchone()

    if body.status == "Rejeitado" and body.motivo_rejeicao:
        print(f"[REJEICAO] row={dict(row) if row else None}")
        if row and row["thread_url"]:
            _notify_rejeicao_slack(row["thread_url"], body.motivo_rejeicao, row["numero_po"])
        else:
            print("[REJEICAO] thread_url ausente no banco — notificação não enviada.")

    return {"ok": True}


class StepApprovalRequest(BaseModel):
    step: int
    approver: str
    date: str


TOTAL_STEPS = 5


@app.patch("/api/pos/{po_id}/approve-step")
def approve_step(po_id: int, body: StepApprovalRequest):
    if not (0 <= body.step < TOTAL_STEPS):
        raise HTTPException(status_code=400, detail="Step inválido (0-4).")

    with get_conn() as conn:
        row = conn.execute(
            "SELECT step_approvals FROM purchase_orders WHERE id = ?", (po_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="PO não encontrada.")

        try:
            approvals = json.loads(row["step_approvals"] or "[]")
        except Exception:
            approvals = []
        while len(approvals) < TOTAL_STEPS:
            approvals.append(None)

        approvals[body.step] = {"approver": body.approver, "date": body.date}

        all_done = all(a is not None for a in approvals)
        approvals_json = json.dumps(approvals)

        if all_done:
            conn.execute(
                "UPDATE purchase_orders SET step_approvals = ?, status = ?, aprovado_por = ? WHERE id = ?",
                (approvals_json, "Validado", body.approver, po_id),
            )
            new_status = "Validado"
        else:
            conn.execute(
                "UPDATE purchase_orders SET step_approvals = ? WHERE id = ?",
                (approvals_json, po_id),
            )
            new_status = "Pendente validação"

    return {"ok": True, "status": new_status, "step_approvals": approvals}


@app.get("/health")
def health():
    return {"status": "ok"}
