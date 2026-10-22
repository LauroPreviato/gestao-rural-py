from datetime import datetime
import os
from flask import Flask, redirect, render_template, request, url_for
import sqlite3

app = Flask(__name__)

# Garante que a pasta 'dados' existe
os.makedirs("dados", exist_ok=True)
DB_PATH = os.path.join("dados", "fazenda.db")


def init_db():
  """Cria todas as tabelas do sistema caso elas ainda não existam"""
  conn = sqlite3.connect(DB_PATH)
  cursor = conn.cursor()

  # 1. Tabela de Insumos
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS insumos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo TEXT NOT NULL,
            quantidade REAL NOT NULL,
            valor_total REAL NOT NULL,
            data_compra TEXT NOT NULL,
            custos_adicionais REAL DEFAULT 0
        )
    """)

  # 2. Tabela de Gado
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS gado (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            raca TEXT NOT NULL,
            quantidade INTEGER NOT NULL,
            peso REAL NOT NULL,
            numero_lote TEXT NOT NULL,
            data_compra TEXT NOT NULL,
            preco_arroba REAL NOT NULL,
            preco_lote REAL NOT NULL,
            preco_cabeca REAL NOT NULL,
            custos_adicionais REAL DEFAULT 0
        )
    """)

  # 3. Tabela de Manutenção / Custos Gerais
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS manutencao (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            categoria TEXT NOT NULL,
            descricao TEXT NOT NULL,
            valor REAL NOT NULL,
            data_gasto TEXT NOT NULL
        )
    """)

  # 4. Tabela de Engorda / Confinamento
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS engorda (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lote_id INTEGER,
            numero_lote TEXT NOT NULL,
            quantidade_animais INTEGER NOT NULL,
            data_entrada TEXT NOT NULL,
            data_saida TEXT,
            peso_entrada REAL NOT NULL,
            preco_arroba_entrada REAL NOT NULL,
            custo_total_insumos REAL DEFAULT 0,
            FOREIGN KEY (lote_id) REFERENCES gado (id)
        )
    """)

  # 5. Tabela para Lançamentos Diários de Consumo na Engorda
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS engorda_lancamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            engorda_id INTEGER,
            insumo_id INTEGER,
            quantidade_consumida REAL NOT NULL,
            data_lancamento TEXT NOT NULL,
            FOREIGN KEY (engorda_id) REFERENCES engorda (id),
            FOREIGN KEY (insumo_id) REFERENCES insumos (id)
        )
    """)

  conn.commit()
  conn.close()


# --- ROTA 0: TELA DE INÍCIO (Dashboard /) ---
@app.route("/")
def inicio():
  conn = sqlite3.connect(DB_PATH)
  conn.row_factory = sqlite3.Row
  cursor = conn.cursor()

  # Buscando algumas estatísticas rápidas para exibir na tela de início
  cursor.execute("SELECT COUNT(*) as total FROM gado")
  total_gado = cursor.fetchone()["total"]

  cursor.execute("SELECT COUNT(*) as total FROM insumos")
  total_insumos = cursor.fetchone()["total"]

  cursor.execute("SELECT COUNT(*) as total FROM engorda")
  total_engorda = cursor.fetchone()["total"]

  conn.close()

  return render_template(
      "inicio.html",
      total_gado=total_gado,
      total_insumos=total_insumos,
      total_engorda=total_engorda,
  )


# --- ROTA 1: INSUMOS (Movido para /insumos) ---
@app.route("/insumos", methods=["GET", "POST"])
def index():
  if request.method == "POST":
    tipo = request.form.get("tipo")
    quantidade = float(request.form.get("quantidade", 0))
    valor_total = float(request.form.get("valor_total", 0))
    data_compra = request.form.get("data_compra")
    custos_adicionais = float(request.form.get("custos_adicionais", 0) or 0)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
            INSERT INTO insumos (tipo, quantidade, valor_total, data_compra, custos_adicionais)
            VALUES (?, ?, ?, ?, ?)
        """,
        (tipo, quantidade, valor_total, data_compra, custos_adicionais),
    )
    conn.commit()
    conn.close()

    return redirect(url_for("index"))

  conn = sqlite3.connect(DB_PATH)
  conn.row_factory = sqlite3.Row
  cursor = conn.cursor()
  cursor.execute("SELECT * FROM insumos ORDER BY data_compra DESC")
  insumos_db = cursor.fetchall()
  conn.close()

  return render_template("insumos.html", insumos=insumos_db)


# --- ROTA 2: GADO (/gado) ---
@app.route("/gado", methods=["GET", "POST"])
def cadastro_gado():
  if request.method == "POST":
    raca = request.form.get("raca")
    quantidade = int(request.form.get("quantidade") or 1)
    peso = float(request.form.get("peso") or 0)
    numero_lote = request.form.get("numero_lote")
    data_compra = request.form.get("data_compra")
    preco_arroba = float(request.form.get("preco_arroba") or 0)
    preco_lote = float(request.form.get("preco_lote") or 0)
    preco_cabeca = float(request.form.get("preco_cabeca") or 0)
    custos_adicionais = float(request.form.get("custos_adicionais") or 0)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
            INSERT INTO gado (raca, quantidade, peso, numero_lote, data_compra, preco_arroba, preco_lote, preco_cabeca, custos_adicionais)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            raca,
            quantidade,
            peso,
            numero_lote,
            data_compra,
            preco_arroba,
            preco_lote,
            preco_cabeca,
            custos_adicionais,
        ),
    )
    conn.commit()
    conn.close()

    return redirect(url_for("cadastro_gado"))

  conn = sqlite3.connect(DB_PATH)
  conn.row_factory = sqlite3.Row
  cursor = conn.cursor()
  cursor.execute("SELECT * FROM gado ORDER BY data_compra DESC")
  lotes_db = cursor.fetchall()
  conn.close()

  return render_template("gado.html", lotes=lotes_db)


# --- ROTA 3: MANUTENÇÃO (/manutencao) ---
@app.route("/manutencao", methods=["GET", "POST"])
def cadastro_manutencao():
  if request.method == "POST":
    categoria = request.form.get("categoria")
    descricao = request.form.get("descricao")
    valor = float(request.form.get("valor") or 0)
    data_gasto = request.form.get("data_gasto")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
            INSERT INTO manutencao (categoria, descricao, valor, data_gasto)
            VALUES (?, ?, ?, ?)
        """,
        (categoria, descricao, valor, data_gasto),
    )
    conn.commit()
    conn.close()

    return redirect(url_for("cadastro_manutencao"))

  conn = sqlite3.connect(DB_PATH)
  conn.row_factory = sqlite3.Row
  cursor = conn.cursor()
  cursor.execute("SELECT * FROM manutencao ORDER BY data_gasto DESC")
  manutencao_db = cursor.fetchall()
  conn.close()

  return render_template("manutencao.html", registros=manutencao_db)


# --- ROTA 4: ENGORDA E CONSUMO DIÁRIO (/engorda) ---
@app.route("/engorda", methods=["GET", "POST"])
def gerenciar_engorda():
  conn = sqlite3.connect(DB_PATH)
  conn.row_factory = sqlite3.Row
  cursor = conn.cursor()

  if request.method == "POST":
    acao = request.form.get("acao")

    # AÇÃO 1: Iniciar um novo lote em engorda/confinamento
    if acao == "iniciar_lote":
      lote_id = request.form.get("lote_id")
      data_entrada = request.form.get("data_entrada")

      cursor.execute("SELECT * FROM gado WHERE id = ?", (lote_id,))
      lote = cursor.fetchone()

      if lote:
        cursor.execute(
            """
                INSERT INTO engorda (lote_id, numero_lote, quantidade_animais, data_entrada, peso_entrada, preco_arroba_entrada)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                lote_id,
                lote["numero_lote"],
                lote["quantidade"],
                data_entrada,
                lote["peso"],
                lote["preco_arroba"],
            ),
        )
        conn.commit()

    # AÇÃO 2: Registrar consumo diário (ex: 10kg hoje, 8kg amanhã) com baixa de estoque
    elif acao == "registrar_consumo":
      engorda_id = request.form.get("engorda_id")
      insumo_id = request.form.get("insumo_id")
      quantidade_consumida = float(
          request.form.get("quantidade_consumida") or 0
      )
      data_lancamento = request.form.get("data_lancamento")

      if engorda_id and insumo_id and quantidade_consumida > 0:
        cursor.execute(
            """
                INSERT INTO engorda_lancamentos (engorda_id, insumo_id, quantidade_consumida, data_lancamento)
                VALUES (?, ?, ?, ?)
            """,
            (
                engorda_id,
                insumo_id,
                quantidade_consumida,
                data_lancamento,
            ),
        )

        # Dá baixa automática no estoque geral de insumos
        cursor.execute("SELECT * FROM insumos WHERE id = ?", (insumo_id,))
        insumo = cursor.fetchone()
        if insumo:
          nova_qtd = insumo["quantidade"] - quantidade_consumida
          cursor.execute(
              "UPDATE insumos SET quantidade = ? WHERE id = ?",
              (max(0, nova_qtd), insumo_id),
          )

        # Recalcula o custo total de insumos desse lote de engorda
        cursor.execute(
            """
                SELECT el.quantidade_consumida, i.valor_total, i.quantidade as qtd_original
                FROM engorda_lancamentos el
                JOIN insumos i ON el.insumo_id = i.id
                WHERE el.engorda_id = ?
            """,
            (engorda_id,),
        )
        lancamentos = cursor.fetchall()

        custo_total = 0
        for l in lancamentos:
          if l["qtd_original"] > 0:
            preco_unit = l["valor_total"] / l["qtd_original"]
            custo_total += l["quantidade_consumida"] * preco_unit

        cursor.execute(
            "UPDATE engorda SET custo_total_insumos = ? WHERE id = ?",
            (custo_total, engorda_id),
        )
        conn.commit()

    conn.close()
    return redirect(url_for("gerenciar_engorda"))

  cursor.execute("SELECT * FROM gado")
  lotes_gado = cursor.fetchall()

  cursor.execute("SELECT * FROM insumos")
  estoque_insumos = cursor.fetchall()

  cursor.execute("""
        SELECT e.*, 
        (julianday(COALESCE(e.data_saida, 'now')) - julianday(e.data_entrada)) AS dias_confinado
        FROM engorda e ORDER BY e.data_entrada DESC
    """)
  lotes_engorda = cursor.fetchall()

  cursor.execute("""
        SELECT el.*, i.tipo as nome_insumo, e.numero_lote
        FROM engorda_lancamentos el
        JOIN insumos i ON el.insumo_id = i.id
        JOIN engorda e ON el.engorda_id = e.id
        ORDER BY el.data_lancamento DESC
    """)
  historico_lancamentos = cursor.fetchall()

  conn.close()

  return render_template(
      "engorda.html",
      lotes=lotes_gado,
      insumos=estoque_insumos,
      lotes_engorda=lotes_engorda,
      lancamentos=historico_lancamentos,
  )


if __name__ == "__main__":
  init_db()
  app.run(debug=True)