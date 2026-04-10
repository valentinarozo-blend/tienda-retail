import streamlit as st
import pandas as pd
from utils import (
    init_session, inject_css, format_precio,
    pedido_a_csv, calcular_margen, get_pedidos_usuario
)
from aws_client import s3_listar_comprobantes, s3_url_comprobante, _aws_disponible

st.set_page_config(page_title="Mis Pedidos", page_icon="📋", layout="wide")
init_session()
inject_css()

st.markdown("# 📋 Mis Pedidos")

if not st.session_state.usuario:
    st.error("🔒 Debes iniciar sesión para ver tu historial.")
    st.stop()

usuario_actual = st.session_state.usuario["username"]
aws_on         = _aws_disponible()

# Badge de fuente de datos
if aws_on:
    st.markdown('<span class="aws-badge aws-badge-ok">☁️ Datos desde DynamoDB + S3</span>', unsafe_allow_html=True)
else:
    st.markdown('<span class="aws-badge aws-badge-off">💾 Datos locales</span>', unsafe_allow_html=True)
st.write("")

mis_pedidos = get_pedidos_usuario(usuario_actual)

if not mis_pedidos:
    st.info("📭 Aún no tienes pedidos. ¡Ve al catálogo y realiza tu primera compra!")
    st.stop()

# ── Métricas globales ─────────────────────────────────────────────────────────
total_gastado  = sum(p["total"] for p in mis_pedidos)
total_unidades = sum(i["cantidad"] for p in mis_pedidos for i in p["items"])
margen_total   = calcular_margen(total_gastado)
ticket_prom    = total_gastado / len(mis_pedidos)

col1, col2, col3, col4 = st.columns(4)
col1.metric("📦 Pedidos realizados", len(mis_pedidos))
col2.metric("💰 Total gastado",      format_precio(total_gastado))
col3.metric("📦 Unidades compradas", total_unidades)
col4.metric("🎫 Ticket promedio",    format_precio(ticket_prom))

st.divider()

# ── Gráfico ───────────────────────────────────────────────────────────────────
if len(mis_pedidos) > 1:
    df_hist = pd.DataFrame([
        {"Pedido": f"#{p['id']} {p['fecha'][:10]}", "Total": p["total"]}
        for p in mis_pedidos
    ])
    st.markdown("#### 📈 Gasto por pedido")
    st.bar_chart(df_hist.set_index("Pedido")["Total"], color="#e94560")
    st.divider()

# ── Lista de pedidos ──────────────────────────────────────────────────────────
st.markdown(f"#### Mostrando {len(mis_pedidos)} pedido(s)")

for pedido in reversed(mis_pedidos):
    total_uds = sum(i["cantidad"] for i in pedido["items"])
    margen_p  = calcular_margen(pedido["total"])

    with st.expander(
        f"📦 Pedido #{pedido['id']}  ·  {pedido['fecha']}  ·  "
        f"{format_precio(pedido['total'])}  ·  📍 {pedido['sede']}"
    ):
        pm1, pm2, pm3 = st.columns(3)
        pm1.metric("💰 Total",       format_precio(pedido["total"]))
        pm2.metric("📦 Unidades",    total_uds)
        pm3.metric("📈 Margen est.", format_precio(margen_p))

        st.divider()
        col_det, col_acc = st.columns([3, 1])

        with col_det:
            for item in pedido["items"]:
                c1, c2, c3 = st.columns([4, 1, 2])
                c1.write(f"• {item['nombre']}")
                c2.write(f"×{item['cantidad']}")
                c3.write(f"**{format_precio(item['subtotal'])}**")

        with col_acc:
            csv_data = pedido_a_csv(pedido)

            # Si hay URL de S3, mostrar link; si no, descarga local
            if pedido.get("s3_url"):
                st.markdown(
                    f'<a href="{pedido["s3_url"]}" target="_blank">'
                    f'<button style="background:linear-gradient(135deg,#e94560,#c23152);'
                    f'color:white;border:none;border-radius:8px;padding:8px 16px;'
                    f'font-weight:600;cursor:pointer;width:100%">'
                    f'☁️ Descargar desde S3</button></a>',
                    unsafe_allow_html=True
                )
            else:
                st.download_button(
                    label="📥 Comprobante CSV",
                    data=csv_data.encode("utf-8"),
                    file_name=f"comprobante_pedido_{pedido['id']}.csv",
                    mime="text/csv",
                    type="primary",
                    use_container_width=True,
                    key=f"dl_{pedido['id']}"
                )

# ── Comprobantes en S3 ────────────────────────────────────────────────────────
if aws_on:
    st.divider()
    st.markdown("#### ☁️ Comprobantes guardados en S3")
    comprobantes = s3_listar_comprobantes(usuario_actual)
    if comprobantes:
        for c in comprobantes:
            col_k, col_f, col_s, col_dl = st.columns([4, 2, 1, 1])
            col_k.write(c["key"].split("/")[-1])
            col_f.caption(c["fecha"])
            col_s.caption(c["size"])
            url = s3_url_comprobante(c["key"])
            if url:
                col_dl.markdown(
                    f'<a href="{url}" target="_blank">📥 Descargar</a>',
                    unsafe_allow_html=True
                )
    else:
        st.caption("No hay comprobantes en S3 aún.")

# ── Exportar historial completo ───────────────────────────────────────────────
st.divider()
rows = []
for p in mis_pedidos:
    for item in p["items"]:
        rows.append({
            "Pedido ID":    p["id"],
            "Fecha":        p["fecha"],
            "Sede":         p["sede"],
            "Producto":     item["nombre"],
            "Cantidad":     item["cantidad"],
            "Precio Unit.": item["precio_unit"],
            "Subtotal":     item["subtotal"],
            "Total Pedido": p["total"],
        })

df_export = pd.DataFrame(rows)
st.download_button(
    label="📥 Exportar historial completo CSV",
    data=df_export.to_csv(index=False).encode("utf-8"),
    file_name=f"historial_{usuario_actual}.csv",
    mime="text/csv",
)
