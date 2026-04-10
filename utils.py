"""
utils.py
────────
Capa de datos unificada con fallback automático:
  AWS disponible  → Cognito / DynamoDB / S3
  Sin credenciales → archivos locales (data/*.json / data/productos.csv)
"""

import json
import csv
import os
import streamlit as st
from datetime import datetime

DATA_DIR    = "data"
MARGEN_COSTO = 0.60   # 60% costo → 40% margen bruto estimado


# ── Helpers de archivos locales ───────────────────────────────────────────────

def load_json(filename):
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(filename, data):
    path = os.path.join(DATA_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_productos_local():
    path = os.path.join(DATA_DIR, "productos.csv")
    productos = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            row["precio"] = int(row["precio"])
            row["stock"]  = int(row["stock"])
            row["id"]     = int(row["id"])
            productos.append(row)
    return productos

def save_productos_local(productos):
    path = os.path.join(DATA_DIR, "productos.csv")
    fieldnames = ["id", "nombre", "categoria", "precio", "stock", "imagen"]
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(productos)


# ── Capa unificada con fallback ───────────────────────────────────────────────

def load_productos():
    """Lee productos: DynamoDB si está disponible, CSV local si no."""
    try:
        from aws_client import dynamo_get_productos
        productos = dynamo_get_productos()
        if productos:
            return productos
    except Exception:
        pass
    return load_productos_local()

def save_productos(productos):
    """Guarda productos: DynamoDB + CSV local."""
    save_productos_local(productos)
    try:
        from aws_client import dynamo_guardar_productos
        dynamo_guardar_productos(productos)
    except Exception:
        pass

def get_pedidos_usuario(username: str) -> list:
    """Lee pedidos del usuario: DynamoDB si disponible, JSON local si no."""
    try:
        from aws_client import dynamo_get_pedidos_usuario
        pedidos = dynamo_get_pedidos_usuario(username)
        if pedidos:
            return sorted(pedidos, key=lambda p: p["id"])
    except Exception:
        pass
    todos = load_json("pedidos.json")
    return [p for p in todos if p["usuario"] == username]

def get_todos_pedidos() -> list:
    """Lee todos los pedidos: DynamoDB si disponible, JSON local si no."""
    try:
        from aws_client import dynamo_get_todos_pedidos
        pedidos = dynamo_get_todos_pedidos()
        if pedidos:
            return sorted(pedidos, key=lambda p: int(p["id"]))
    except Exception:
        pass
    return load_json("pedidos.json")


# ── Formateo ──────────────────────────────────────────────────────────────────

def format_precio(precio):
    return f"${precio:,.0f}".replace(",", ".")

def calcular_margen(total_ventas):
    return total_ventas * (1 - MARGEN_COSTO)


# ── Sesión ────────────────────────────────────────────────────────────────────

def init_session():
    defaults = {
        "usuario":       None,
        "carrito":       {},
        "historial":     [],
        "ultimo_pedido": None,
        "aws_mode":      False,   # True cuando Cognito está activo
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


# ── Carrito ───────────────────────────────────────────────────────────────────

def get_carrito_total():
    productos = load_productos()
    prod_dict = {p["id"]: p for p in productos}
    return sum(
        prod_dict[pid]["precio"] * qty
        for pid, qty in st.session_state.carrito.items()
        if pid in prod_dict
    )

def get_carrito_items():
    productos = load_productos()
    prod_dict = {p["id"]: p for p in productos}
    return [
        {"producto": prod_dict[pid], "cantidad": qty}
        for pid, qty in st.session_state.carrito.items()
        if pid in prod_dict
    ]


# ── Pedidos ───────────────────────────────────────────────────────────────────

def guardar_pedido(usuario, items, sede, total):
    # Calcular ID
    todos = load_json("pedidos.json")
    pedido_id = len(todos) + 1

    pedido = {
        "id":     pedido_id,
        "usuario": usuario,
        "fecha":  datetime.now().strftime("%Y-%m-%d %H:%M"),
        "items":  [
            {
                "nombre":      i["producto"]["nombre"],
                "cantidad":    i["cantidad"],
                "precio_unit": i["producto"]["precio"],
                "subtotal":    i["producto"]["precio"] * i["cantidad"],
            }
            for i in items
        ],
        "sede":  sede,
        "total": total,
    }

    # Guardar local
    todos.append(pedido)
    save_json("pedidos.json", todos)

    # Guardar en DynamoDB
    try:
        from aws_client import dynamo_guardar_pedido
        dynamo_guardar_pedido(pedido)
    except Exception:
        pass

    # Actualizar stock
    productos = load_productos()
    for item in items:
        for p in productos:
            if p["id"] == item["producto"]["id"]:
                p["stock"] = max(0, p["stock"] - item["cantidad"])
    save_productos(productos)

    # Subir comprobante a S3
    try:
        from aws_client import s3_subir_comprobante
        csv_str = pedido_a_csv(pedido)
        resultado = s3_subir_comprobante(pedido_id, csv_str, usuario)
        if resultado["ok"]:
            pedido["s3_url"] = resultado["url"]
    except Exception:
        pass

    return pedido


# ── Comprobante CSV ───────────────────────────────────────────────────────────

def pedido_a_csv(pedido):
    lines = [
        "COMPROBANTE DE PEDIDO",
        f"Pedido N°:,{pedido['id']}",
        f"Fecha:,{pedido['fecha']}",
        f"Cliente:,{pedido['usuario']}",
        f"Entrega:,{pedido['sede']}",
        "",
        "Producto,Cantidad,Precio Unit.,Subtotal",
    ]
    for item in pedido["items"]:
        lines.append(
            f"{item['nombre']},{item['cantidad']},"
            f"{format_precio(item['precio_unit'])},{format_precio(item['subtotal'])}"
        )
    lines += [
        "",
        f",,TOTAL,{format_precio(pedido['total'])}",
        f",,Margen estimado (40%),{format_precio(pedido['total'] * 0.40)}",
    ]
    return "\n".join(lines)


# ── CSS global ────────────────────────────────────────────────────────────────

GLOBAL_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #1a1a2e 0%, #16213e 60%, #0f3460 100%);
}
section[data-testid="stSidebar"] * { color: #e0e0e0 !important; }
section[data-testid="stSidebar"] .stButton button {
    background: rgba(255,255,255,0.1) !important;
    border: 1px solid rgba(255,255,255,0.2) !important;
    color: white !important;
    border-radius: 8px !important;
}
section[data-testid="stSidebar"] .stButton button:hover {
    background: rgba(255,255,255,0.2) !important;
}
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #e94560, #c23152) !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    transition: transform 0.15s, box-shadow 0.15s !important;
}
.stButton > button[kind="primary"]:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 15px rgba(233,69,96,0.4) !important;
}
[data-testid="stMetric"] {
    background: white;
    border: 1px solid #f0f0f0;
    border-radius: 12px;
    padding: 16px 20px !important;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}
[data-testid="stMetricLabel"] { font-size: 0.78rem !important; color: #888 !important; font-weight: 500 !important; }
[data-testid="stMetricValue"] { font-size: 1.6rem !important; font-weight: 700 !important; color: #1a1a2e !important; }
.stTabs [data-baseweb="tab-list"] {
    gap: 8px; background: #f8f9fa; padding: 6px; border-radius: 12px;
}
.stTabs [data-baseweb="tab"] {
    border-radius: 8px !important; font-weight: 500 !important; padding: 8px 20px !important;
}
.stTabs [aria-selected="true"] {
    background: white !important; box-shadow: 0 2px 8px rgba(0,0,0,0.1) !important;
}
.stTextInput input, .stNumberInput input {
    border-radius: 8px !important; border: 1.5px solid #e0e0e0 !important;
}
hr { border-color: #f0f0f0 !important; }
.cart-badge {
    background: linear-gradient(135deg, #e94560, #c23152);
    color: white; border-radius: 20px; padding: 4px 12px;
    font-size: 0.85rem; font-weight: 600; display: inline-block;
}
.hero-banner {
    background: linear-gradient(135deg, #1a1a2e 0%, #e94560 100%);
    border-radius: 20px; padding: 40px; color: white; margin-bottom: 24px;
}
.aws-badge {
    display: inline-flex; align-items: center; gap: 6px;
    background: #232f3e; color: #ff9900; border-radius: 6px;
    padding: 3px 10px; font-size: 0.75rem; font-weight: 600;
}
.aws-badge-ok   { background: #0d6e3f; color: #4ade80; }
.aws-badge-off  { background: #3d1a1a; color: #f87171; }
</style>
"""

def inject_css():
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)
