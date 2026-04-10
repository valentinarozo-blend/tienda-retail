import streamlit as st
import pandas as pd
from utils import (
    init_session, inject_css, load_json, load_productos,
    save_productos, format_precio, calcular_margen, get_todos_pedidos
)
from aws_client import aws_status, _aws_disponible
from bedrock_client import analizar_ventas, generar_descripcion_producto

st.set_page_config(page_title="Administrador", page_icon="🔑", layout="wide")
init_session()
inject_css()

st.markdown("# 🔑 Panel de Administrador")

if not st.session_state.usuario:
    st.error("🔒 Debes iniciar sesión.")
    st.stop()

if st.session_state.usuario.get("rol") != "admin":
    st.error("🚫 Acceso restringido. Solo administradores pueden ver esta página.")
    st.stop()

# ── Status AWS ────────────────────────────────────────────────────────────────
aws_on = _aws_disponible()
status = aws_status()

with st.expander("☁️ Estado de servicios AWS", expanded=False):
    s1, s2, s3, s4 = st.columns(4)
    def badge(ok, label):
        cls = "aws-badge-ok" if ok else "aws-badge-off"
        ico = "✅" if ok else "❌"
        return f'<span class="aws-badge {cls}">{ico} {label}</span>'
    s1.markdown(badge(status["cognito"],  "Cognito"),  unsafe_allow_html=True)
    s2.markdown(badge(status["dynamodb"], "DynamoDB"), unsafe_allow_html=True)
    s3.markdown(badge(status["s3"],       "S3"),       unsafe_allow_html=True)
    s4.markdown(badge(status["bedrock"],  "Bedrock"),  unsafe_allow_html=True)
    st.caption(f"Región: `{status['region']}`")

st.divider()

tab_metricas, tab_inventario, tab_pedidos = st.tabs(
    ["📊 Métricas y Ventas", "📦 Inventario", "🧾 Pedidos"]
)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — MÉTRICAS
# ══════════════════════════════════════════════════════════════════════════════
with tab_metricas:
    pedidos   = get_todos_pedidos()
    productos = load_productos()
    usuarios  = load_json("usuarios.json")

    # KPIs globales
    total_ventas   = sum(p["total"] for p in pedidos) if pedidos else 0
    total_pedidos  = len(pedidos)
    total_uds      = sum(i["cantidad"] for p in pedidos for i in p["items"]) if pedidos else 0
    clientes_uniq  = len(set(p["usuario"] for p in pedidos)) if pedidos else 0
    ticket_prom    = total_ventas / total_pedidos if total_pedidos else 0
    margen_total   = calcular_margen(total_ventas)

    st.markdown("#### 📊 KPIs Globales")
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("💰 Ventas totales",   format_precio(total_ventas))
    k2.metric("📦 Pedidos",          total_pedidos)
    k3.metric("📦 Unidades vendidas",total_uds)
    k4.metric("👥 Clientes únicos",  clientes_uniq)
    k5.metric("🎫 Ticket promedio",  format_precio(ticket_prom))
    k6.metric("📈 Margen bruto",     format_precio(margen_total))

    st.divider()

    if not pedidos:
        st.info("📭 Aún no hay pedidos registrados.")
    else:
        col_g1, col_g2 = st.columns(2)

        with col_g1:
            st.markdown("#### 🏪 Ventas por sede")
            ventas_sede = {}
            for p in pedidos:
                ventas_sede[p["sede"]] = ventas_sede.get(p["sede"], 0) + p["total"]
            df_sede = pd.DataFrame(
                list(ventas_sede.items()), columns=["Sede", "Total"]
            ).sort_values("Total", ascending=False)
            st.bar_chart(df_sede.set_index("Sede")["Total"], color="#e94560")

        with col_g2:
            st.markdown("#### 🏷️ Productos más vendidos (unidades)")
            ventas_prod = {}
            for p in pedidos:
                for item in p["items"]:
                    ventas_prod[item["nombre"]] = ventas_prod.get(item["nombre"], 0) + item["cantidad"]
            df_prod = pd.DataFrame(
                list(ventas_prod.items()), columns=["Producto", "Unidades"]
            ).sort_values("Unidades", ascending=False)
            st.bar_chart(df_prod.set_index("Producto")["Unidades"], color="#1a1a2e")

        st.divider()

        # Tabla resumen por sede con margen
        st.markdown("#### 📋 Resumen por sede")
        resumen_sede = []
        for sede, total in ventas_sede.items():
            n_pedidos_sede = sum(1 for p in pedidos if p["sede"] == sede)
            uds_sede = sum(
                i["cantidad"] for p in pedidos if p["sede"] == sede
                for i in p["items"]
            )
            resumen_sede.append({
                "Sede":           sede,
                "Pedidos":        n_pedidos_sede,
                "Unidades":       uds_sede,
                "Ventas":         format_precio(total),
                "Margen est.":    format_precio(calcular_margen(total)),
            })
        st.dataframe(pd.DataFrame(resumen_sede), use_container_width=True, hide_index=True)

    st.divider()
    col_u, col_p, col_s = st.columns(3)
    col_u.metric("👤 Usuarios registrados", len(usuarios))
    col_p.metric("🏷️ Productos en catálogo", len(productos))
    col_s.metric("⚠️ Productos bajo stock",
                 sum(1 for p in productos if p["stock"] <= 5))

    # ── Análisis IA con Nova Pro ──────────────────────────────────────────────
    st.divider()
    st.markdown("#### 🤖 Análisis de ventas con Amazon Nova Pro")
    st.caption("Powered by `amazon.nova-pro-v1:0` vía Amazon Bedrock")

    col_btn_ia, col_info_ia = st.columns([1, 3])
    with col_btn_ia:
        run_analysis = st.button(
            "✨ Generar análisis IA",
            type="primary",
            use_container_width=True,
            disabled=not pedidos
        )
    with col_info_ia:
        if not pedidos:
            st.warning("Necesitas al menos un pedido para generar el análisis.")
        else:
            st.caption(f"Analizará {len(pedidos)} pedido(s) y {len(productos)} producto(s).")

    if run_analysis:
        with st.spinner("🧠 Nova Pro analizando datos de ventas..."):
            analisis = analizar_ventas(pedidos, productos)
        st.session_state["ultimo_analisis"] = analisis

    if "ultimo_analisis" in st.session_state:
        with st.container(border=True):
            st.markdown(st.session_state["ultimo_analisis"])
        st.download_button(
            "📥 Exportar análisis",
            data=st.session_state["ultimo_analisis"].encode("utf-8"),
            file_name="analisis_ventas_nova.txt",
            mime="text/plain",
        )

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — INVENTARIO con st.data_editor
# ══════════════════════════════════════════════════════════════════════════════
with tab_inventario:
    st.markdown("#### 📦 Gestión de Inventario")
    productos = load_productos()

    bajo_stock = [p for p in productos if p["stock"] <= 5]
    sin_stock  = [p for p in productos if p["stock"] == 0]

    if sin_stock:
        st.error(f"🚨 {len(sin_stock)} producto(s) sin stock: {', '.join(p['nombre'] for p in sin_stock)}")
    if bajo_stock:
        st.warning(f"⚠️ {len(bajo_stock)} producto(s) con stock bajo (≤5 uds.)")

    df = pd.DataFrame(productos)
    df_display = df[["id", "nombre", "categoria", "precio", "stock", "imagen"]].copy()
    df_display.columns = ["ID", "Nombre", "Categoría", "Precio", "Stock", "Emoji"]

    edited_df = st.data_editor(
        df_display,
        use_container_width=True,
        num_rows="dynamic",
        hide_index=True,
        column_config={
            "ID":       st.column_config.NumberColumn(disabled=True, width="small"),
            "Nombre":   st.column_config.TextColumn(width="large"),
            "Categoría":st.column_config.SelectboxColumn(
                options=["Ropa", "Calzado", "Accesorios"], width="medium"
            ),
            "Precio":   st.column_config.NumberColumn(
                format="$ %d", min_value=0, step=100, width="medium"
            ),
            "Stock":    st.column_config.NumberColumn(
                min_value=0, step=1, width="small",
                help="Unidades disponibles"
            ),
            "Emoji":    st.column_config.TextColumn(width="small"),
        },
        key="editor_inventario"
    )

    col_save, col_export = st.columns(2)
    with col_save:
        if st.button("💾 Guardar cambios", type="primary", use_container_width=True):
            nuevos = edited_df.rename(columns={
                "ID": "id", "Nombre": "nombre", "Categoría": "categoria",
                "Precio": "precio", "Stock": "stock", "Emoji": "imagen"
            }).to_dict("records")
            errores = []
            for i, p in enumerate(nuevos):
                try:
                    p["id"]     = int(p["id"]) if p.get("id") else i + 1
                    p["precio"] = int(p["precio"])
                    p["stock"]  = int(p["stock"])
                    if not p.get("nombre"):
                        errores.append(f"Fila {i+1}: el nombre no puede estar vacío.")
                except (ValueError, TypeError):
                    errores.append(f"Fila {i+1}: precio o stock inválido.")

            if errores:
                for e in errores:
                    st.error(e)
            else:
                save_productos(nuevos)
                st.success("✅ Inventario guardado correctamente.")
                st.rerun()

    with col_export:
        csv_inv = df_display.to_csv(index=False).encode("utf-8")
        st.download_button(
            "📥 Exportar inventario CSV",
            data=csv_inv,
            file_name="inventario.csv",
            mime="text/csv",
            use_container_width=True
        )

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — PEDIDOS
# ══════════════════════════════════════════════════════════════════════════════
with tab_pedidos:
    st.markdown("#### 🧾 Todos los Pedidos")
    pedidos = get_todos_pedidos()

    if not pedidos:
        st.info("📭 No hay pedidos aún.")
    else:
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            usuarios_pedidos = ["Todos"] + sorted(set(p["usuario"] for p in pedidos))
            filtro_usuario = st.selectbox("👤 Filtrar por usuario", usuarios_pedidos)
        with col_f2:
            sedes_pedidos = ["Todas"] + sorted(set(p["sede"] for p in pedidos))
            filtro_sede = st.selectbox("🏪 Filtrar por sede", sedes_pedidos)

        pedidos_f = pedidos[:]
        if filtro_usuario != "Todos":
            pedidos_f = [p for p in pedidos_f if p["usuario"] == filtro_usuario]
        if filtro_sede != "Todas":
            pedidos_f = [p for p in pedidos_f if p["sede"] == filtro_sede]

        st.caption(f"Mostrando **{len(pedidos_f)}** pedido(s)")

        for pedido in reversed(pedidos_f):
            total_uds = sum(i["cantidad"] for i in pedido["items"])
            with st.expander(
                f"#{pedido['id']}  ·  {pedido['usuario']}  ·  {pedido['fecha']}  ·  {format_precio(pedido['total'])}"
            ):
                pm1, pm2, pm3 = st.columns(3)
                pm1.metric("💰 Total",    format_precio(pedido["total"]))
                pm2.metric("📦 Unidades", total_uds)
                pm3.metric("🏪 Sede",     pedido["sede"])

                st.divider()
                for item in pedido["items"]:
                    c1, c2, c3 = st.columns([4, 1, 2])
                    c1.write(f"• {item['nombre']}")
                    c2.write(f"×{item['cantidad']}")
                    c3.write(f"**{format_precio(item['subtotal'])}**")

        # Exportar
        st.divider()
        rows = []
        for p in pedidos_f:
            for item in p["items"]:
                rows.append({
                    "Pedido ID": p["id"],
                    "Usuario":   p["usuario"],
                    "Fecha":     p["fecha"],
                    "Sede":      p["sede"],
                    "Producto":  item["nombre"],
                    "Cantidad":  item["cantidad"],
                    "Precio Unit.": item["precio_unit"],
                    "Subtotal":  item["subtotal"],
                    "Total Pedido": p["total"],
                    "Margen est.": round(item["subtotal"] * 0.40),
                })
        df_pedidos = pd.DataFrame(rows)

        col_dl, col_prev = st.columns([1, 2])
        with col_dl:
            st.download_button(
                "📥 Exportar pedidos filtrados CSV",
                data=df_pedidos.to_csv(index=False).encode("utf-8"),
                file_name="pedidos_export.csv",
                mime="text/csv",
                type="primary",
                use_container_width=True
            )
        with col_prev:
            with st.expander("👁️ Vista previa del CSV"):
                st.dataframe(df_pedidos.head(10), use_container_width=True, hide_index=True)
