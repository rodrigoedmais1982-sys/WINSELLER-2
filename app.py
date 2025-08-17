import os
from flask import Flask, render_template, request, redirect, url_for, flash
from sqlalchemy import create_engine, text
import pandas as pd

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "devsecret")

DB_URL = os.getenv("DATABASE_URL", "sqlite:///winseller.db")
engine = create_engine(DB_URL, pool_pre_ping=True)

# Regras (ajuste aqui se precisar)
COMISSAO_PCT = 0.20
TAXA_FIXA_UN = 4.00
REPASSE_ENTREGA_DIRETA = 8.00

def init_db():
    with engine.begin() as con:
        con.execute(text("""CREATE TABLE IF NOT EXISTS orders(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_sn TEXT,
            item_name TEXT,
            unit_price REAL,
            qty INTEGER,
            metodo_envio TEXT,
            bruto REAL,
            comissao REAL,
            taxa_fixa REAL,
            repasse REAL,
            esperado REAL
        )"""))
        con.execute(text("""CREATE TABLE IF NOT EXISTS releases(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_sn TEXT,
            valor_creditado REAL,
            batch TEXT,
            data_release TEXT
        )"""))
init_db()

# mapeamentos de nomes comuns -> colunas internas
ORDER_COL_CANDIDATES = {
    "order_sn": ["order_sn", "id do pedido", "pedido", "order id", "order number", "order no"],
    "item_name": ["item_name", "nome do produto", "produto", "item"],
    "unit_price": ["unit_price", "preço acordado", "preco acordado", "price", "unit price", "preço", "valor do produto"],
    "qty": ["qty", "quantidade", "qtd", "número de produtos pedidos", "numero de produtos pedidos", "quantity"],
    "metodo_envio": ["metodo_envio", "método de envio", "shipping method", "envio", "logística"]
}
RELEASE_COL_CANDIDATES = {
    "order_sn": ["order_sn", "id do pedido", "pedido", "order id", "order number", "order no"],
    "valor_creditado": ["valor_creditado", "valor", "valor lançado", "valor lancado", "amount", "credit", "released"],
    "batch": ["batch", "lote", "ciclo", "settlement id"],
    "data_release": ["data_release", "data", "release date", "payment date"]
}

def auto_map_columns(df, candidates):
    cols = {}
    lower_map = {c.lower(): c for c in df.columns}
    for target, options in candidates.items():
        found = None
        for opt in options:
            if opt in lower_map:
                found = lower_map[opt]
                break
        if not found:
            # tenta match por aproximação simples
            for lc, orig in lower_map.items():
                if opt_like(lc, options):
                    found = orig
                    break
        cols[target] = found
    return cols

def opt_like(name, options):
    # aproximações simples
    for opt in options:
        if opt.replace(" ", "") in name.replace(" ", ""):
            return True
    return False

def compute_expected(row):
    bruto = (row["unit_price"] or 0) * (row["qty"] or 0)
    comissao = bruto * COMISSAO_PCT
    taxa_fixa = (row["qty"] or 0) * TAXA_FIXA_UN
    repasse = REPASSE_ENTREGA_DIRETA if str(row.get("metodo_envio","")).strip().lower() in ["entrega direta","entregadireta"] else 0.0
    esperado = bruto - comissao - taxa_fixa + repasse
    return bruto, comissao, taxa_fixa, repasse, esperado

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/upload/orders", methods=["GET","POST"])
def upload_orders():
    if request.method == "POST":
        file = request.files.get("file")
        if not file or file.filename == "":
            flash("Selecione um CSV de pedidos.", "warning")
            return redirect(request.url)
        try:
            df = pd.read_csv(file, encoding="utf-8", sep=None, engine="python")
        except Exception:
            file.seek(0)
            df = pd.read_csv(file, sep=";", encoding_errors="ignore", engine="python")
        colmap = auto_map_columns(df, ORDER_COL_CANDIDATES)
        if not colmap["order_sn"] or not colmap["unit_price"] or not colmap["qty"]:
            flash("Não consegui mapear as colunas principais (order_sn, unit_price, qty). Verifique o cabeçalho.", "danger")
            return redirect(request.url)

        rows = []
        for _,r in df.iterrows():
            row = {
                "order_sn": str(r.get(colmap["order_sn"])) if colmap["order_sn"] else "",
                "item_name": str(r.get(colmap["item_name"])) if colmap["item_name"] else "",
                "unit_price": float(pd.to_numeric(r.get(colmap["unit_price"]), errors="coerce")) if colmap["unit_price"] else 0.0,
                "qty": int(pd.to_numeric(r.get(colmap["qty"]), errors="coerce")) if colmap["qty"] else 0,
                "metodo_envio": str(r.get(colmap["metodo_envio"])) if colmap["metodo_envio"] else "",
            }
            bruto, comissao, taxa_fixa, repasse, esperado = compute_expected(row)
            row.update({"bruto": bruto, "comissao": comissao, "taxa_fixa": taxa_fixa, "repasse": repasse, "esperado": esperado})
            rows.append(row)

        if rows:
            with engine.begin() as con:
                con.execute(text("""DELETE FROM orders"""))
                con.execute(text("""
                    INSERT INTO orders(order_sn,item_name,unit_price,qty,metodo_envio,bruto,comissao,taxa_fixa,repasse,esperado)
                    VALUES(:order_sn,:item_name,:unit_price,:qty,:metodo_envio,:bruto,:comissao,:taxa_fixa,:repasse,:esperado)
                """), rows)
            flash(f"Importei {len(rows)} linhas de pedidos.", "success")
            return redirect(url_for("report"))
        flash("Nenhuma linha válida encontrada.", "warning")
        return redirect(request.url)
    return render_template("upload.html", kind="Pedidos (CSV)")

@app.route("/upload/releases", methods=["GET","POST"])
def upload_releases():
    if request.method == "POST":
        file = request.files.get("file")
        if not file or file.filename == "":
            flash("Selecione um CSV de recebimentos.", "warning")
            return redirect(request.url)
        try:
            df = pd.read_csv(file, encoding="utf-8", sep=None, engine="python")
        except Exception:
            file.seek(0)
            df = pd.read_csv(file, sep=";", encoding_errors="ignore", engine="python")
        colmap = auto_map_columns(df, RELEASE_COL_CANDIDATES)
        if not colmap["order_sn"] or not colmap["valor_creditado"]:
            flash("Não consegui mapear as colunas principais (order_sn, valor_creditado). Verifique o cabeçalho.", "danger")
            return redirect(request.url)

        rows = []
        for _,r in df.iterrows():
            rows.append({
                "order_sn": str(r.get(colmap["order_sn"])),
                "valor_creditado": float(pd.to_numeric(r.get(colmap["valor_creditado"]), errors="coerce")),
                "batch": str(r.get(colmap["batch"])) if colmap["batch"] else None,
                "data_release": str(r.get(colmap["data_release"])) if colmap["data_release"] else None
            })
        if rows:
            with engine.begin() as con:
                con.execute(text("""DELETE FROM releases"""))
                con.execute(text("""
                    INSERT INTO releases(order_sn,valor_creditado,batch,data_release)
                    VALUES(:order_sn,:valor_creditado,:batch,:data_release)
                """), rows)
            flash(f"Importei {len(rows)} lançamentos de recebimentos.", "success")
            return redirect(url_for("report"))
        flash("Nenhuma linha válida encontrada.", "warning")
        return redirect(request.url)
    return render_template("upload.html", kind="Recebimentos (CSV)")

@app.route("/report")
def report():
    with engine.begin() as con:
        df_orders = pd.read_sql("SELECT * FROM orders", con)
        df_rels = pd.read_sql("SELECT order_sn, SUM(valor_creditado) AS liberado FROM releases GROUP BY order_sn", con)
    if df_orders.empty:
        flash("Suba primeiro os Pedidos (CSV).", "info")
        return redirect(url_for("upload_orders"))
    conc = df_orders.merge(df_rels, on="order_sn", how="left")
    conc["liberado"] = conc["liberado"].fillna(0.0)
    conc["delta"] = conc["liberado"] - conc["esperado"]

    def status_row(row):
        exp = round(float(row["esperado"]),2)
        lib = round(float(row["liberado"]),2)
        if lib == 0: return "PENDENTE"
        if abs(lib-exp) <= 0.01: return "LIBERADO"
        if 0 < lib < exp - 0.01: return "PARCIAL"
        if lib > exp + 0.01: return "ACIMA_DO_ESPERADO"
        return "VERIFICAR"
    conc["status"] = conc.apply(status_row, axis=1)

    # KPIs
    kpis = {
        "pedidos": int(conc["order_sn"].nunique()),
        "bruto": float(conc["bruto"].sum()),
        "esperado": float(conc["esperado"].sum()),
        "liberado": float(conc["liberado"].sum()),
        "delta": float(conc["delta"].sum())
    }

    # tabela ordenada
    conc = conc[["order_sn","item_name","unit_price","qty","metodo_envio","bruto","comissao","taxa_fixa","repasse","esperado","liberado","delta","status"]]
    conc = conc.sort_values(["status","order_sn"])

    # render
    return render_template("report.html", kpis=kpis, rows=conc.to_dict(orient="records"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
