import streamlit as st
import pandas as pd
from utils import (
    init_session, inject_css, load_json, get_carrito_items, get_carrito_total,
    guardar_pedido, pedido_a_csv, format_precio, load_productos, calcular_margen
)
from map_utils import mapa_sedes, mapa_ruta_envio, distancia_km

st.set_page_config(page_title="Carrito / Checkout", page_icon="📦", layout="wide")
init_session()
inject_css()

st.markdown("# 📦 Carrito y Checkout")

if not st.session_state.usuario:
    st.error("🔒 Debes iniciar sesión para ver tu carrito.")
    st.stop()

# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 1 — CARRITO con st.data_editor
# ══════════════════════════════════════════════════════════════════════════════
items = get_carrito_items()

st.subheader("🛒 Tu Carrito")

if not items:
    st.info("Tu carrito está vacío. Ve al catálogo para agregar productos.")
    st.stop()

productos_db = load_productos()
prod_dict    = {p["id"]: p for p in productos_db}

rows = []
for item in items:
    p = item["producto"]
    rows.append({
        "pid":          p["id"],
        "Producto":     f"{p['imagen']} {p['nombre']}",
        "Categoría":    p["categoria"],
        "Precio unit.": p["precio"],
        "Cantidad":     item["cantidad"],
        "Subtotal":     p["precio"] * item["cantidad"],
        "Stock máx.":   prod_dict[p["id"]]["stock"],
    })

df_carrito = pd.DataFrame(rows)

edited = st.data_editor(
    df_carrito[["Producto", "Categoría", "Precio unit.", "Cantidad", "Subtotal"]],
    use_container_width=True,
    hide_index=True,
    column_config={
        "Producto":     st.column_config.TextColumn(disabled=True),
        "Categoría":    st.column_config.TextColumn(disabled=True),
        "Precio unit.": st.column_config.NumberColumn(format="$ %d", disabled=True),
        "Cantidad":     st.column_config.NumberColumn(min_value=1, step=1,
                            help="Edita la cantidad directamente aquí"),
        "Subtotal":     st.column_config.NumberColumn(format="$ %d", disabled=True),
    },
    key="editor_carrito"
)

# Validar stock
cambios_validos = True
for i, row in edited.iterrows():
    pid       = df_carrito.loc[i, "pid"]
    nueva_qty = int(row["Cantidad"])
    stock_max = df_carrito.loc[i, "Stock máx."]
    nombre    = df_carrito.loc[i, "Producto"]
    if nueva_qty < 1:
        st.error(f"❌ **{nombre}**: cantidad mínima es 1.")
        cambios_validos = False
    elif nueva_qty > stock_max:
        st.error(f"❌ **{nombre}**: solo hay {stock_max} unidades disponibles.")
        cambios_validos = False
    else:
        st.session_state.carrito[pid] = nueva_qty

total_unidades = int(edited["Cantidad"].sum())
total_precio   = sum(
    prod_dict[df_carrito.loc[i, "pid"]]["precio"] * int(edited.loc[i, "Cantidad"])
    for i in edited.index
)
margen_est = calcular_margen(total_precio)

# Métricas
st.divider()
mc1, mc2, mc3, mc4 = st.columns(4)
mc1.metric("🛒 Productos distintos", len(items))
mc2.metric("📦 Total unidades",      total_unidades)
mc3.metric("💰 Total a pagar",       format_precio(total_precio))
mc4.metric("📈 Margen estimado",     format_precio(margen_est), help="40% sobre precio de venta")

col_vaciar, _ = st.columns([1, 4])
with col_vaciar:
    if st.button("🗑️ Vaciar carrito", type="secondary"):
        st.session_state.carrito = {}
        st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 2 — MODO DE ENTREGA
# ══════════════════════════════════════════════════════════════════════════════
st.divider()
st.subheader("🚚 Modo de entrega")

sedes = load_json("sedes.json")

modo = st.radio(
    "¿Cómo quieres recibir tu pedido?",
    ["🏪 Retiro en tienda", "🏠 Envío a domicilio"],
    horizontal=True
)

# ── RETIRO EN TIENDA ──────────────────────────────────────────────────────────
if modo == "🏪 Retiro en tienda":
    sede_nombres    = [s["nombre"] for s in sedes]
    sede_sel_nombre = st.selectbox("Elige tu sucursal", sede_nombres)
    sede_sel        = next(s for s in sedes if s["nombre"] == sede_sel_nombre)

    col_info, col_mapa = st.columns([1, 2])

    with col_info:
        with st.container(border=True):
            st.markdown(f"#### 📍 {sede_sel['nombre']}")
            st.write(f"🗺️ {sede_sel['direccion']}")
            st.write(f"🕐 {sede_sel['horario']}")
            st.write(f"📞 {sede_sel['telefono']}")
            st.success("✅ Retiro sin costo adicional")

    with col_mapa:
        deck = mapa_sedes(sedes, sede_activa_nombre=sede_sel_nombre, zoom=11)
        st.pydeck_chart(deck, use_container_width=True)
        st.caption("🔴 Sede seleccionada  ·  ⚫ Otras sedes  ·  Arrastra para rotar el mapa 3D")

    destino_label = sede_sel_nombre
    costo_envio   = 0
    lat_entrega   = None
    lon_entrega   = None

# ── ENVÍO A DOMICILIO ─────────────────────────────────────────────────────────
else:
    st.markdown("#### 🏠 Datos de entrega")

    col_dir, col_coords = st.columns([2, 1])
    with col_dir:
        direccion_envio = st.text_input(
            "Dirección de entrega",
            placeholder="Ej: Av. Las Flores 456, Depto 3B, Ñuñoa"
        )
    with col_coords:
        st.caption("Coordenadas de tu domicilio (para calcular ruta)")
        lat_envio = st.number_input("Latitud",  value=-33.4569, format="%.4f", key="lat_env")
        lon_envio = st.number_input("Longitud", value=-70.6483, format="%.4f", key="lon_env")

    # Calcular sede de despacho más cercana al domicilio
    from map_utils import sede_mas_cercana
    sede_despacho = sede_mas_cercana(sedes, lat_envio, lon_envio)
    dist_despacho = distancia_km(lat_envio, lon_envio, sede_despacho["lat"], sede_despacho["lon"])
    costo_envio   = 3990 if dist_despacho <= 10 else 5990

    col_info_env, col_mapa_env = st.columns([1, 2])

    with col_info_env:
        with st.container(border=True):
            st.markdown("#### 🏪 Despacha desde")
            st.markdown(f"**{sede_despacho['nombre']}**")
            st.caption(sede_despacho["direccion"])
            st.divider()
            st.markdown("#### 📦 Detalle del envío")
            st.write(f"📏 Distancia estimada: **{dist_despacho:.1f} km**")
            st.write(f"⏱️ Tiempo estimado: **{int(dist_despacho * 4 + 20)}-{int(dist_despacho * 4 + 40)} min**")
            st.write(f"💳 Costo de envío: **{format_precio(costo_envio)}**")
            if dist_despacho <= 10:
                st.success("✅ Zona de despacho express")
            else:
                st.warning("⚠️ Zona de despacho estándar")

    with col_mapa_env:
        deck_ruta = mapa_ruta_envio(
            lat_envio, lon_envio,
            sede_despacho["lat"], sede_despacho["lon"],
            sede_despacho["nombre"]
        )
        st.pydeck_chart(deck_ruta, use_container_width=True)
        st.caption("🔴 Tienda origen  ·  🟣 Tu domicilio  ·  Línea = ruta de envío")

    destino_label = f"Domicilio: {direccion_envio or 'Sin especificar'}"
    lat_entrega   = lat_envio
    lon_entrega   = lon_envio

    # Recalcular total con envío
    total_precio += costo_envio
    st.info(f"💰 Total con envío: **{format_precio(total_precio)}** (incluye {format_precio(costo_envio)} de despacho)")

# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 3 — CONFIRMAR PEDIDO
# ══════════════════════════════════════════════════════════════════════════════
st.divider()
st.subheader("✅ Confirmar Pedido")

col_res, col_btn = st.columns([3, 1])
with col_res:
    with st.container(border=True):
        st.markdown(
            f"**{len(items)} producto(s)** · "
            f"**{total_unidades} unidades** · "
            f"Entrega: **{destino_label}** · "
            f"Total: **{format_precio(total_precio)}**"
        )

with col_btn:
    confirmar = st.button(
        "✅ Confirmar Compra",
        type="primary",
        use_container_width=True,
        disabled=not cambios_validos
    )

if confirmar:
    if not cambios_validos:
        st.error("❌ Corrige los errores de cantidad antes de confirmar.")
    else:
        items_actualizados = get_carrito_items()
        pedido = guardar_pedido(
            usuario=st.session_state.usuario["username"],
            items=items_actualizados,
            sede=destino_label,
            total=total_precio
        )
        st.session_state.historial.append(pedido)
        st.session_state.carrito      = {}
        st.session_state.ultimo_pedido = pedido
        st.success(f"🎉 ¡Pedido #{pedido['id']} confirmado exitosamente!")
        st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 4 — COMPROBANTE
# ══════════════════════════════════════════════════════════════════════════════
if st.session_state.ultimo_pedido:
    pedido = st.session_state.ultimo_pedido
    st.divider()
    st.success(f"🎉 Pedido **#{pedido['id']}** confirmado el **{pedido['fecha']}**")

    total_uds_conf = sum(i["cantidad"] for i in pedido["items"])
    p1, p2, p3 = st.columns(3)
    p1.metric("💰 Total pagado",   format_precio(pedido["total"]))
    p2.metric("📦 Unidades",       total_uds_conf)
    p3.metric("📍 Entrega",        pedido["sede"][:30])

    with st.container(border=True):
        st.markdown("#### 📋 Detalle del pedido")
        for item in pedido["items"]:
            col_n, col_q, col_s = st.columns([4, 1, 2])
            col_n.write(f"• {item['nombre']}")
            col_q.write(f"×{item['cantidad']}")
            col_s.write(f"**{format_precio(item['subtotal'])}**")
        st.divider()
        st.markdown(f"**Total: {format_precio(pedido['total'])}**")

    col_dl, col_clear = st.columns([2, 1])
    with col_dl:
        csv_data = pedido_a_csv(pedido)
        st.download_button(
            label="📥 Descargar comprobante CSV",
            data=csv_data.encode("utf-8"),
            file_name=f"comprobante_pedido_{pedido['id']}.csv",
            mime="text/csv",
            type="primary",
            use_container_width=True
        )
    with col_clear:
        if st.button("✖ Cerrar comprobante", use_container_width=True):
            st.session_state.ultimo_pedido = None
            st.rerun()
