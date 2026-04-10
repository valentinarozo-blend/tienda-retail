import streamlit as st
from utils import init_session, inject_css, load_productos, format_precio, get_carrito_items
from bedrock_client import recomendar_productos

st.set_page_config(page_title="Catálogo", page_icon="🛒", layout="wide")
init_session()
inject_css()

st.markdown("# 🛒 Catálogo de Productos")

if not st.session_state.usuario:
    st.warning("⚠️ Inicia sesión para agregar productos al carrito.")

productos = load_productos()

# ── Filtros ───────────────────────────────────────────────────────────────────
with st.container(border=True):
    col_busq, col_cat, col_orden, col_stock = st.columns([3, 2, 2, 1])
    with col_busq:
        busqueda = st.text_input("🔍 Buscar", placeholder="Camiseta, zapatillas...")
    with col_cat:
        categorias = ["Todas"] + sorted(set(p["categoria"] for p in productos))
        categoria_sel = st.selectbox("📂 Categoría", categorias)
    with col_orden:
        orden = st.selectbox("↕️ Ordenar", ["Nombre A-Z", "Precio ↑", "Precio ↓", "Mayor stock"])
    with col_stock:
        solo_stock = st.checkbox("Solo en stock", value=True)

# Aplicar filtros
filtrados = productos[:]
if busqueda:
    filtrados = [p for p in filtrados if busqueda.lower() in p["nombre"].lower()]
if categoria_sel != "Todas":
    filtrados = [p for p in filtrados if p["categoria"] == categoria_sel]
if solo_stock:
    filtrados = [p for p in filtrados if p["stock"] > 0]

orden_map = {
    "Nombre A-Z": (lambda x: x["nombre"], False),
    "Precio ↑":   (lambda x: x["precio"], False),
    "Precio ↓":   (lambda x: x["precio"], True),
    "Mayor stock":(lambda x: x["stock"],  True),
}
key_fn, rev = orden_map[orden]
filtrados.sort(key=key_fn, reverse=rev)

# ── Resumen de filtros ────────────────────────────────────────────────────────
col_info, col_carrito = st.columns([3, 1])
with col_info:
    st.caption(f"Mostrando **{len(filtrados)}** de {len(productos)} productos")
with col_carrito:
    n_items = sum(st.session_state.carrito.values())
    if n_items:
        st.markdown(
            f'<div class="cart-badge" style="float:right">🛒 {n_items} en carrito</div>',
            unsafe_allow_html=True
        )

st.divider()

# ── Grid de productos ─────────────────────────────────────────────────────────
if not filtrados:
    st.info("😕 No se encontraron productos con esos filtros.")
else:
    cols = st.columns(3)
    for i, prod in enumerate(filtrados):
        pid = prod["id"]
        en_carrito = st.session_state.carrito.get(pid, 0)

        with cols[i % 3]:
            with st.container(border=True):
                # Emoji grande + nombre
                col_em, col_nm = st.columns([1, 3])
                with col_em:
                    st.markdown(f"<div style='font-size:3rem;text-align:center'>{prod['imagen']}</div>",
                                unsafe_allow_html=True)
                with col_nm:
                    st.markdown(f"**{prod['nombre']}**")
                    st.caption(f"📂 {prod['categoria']}")
                    st.markdown(
                        f"<span style='font-size:1.3rem;font-weight:700;color:#e94560'>"
                        f"{format_precio(prod['precio'])}</span>",
                        unsafe_allow_html=True
                    )

                # Badge stock
                if prod["stock"] > 10:
                    st.success(f"✅ Stock disponible: {prod['stock']} uds.")
                elif prod["stock"] > 0:
                    st.warning(f"⚠️ Últimas {prod['stock']} unidades")
                else:
                    st.error("❌ Sin stock")

                # Badge "en carrito"
                if en_carrito > 0:
                    st.markdown(
                        f'<div class="cart-badge" style="font-size:0.75rem;margin-bottom:6px">'
                        f'✓ {en_carrito} en carrito</div>',
                        unsafe_allow_html=True
                    )

                # Controles
                if st.session_state.usuario and prod["stock"] > 0:
                    col_qty, col_btn = st.columns([2, 3])
                    with col_qty:
                        cantidad = st.number_input(
                            "Cant.", min_value=1, max_value=prod["stock"],
                            value=max(1, en_carrito),
                            key=f"qty_{pid}", label_visibility="collapsed"
                        )
                    with col_btn:
                        label = "🔄 Actualizar" if en_carrito > 0 else "🛒 Agregar"
                        if st.button(label, key=f"add_{pid}", use_container_width=True, type="primary"):
                            st.session_state.carrito[pid] = cantidad
                            st.success(f"✅ **{prod['nombre']}** agregado al carrito")
                            st.rerun()

                    if en_carrito > 0:
                        if st.button("🗑️ Quitar", key=f"rm_{pid}", use_container_width=True):
                            del st.session_state.carrito[pid]
                            st.rerun()

                elif not st.session_state.usuario:
                    st.button("🔒 Inicia sesión para comprar", key=f"lock_{pid}",
                              disabled=True, use_container_width=True)

# ── Banner carrito ────────────────────────────────────────────────────────────
if st.session_state.carrito:
    from utils import get_carrito_total
    total = get_carrito_total()
    st.divider()
    st.success(
        f"🛒 Tienes **{sum(st.session_state.carrito.values())} producto(s)** "
        f"en tu carrito · Total: **{format_precio(total)}** · "
        f"Ve a **Carrito** para finalizar tu compra."
    )

# ── Recomendador Bedrock ──────────────────────────────────────────────────────
if st.session_state.usuario and st.session_state.carrito:
    st.divider()
    st.markdown("### ✨ Recomendado para ti")
    st.caption("Basado en tu carrito actual · Powered by Amazon Bedrock")

    if "recomendaciones" not in st.session_state:
        st.session_state.recomendaciones = []
    if "recs_carrito_hash" not in st.session_state:
        st.session_state.recs_carrito_hash = None

    carrito_hash = str(sorted(st.session_state.carrito.items()))

    col_btn, col_info = st.columns([1, 3])
    with col_btn:
        if st.button("🤖 Obtener recomendaciones", type="primary", use_container_width=True):
            with st.spinner("Consultando Amazon Bedrock..."):
                items_carrito = get_carrito_items()
                recs = recomendar_productos(items_carrito, productos, n=3)
                st.session_state.recomendaciones = recs
                st.session_state.recs_carrito_hash = carrito_hash
            if not recs:
                st.warning("No se pudieron obtener recomendaciones. Verifica las credenciales AWS.")
    with col_info:
        if st.session_state.recs_carrito_hash != carrito_hash and st.session_state.recomendaciones:
            st.caption("⚠️ Tu carrito cambió. Actualiza las recomendaciones.")

    if st.session_state.recomendaciones:
        prod_dict_all = {p["id"]: p for p in productos}
        rec_cols = st.columns(len(st.session_state.recomendaciones))
        for col, rec in zip(rec_cols, st.session_state.recomendaciones):
            pid = rec.get("id")
            prod = prod_dict_all.get(pid)
            if not prod:
                continue
            with col:
                with st.container(border=True):
                    st.markdown(
                        f"<div style='font-size:2.5rem;text-align:center'>{prod['imagen']}</div>",
                        unsafe_allow_html=True
                    )
                    st.markdown(f"**{prod['nombre']}**")
                    st.caption(f"📂 {prod['categoria']}")
                    st.markdown(
                        f"<span style='color:#e94560;font-weight:700'>{format_precio(prod['precio'])}</span>",
                        unsafe_allow_html=True
                    )
                    st.info(f"💡 {rec.get('razon', '')}")
                    if st.session_state.usuario and prod["stock"] > 0:
                        if st.button("🛒 Agregar", key=f"rec_add_{pid}", use_container_width=True, type="primary"):
                            st.session_state.carrito[pid] = st.session_state.carrito.get(pid, 0) + 1
                            st.success(f"✅ **{prod['nombre']}** agregado")
                            st.rerun()
