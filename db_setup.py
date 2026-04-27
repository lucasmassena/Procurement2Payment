"""
Inicialização do banco SQLite para o MVP de Procurement.
Execute sempre que precisar recriar o esquema: python db_setup.py
"""

import sqlite3


def init_db(db_path: str = "procurement.db") -> None:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Cadastro de fornecedores
    cur.execute("""
        CREATE TABLE IF NOT EXISTS suppliers (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            cnpj    TEXT    NOT NULL UNIQUE,
            name    TEXT    NOT NULL,
            status  TEXT    NOT NULL DEFAULT 'active'
        )
    """)

    # Purchase Orders — recria com esquema completo (migração destrutiva para MVP)
    cur.execute("DROP TABLE IF EXISTS purchase_orders")
    cur.execute("""
        CREATE TABLE purchase_orders (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            numero_po           TEXT    NOT NULL,
            fornecedor          TEXT    NOT NULL DEFAULT '',
            cnpj                TEXT    NOT NULL DEFAULT '',
            valor_total         REAL    NOT NULL DEFAULT 0,
            valor_utilizado     REAL    NOT NULL DEFAULT 0,
            condicao_pagamento  TEXT    DEFAULT NULL,
            status              TEXT    NOT NULL DEFAULT 'Pendente validação',
            pdf_url             TEXT    DEFAULT NULL,
            criado_por          TEXT    DEFAULT NULL,
            thread_url          TEXT    DEFAULT NULL,
            motivo_rejeicao     TEXT    DEFAULT NULL,
            rejeitado_por       TEXT    DEFAULT NULL,
            aprovado_por        TEXT    DEFAULT NULL,
            data_criacao        TEXT    NOT NULL DEFAULT (datetime('now')),
            -- Novos campos de extração
            moeda               TEXT    DEFAULT NULL,
            data_inicio         TEXT    DEFAULT NULL,
            data_termino        TEXT    DEFAULT NULL,
            descricao_itens     TEXT    DEFAULT NULL,
            escopo              TEXT    DEFAULT NULL,
            contratante_nome    TEXT    DEFAULT NULL,
            contratante_cnpj    TEXT    DEFAULT NULL,
            fornecedor_pais     TEXT    DEFAULT NULL,
            alerta_pj           TEXT    DEFAULT NULL,
            contato_nome        TEXT    DEFAULT NULL,
            contato_email       TEXT    DEFAULT NULL,
            frequencia_pagamento TEXT   DEFAULT NULL,
            assinaturas         TEXT    DEFAULT NULL
        )
    """)

    # Fornecedores de exemplo
    cur.executemany(
        "INSERT OR IGNORE INTO suppliers (cnpj, name, status) VALUES (?, ?, ?)",
        [
            ("00000000000191", "Banco do Brasil S.A.", "active"),
            ("99999999000199", "Fornecedor Bloqueado Ltda", "blocked"),
        ],
    )

    # PO de exemplo apontando para o PDF disponível na pasta
    pdf_example = "CONTRATO_VTEX_PROMED_assinado.pdf"
    cur.execute(
        """
        INSERT OR IGNORE INTO purchase_orders
            (numero_po, fornecedor, cnpj, valor_total, valor_utilizado,
             condicao_pagamento, status, pdf_url)
        SELECT 'PO-000001','PROMED Industria e Comercio Ltda','12345678000199',
               150000.00, 45000.00, '30/60/90 dias', 'approved', ?
        WHERE NOT EXISTS (SELECT 1 FROM purchase_orders WHERE numero_po = 'PO-000001')
        """,
        (pdf_example,),
    )

    conn.commit()
    conn.close()
    print(f"Banco '{db_path}' inicializado com sucesso.")



if __name__ == "__main__":
    init_db()
