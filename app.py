from datetime import datetime
import os
import io
import sqlite3
from flask import Flask, redirect, render_template, request, url_for, make_response
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

app = Flask(__name__)

# Garante que a pasta 'dados' existe
os.makedirs("dados", exist_ok=True)
DB_PATH = os.path.join("dados", "fazenda.db")


def init_db():
    """Cria todas as tabelas do sistema caso elas ainda não existam e atualiza colunas se necessário"""
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

    # 2. Tabela de Gado (Compra Inicial)
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
            custos_adicionais REAL DEFAULT 0,
            status TEXT DEFAULT 'Disponível'
        )
    """)
    try:
        cursor.execute("ALTER TABLE gado ADD COLUMN status TEXT DEFAULT 'Disponível'")
    except sqlite3.OperationalError:
        pass

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

    # 4. Tabela de Fases (Recria ou Engorda)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fases_lote (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lote_id INTEGER,
            numero_lote TEXT NOT NULL,
            etapa TEXT NOT NULL, -- 'Recria' ou 'Engorda'
            quantidade_animais INTEGER NOT NULL,
            data_entrada TEXT NOT NULL,
            data_saida TEXT,
            peso_entrada REAL NOT NULL,
            preco_arroba_entrada REAL NOT NULL,
            custo_total_insumos REAL DEFAULT 0,
            status TEXT DEFAULT 'Ativo', -- 'Ativo', 'Finalizado'
            FOREIGN KEY (lote_id) REFERENCES gado (id)
        )
    """)
    try:
        cursor.execute("ALTER TABLE fases_lote ADD COLUMN status TEXT DEFAULT 'Ativo'")
    except sqlite3.OperationalError:
        pass

    # 5. Tabela para Lançamentos Diários de Consumo na Fase
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fase_lancamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fase_id INTEGER,
            insumo_id INTEGER,
            quantidade_consumida REAL NOT NULL,
            data_lancamento TEXT NOT NULL,
            FOREIGN KEY (fase_id) REFERENCES fases_lote (id),
            FOREIGN KEY (insumo_id) REFERENCES insumos (id)
        )
    """)

    # 6. Tabela de Gado Abatido / Venda Direta
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS abate (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fase_id INTEGER,
            numero_lote TEXT NOT NULL,
            data_abate TEXT NOT NULL,
            quantidade_cabecas INTEGER NOT NULL,
            peso_vivo_embarque REAL NOT NULL,
            peso_total_carcaca REAL NOT NULL,
            rendimento_carcaca REAL,
            valor_recebido REAL NOT NULL,
            observacoes TEXT,
            FOREIGN KEY (fase_id) REFERENCES fases_lote (id)
        )
    """)
    try:
        cursor.execute("ALTER TABLE abate ADD COLUMN fase_id INTEGER")
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()


# --- ROTA 0: TELA DE INÍCIO (Dashboard /) ---
@app.route("/")
def inicio():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) as total FROM gado")
    total_gado = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) as total FROM insumos")
    total_insumos = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) as total FROM fases_lote")
    total_fases = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) as total FROM abate")
    total_abate = cursor.fetchone()["total"]

    conn.close()

    return render_template(
        "inicio.html",
        total_gado=total_gado,
        total_insumos=total_insumos,
        total_engorda=total_fases,
        total_abate=total_abate,
    )


# --- ROTA 1: INSUMOS (/insumos) ---
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
            INSERT INTO gado (raca, quantidade, peso, numero_lote, data_compra, preco_arroba, preco_lote, preco_cabeca, custos_adicionais, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Disponível')
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


# --- ROTA 4: GERENCIAR FASES (Recria / Engorda / Consumo / Baixa) ---
@app.route("/fases", methods=["GET", "POST"])
def gerenciar_fases():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if request.method == "POST":
        acao = request.form.get("acao")

        # 1. Iniciar fase a partir da compra (Recria ou Engorda direta)
        if acao == "iniciar_fase":
            lote_id = request.form.get("lote_id")
            etapa = request.form.get("etapa")  # 'Recria' ou 'Engorda'
            data_entrada = request.form.get("data_entrada")
            peso_entrada = float(request.form.get("peso_entrada") or 0)

            cursor.execute("SELECT * FROM gado WHERE id = ?", (lote_id,))
            lote = cursor.fetchone()

            if lote:
                cursor.execute(
                    """
                    INSERT INTO fases_lote (lote_id, numero_lote, etapa, quantidade_animais, data_entrada, peso_entrada, preco_arroba_entrada, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'Ativo')
                """,
                    (
                        lote_id,
                        lote["numero_lote"],
                        etapa,
                        lote["quantidade"],
                        data_entrada,
                        peso_entrada,
                        lote["preco_arroba"],
                    ),
                )

                cursor.execute(
                    "UPDATE gado SET status = ? WHERE id = ?",
                    (f"Em {etapa}", lote_id),
                )
                conn.commit()

        # 2. Transição: Mover lote da Recria para a Engorda
        elif acao == "mudar_para_engorda":
            fase_atual_id = request.form.get("fase_atual_id")
            data_entrada_engorda = request.form.get("data_entrada_engorda")
            peso_entrada_engorda = float(request.form.get("peso_entrada_engorda") or 0)
            data_saida_recria = request.form.get("data_saida_recria")

            cursor.execute("SELECT * FROM fases_lote WHERE id = ?", (fase_atual_id,))
            fase_antiga = cursor.fetchone()

            if fase_antiga:
                cursor.execute(
                    """
                    UPDATE fases_lote 
                    SET data_saida = ?, status = 'Finalizado' 
                    WHERE id = ?
                """,
                    (data_saida_recria, fase_atual_id),
                )

                cursor.execute(
                    """
                    INSERT INTO fases_lote (lote_id, numero_lote, etapa, quantidade_animais, data_entrada, peso_entrada, preco_arroba_entrada, status)
                    VALUES (?, ?, 'Engorda', ?, ?, ?, ?, 'Ativo')
                """,
                    (
                        fase_antiga["lote_id"],
                        fase_antiga["numero_lote"],
                        fase_antiga["quantidade_animais"],
                        data_entrada_engorda,
                        peso_entrada_engorda,
                        fase_antiga["preco_arroba_entrada"],
                    ),
                )

                cursor.execute(
                    "UPDATE gado SET status = 'Em Engorda' WHERE id = ?",
                    (fase_antiga["lote_id"],),
                )
                conn.commit()

        # 3. Dar baixa / Finalizar fase manualmente (Recria ou Engorda)
        elif acao == "finalizar_fase":
            fase_id = request.form.get("fase_id")
            data_saida = request.form.get("data_saida")

            cursor.execute("SELECT * FROM fases_lote WHERE id = ?", (fase_id,))
            fase_atual = cursor.fetchone()

            if fase_atual:
                cursor.execute(
                    """
                    UPDATE fases_lote 
                    SET data_saida = ?, status = 'Finalizado' 
                    WHERE id = ?
                """,
                    (data_saida, fase_id),
                )

                cursor.execute(
                    "UPDATE gado SET status = 'Concluído' WHERE id = ?",
                    (fase_atual["lote_id"],),
                )
                conn.commit()

        # 4. Registrar consumo de insumos na fase ativa
        elif acao == "registrar_consumo":
            fase_id = request.form.get("fase_id")
            insumo_id = request.form.get("insumo_id")
            quantidade_consumida = float(request.form.get("quantidade_consumida") or 0)
            data_lancamento = request.form.get("data_lancamento")

            if fase_id and insumo_id and quantidade_consumida > 0:
                cursor.execute(
                    """
                    INSERT INTO fase_lancamentos (fase_id, insumo_id, quantidade_consumida, data_lancamento)
                    VALUES (?, ?, ?, ?)
                """,
                    (fase_id, insumo_id, quantidade_consumida, data_lancamento),
                )

                cursor.execute("SELECT * FROM insumos WHERE id = ?", (insumo_id,))
                insumo = cursor.fetchone()
                if insumo:
                    nova_qtd = insumo["quantidade"] - quantidade_consumida
                    cursor.execute(
                        "UPDATE insumos SET quantidade = ? WHERE id = ?",
                        (max(0, nova_qtd), insumo_id),
                    )

                cursor.execute(
                    """
                    SELECT fl.quantidade_consumida, i.valor_total, i.quantidade as qtd_original
                    FROM fase_lancamentos fl
                    JOIN insumos i ON fl.insumo_id = i.id
                    WHERE fl.fase_id = ?
                """,
                    (fase_id,),
                )
                lancamentos = cursor.fetchall()

                custo_total = 0
                for l in lancamentos:
                    if l["qtd_original"] > 0:
                        preco_unit = l["valor_total"] / l["qtd_original"]
                        custo_total += l["quantidade_consumida"] * preco_unit

                cursor.execute(
                    "UPDATE fases_lote SET custo_total_insumos = ? WHERE id = ?",
                    (custo_total, fase_id),
                )
                conn.commit()

        conn.close()
        return redirect(url_for("gerenciar_fases"))

    cursor.execute("SELECT * FROM gado WHERE status = 'Disponível'")
    lotes_disponiveis = cursor.fetchall()

    cursor.execute("SELECT * FROM insumos")
    estoque_insumos = cursor.fetchall()

    cursor.execute("""
        SELECT f.*, 
        (julianday(COALESCE(f.data_saida, 'now')) - julianday(f.data_entrada)) AS dias_fase
        FROM fases_lote f 
        WHERE f.status = 'Ativo'
        ORDER BY f.data_entrada DESC
    """)
    fases_ativas = cursor.fetchall()

    cursor.execute("""
        SELECT fl.*, i.tipo as nome_insumo, f.numero_lote, f.etapa
        FROM fase_lancamentos fl
        JOIN insumos i ON fl.insumo_id = i.id
        JOIN fases_lote f ON fl.fase_id = f.id
        ORDER BY fl.data_lancamento DESC
    """)
    historico_lancamentos = cursor.fetchall()

    conn.close()

    return render_template(
        "fases.html",
        lotes_disponiveis=lotes_disponiveis,
        insumos=estoque_insumos,
        fases_ativas=fases_ativas,
        lancamentos=historico_lancamentos,
    )


# --- ROTA 5: RELATÓRIOS (/relatorios) ---
@app.route("/relatorios")
def relatorios():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT f.*, 
        (julianday(COALESCE(f.data_saida, 'now')) - julianday(f.data_entrada)) AS dias_fase
        FROM fases_lote f 
        ORDER BY f.data_entrada DESC
    """)
    relatorio_fases = cursor.fetchall()

    cursor.execute("""
        SELECT *, (valor_total + custos_adicionais) as custo_final_total 
        FROM insumos 
        ORDER BY data_compra DESC
    """)
    relatorio_insumos = cursor.fetchall()

    cursor.execute("""
        SELECT *, (preco_lote + custos_adicionais) as custo_final_lote 
        FROM gado 
        ORDER BY data_compra DESC
    """)
    relatorio_gado = cursor.fetchall()

    cursor.execute("""
        SELECT * FROM manutencao 
        ORDER BY data_gasto DESC
    """)
    relatorio_manutencao = cursor.fetchall()

    cursor.execute("SELECT SUM(valor_total + custos_adicionais) as total FROM insumos")
    gasto_insumos = cursor.fetchone()["total"] or 0

    cursor.execute("SELECT SUM(preco_lote + custos_adicionais) as total FROM gado")
    gasto_gado = cursor.fetchone()["total"] or 0

    cursor.execute("SELECT SUM(valor) as total FROM manutencao")
    gasto_manutencao = cursor.fetchone()["total"] or 0

    gasto_total_geral = gasto_insumos + gasto_gado + gasto_manutencao

    conn.close()

    return render_template(
        "relatorios.html",
        relatorio_engorda=relatorio_fases,
        relatorio_insumos=relatorio_insumos,
        relatorio_gado=relatorio_gado,
        relatorio_manutencao=relatorio_manutencao,
        gasto_insumos=gasto_insumos,
        gasto_gado=gasto_gado,
        gasto_manutencao=gasto_manutencao,
        gasto_total_geral=gasto_total_geral,
    )


# --- ROTA 6: GADO ABATIDO E RELATÓRIO DE RENDIMENTO (/abate) ---
@app.route("/abate", methods=["GET", "POST"])
def gerenciar_abate():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if request.method == "POST":
        fase_id = request.form.get("fase_id")
        data_abate = request.form.get("data_abate")
        peso_vivo_embarque = float(request.form.get("peso_vivo_embarque") or 0)
        peso_total_carcaca = float(request.form.get("peso_total_carcaca") or 0)
        valor_recebido = float(request.form.get("valor_recebido") or 0)
        observacoes = request.form.get("observacoes", "")

        rendimento_carcaca = 0
        if peso_vivo_embarque > 0:
            rendimento_carcaca = (peso_total_carcaca / peso_vivo_embarque) * 100

        cursor.execute("SELECT * FROM fases_lote WHERE id = ?", (fase_id,))
        lote_fase = cursor.fetchone()

        if lote_fase:
            numero_lote = lote_fase["numero_lote"]
            quantidade_cabecas = lote_fase["quantidade_animais"]

            cursor.execute(
                """
                INSERT INTO abate (fase_id, numero_lote, data_abate, quantidade_cabecas, peso_vivo_embarque, peso_total_carcaca, rendimento_carcaca, valor_recebido, observacoes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    fase_id,
                    numero_lote,
                    data_abate,
                    quantidade_cabecas,
                    peso_vivo_embarque,
                    peso_total_carcaca,
                    rendimento_carcaca,
                    valor_recebido,
                    observacoes,
                ),
            )
            
            # Atualiza fase para finalizado
            cursor.execute("UPDATE fases_lote SET status = 'Finalizado', data_saida = ? WHERE id = ?", (data_abate, fase_id))
            cursor.execute("UPDATE gado SET status = 'Vendido' WHERE id = ?", (lote_fase["lote_id"],))
            
            conn.commit()

        conn.close()
        return redirect(url_for("gerenciar_abate"))

    cursor.execute("SELECT * FROM fases_lote WHERE status = 'Ativo' ORDER BY data_entrada DESC")
    fases_ativas = cursor.fetchall()

    cursor.execute("""
        SELECT a.*, f.data_entrada, f.peso_entrada, f.custo_total_insumos, f.etapa,
               g.preco_lote, g.custos_adicionais as custo_compra_extra,
               (g.preco_lote + g.custos_adicionais + f.custo_total_insumos) AS custo_total_producao
        FROM abate a
        JOIN fases_lote f ON a.fase_id = f.id
        JOIN gado g ON f.lote_id = g.id
        ORDER BY a.data_abate DESC
    """)
    historico_abates = cursor.fetchall()

    conn.close()

    return render_template(
        "abate.html",
        lotes_engorda=fases_ativas,
        historico_abates=historico_abates,
    )


# --- ROTA 7: EXPORTAR DADOS EM PDF (/exportar/<tipo>) ---
@app.route("/exportar/<tipo>")
def exportar_dados(tipo):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    response = make_response()
    response.headers['Content-Type'] = 'application/pdf'

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, 
        pagesize=landscape(letter),
        rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30
    )
    elements = []
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'TitleStyle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=18,
        textColor=colors.HexColor('#065f46'),
        spaceAfter=4
    )
    subtitle_style = ParagraphStyle(
        'SubTitleStyle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        textColor=colors.HexColor('#78716c'),
        spaceAfter=15
    )
    cell_style = ParagraphStyle(
        'CellStyle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        textColor=colors.HexColor('#1c1917')
    )

    if tipo == "abate":
        cursor.execute("""
            SELECT a.numero_lote, a.data_abate, a.quantidade_cabecas, a.peso_vivo_embarque, 
                   a.peso_total_carcaca, a.rendimento_carcaca, a.valor_recebido, a.observacoes
            FROM abate a ORDER BY a.data_abate DESC
        """)
        registros = cursor.fetchall()
        
        elements.append(Paragraph("Agropecuária Previato", title_style))
        elements.append(Paragraph("Relatório Oficial de Gado Abatido / Venda Direta", subtitle_style))

        data = [["Lote", "Data Abate", "Cabeças", "Peso Vivo", "Peso Carcaça", "Rend. (%)", "Valor Recebido", "Observações"]]
        
        for r in registros:
            data.append([
                Paragraph(str(r["numero_lote"]), cell_style),
                Paragraph(str(r["data_abate"]), cell_style),
                Paragraph(str(r["quantidade_cabecas"]), cell_style),
                Paragraph(f"{r['peso_vivo_embarque']:.2f} kg", cell_style),
                Paragraph(f"{r['peso_total_carcaca']:.2f} kg", cell_style),
                Paragraph(f"{r['rendimento_carcaca']:.2f}%" if r['rendimento_carcaca'] else "0%", cell_style),
                Paragraph(f"R$ {r['valor_recebido']:.2f}", cell_style),
                Paragraph(str(r["observacoes"] or ""), cell_style)
            ])
        
        filename = "relatorio_abate.pdf"
        col_widths = [65, 75, 55, 70, 75, 65, 85, 185]

    elif tipo == "engorda" or tipo == "fases":
        cursor.execute("""
            SELECT f.numero_lote, f.etapa, f.quantidade_animais, f.data_entrada, f.data_saida, 
                   f.peso_entrada, f.custo_total_insumos,
                   (julianday(COALESCE(f.data_saida, 'now')) - julianday(f.data_entrada)) AS dias
            FROM fases_lote f ORDER BY f.data_entrada DESC
        """)
        registros = cursor.fetchall()

        elements.append(Paragraph("Agropecuária Previato", title_style))
        elements.append(Paragraph("Relatório de Desempenho e Custos Operacionais por Fase (Recria/Engorda)", subtitle_style))

        data = [["Lote", "Etapa", "Animais", "Entrada", "Saída", "Peso Entrada", "Custo Insumos", "Dias", "Custo Diário/Cab"]]
        
        for r in registros:
            dias = int(r["dias"]) if r["dias"] and r["dias"] > 0 else 1
            custo_cab = (r["custo_total_insumos"] / dias) / r["quantidade_animais"] if r["quantidade_animais"] > 0 else 0
            
            data.append([
                Paragraph(str(r["numero_lote"]), cell_style),
                Paragraph(str(r["etapa"]), cell_style),
                Paragraph(str(r["quantidade_animais"]), cell_style),
                Paragraph(str(r["data_entrada"]), cell_style),
                Paragraph(str(r["data_saida"] or "Ativo"), cell_style),
                Paragraph(f"{r['peso_entrada']:.2f} kg", cell_style),
                Paragraph(f"R$ {r['custo_total_insumos']:.2f}", cell_style),
                Paragraph(f"{dias} dias", cell_style),
                Paragraph(f"R$ {custo_cab:.2f}", cell_style)
            ])

        filename = "relatorio_desempenho.pdf"
        col_widths = [65, 60, 55, 70, 70, 75, 85, 55, 85]

    conn.close()

    t = Table(data, colWidths=col_widths)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#047857')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('BOTTOMPADDING', (0,0), (-1,0), 6),
        ('TOPPADDING', (0,0), (-1,0), 6),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f9fafb')]),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#e7e5e4'))
    ]))

    elements.append(t)
    doc.build(elements)

    response.data = buffer.getvalue()
    response.headers['Content-Disposition'] = f'attachment; filename={filename}'
    return response


# --- ROTA 8: DESEMPENHO ZOOTÉCNICO (/desempenho) ---
@app.route("/desempenho")
def desempenho_lotes():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT f.id as fase_id, f.numero_lote, f.etapa, f.quantidade_animais, f.data_entrada, f.data_saida,
               f.peso_entrada, f.custo_total_insumos,
               g.preco_lote, g.custos_adicionais as custo_extra_gado, g.raca,
               (julianday(COALESCE(f.data_saida, 'now')) - julianday(f.data_entrada)) AS dias_confinado,
               ab.peso_total_carcaca, ab.valor_recebido, ab.data_abate
        FROM fases_lote f
        JOIN gado g ON f.lote_id = g.id
        LEFT JOIN abate ab ON ab.fase_id = f.id
        ORDER BY f.data_entrada DESC
    """)
    lotes_desempenho = cursor.fetchall()
    conn.close()

    return render_template("desempenho.html", lotes_desempenho=lotes_desempenho)


if __name__ == "__main__":
    init_db()
    app.run(debug=True)