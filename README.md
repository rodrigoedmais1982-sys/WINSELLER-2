# WinSeller — Flask site (sem Streamlit)

## O que faz
- Upload de **Pedidos (CSV)** e **Recebimentos/Income (CSV)**
- Calcula **recebível previsto**: 20% + R$ 4/unidade + **+R$ 8** se "Entrega Direta"
- Conciliação por `order_sn`: **PENDENTE / PARCIAL / LIBERADO / ACIMA_DO_ESPERADO**
- Banco **SQLite** (arquivo `winseller.db`)

## Como rodar local
```bash
python -m venv venv
source venv/bin/activate  # no Windows: venv\Scripts\activate
pip install -r requirements.txt
export FLASK_ENV=production
python app.py  # abre em http://127.0.0.1:5000
```

## Deploy no Render
1. Suba esses arquivos no GitHub (na raiz).
2. No Render → New Web Service → conecte seu repo.
3. Build command: `pip install -r requirements.txt`
4. Start command: `gunicorn app:app --bind 0.0.0.0:$PORT`
5. Ou use o `render.yaml` (Infrastructure as Code).

## CSV esperado
### Pedidos
- Precisamos conseguir extrair: `order_sn`, `item_name`, `unit_price`, `qty`, `metodo_envio`
- O app tenta **mapear automaticamente** os nomes comuns da Shopee (ex.: `ID do pedido`, `Preço acordado`, `Número de produtos pedidos`, `Método de envio`).

### Recebimentos (Income/Lançado)
- Colunas mínimas: `order_sn` e `valor_creditado` (ele soma por pedido).

## Ajustando regras
- Editar os valores em `app.py`: `COMISSAO_PCT=0.20`, `TAXA_FIXA_UN=4.00`, `REPASSE_ENTREGA_DIRETA=8.00`.
