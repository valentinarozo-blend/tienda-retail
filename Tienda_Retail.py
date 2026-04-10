import streamlit as st
from utils import init_session, inject_css, load_productos, load_json, format_precio, get_carrito_total
from map_utils import mapa_sede_cercana, distancia_km

st.set_page_config(
    page_title="Tienda Retail",
    page_icon="🛍️",
    layout="wide",
    initial_sidebar_state="expanded"
)

init_session()
inject_css()

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🛍️ Tienda Retail")
    st.divider()

    if st.session_state.usuario:
        u = st.session_state.usuario
        rol_badge = "🔑 Admin" if u.get("rol") == "admin" else "👤 Cliente"
        st.markdown(f"**{u['nombre']}**  \n`{rol_badge}`")
        st.caption(f"📧 {u['email']}")
        st.divider()

        n_items = sum(st.session_state.carrito.values())
        total_carrito = get_carrito_total()
        if n_items > 0:
            st.markdown(
                f'<div class="cart-badge">🛒 {n_items} ítem(s) · {format_precio(total_carrito)}</div>',
                unsafe_allow_html=True
            )
            st.write("")

        if st.button("🚪 Cerrar sesión", use_container_width=True):
            st.session_state.usuario = None
            st.session_state.carrito = {}
            st.session_state.ultimo_pedido = None
            st.rerun()
    else:
        st.info("👈 Inicia sesión para comprar")

    st.divider()
    st.caption("v1.0 · Tienda Retail Interactiva")

# ── Hero ──────────────────────────────────────────────────────────────────────
if st.session_state.usuario:
    nombre = st.session_state.usuario["nombre"]
    st.markdown(
        f"""<div class="hero-banner">
            <h1 style="margin:0;font-size:2rem;">¡Hola, {nombre}! 👋</h1>
            <p style="margin:8px 0 0;opacity:0.85;font-size:1.1rem;">
                Explora nuestro catálogo y encuentra lo que buscas.
            </p>
        </div>""",
        unsafe_allow_html=True
    )
else:
    st.markdown(
        """<div class="hero-banner">
            <h1 style="margin:0;font-size:2.2rem;">🛍️ Tienda Retail Interactiva</h1>
            <p style="margin:8px 0 0;opacity:0.85;font-size:1.1rem;">
                Moda y accesorios con la mejor selección. Inicia sesión para comenzar.
            </p>
        </div>""",
        unsafe_allow_html=True
    )

# ── Stats rápidas ─────────────────────────────────────────────────────────────
productos  = load_productos()
categorias = set(p["categoria"] for p in productos)
en_stock   = sum(1 for p in productos if p["stock"] > 0)

col1, col2, col3, col4 = st.columns(4)
col1.metric("🏷️ Productos",   len(productos))
col2.metric("📂 Categorías",  len(categorias))
col3.metric("✅ En stock",    en_stock)
col4.metric("🏪 Sucursales",  4)

st.divider()

# ── Cards de navegación ───────────────────────────────────────────────────────
c1, c2, c3, c4 = st.columns(4)
with c1:
    with st.container(border=True):
        st.markdown("### 👤 Mi Cuenta")
        st.caption("Registro, login y perfil de usuario")
with c2:
    with st.container(border=True):
        st.markdown("### 🛒 Catálogo")
        st.caption("Filtra y busca entre todos los productos")
with c3:
    with st.container(border=True):
        st.markdown("### 📦 Carrito")
        st.caption("Revisa tu selección y confirma el pedido")
with c4:
    with st.container(border=True):
        st.markdown("### 📋 Historial")
        st.caption("Tus compras anteriores y comprobantes")

if not st.session_state.usuario:
    st.warning("👈 Ve a **Registro** en el menú lateral para comenzar a comprar.")

# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN — SEDE MÁS CERCANA
# ══════════════════════════════════════════════════════════════════════════════
st.divider()
st.markdown("## 📍 Encuentra tu tienda más cercana")
st.caption("Ingresa tu ubicación aproximada para ver qué sucursal te queda más cerca.")

sedes = load_json("sedes.json")

col_form, col_mapa = st.columns([1, 2])

with col_form:
    with st.container(border=True):
        st.markdown("#### 🗺️ Tu ubicación")

        # Coordenadas por defecto: centro de Santiago
        lat_default = -33.4569
        lon_default = -70.6483

        user_lat = st.number_input(
            "Latitud", value=lat_default, format="%.4f",
            help="Ej: -33.4569 (Santiago centro)"
        )
        user_lon = st.number_input(
            "Longitud", value=lon_default, format="%.4f",
            help="Ej: -70.6483 (Santiago centro)"
        )

        st.caption("💡 Puedes obtener tus coordenadas en Google Maps → clic derecho → '¿Qué hay aquí?'")

        buscar = st.button("🔍 Ver sede más cercana", type="primary", use_container_width=True)

    # Tabla de distancias a todas las sedes
    st.markdown("#### 📏 Distancias a todas las sedes")
    for s in sedes:
        dist = distancia_km(user_lat, user_lon, s["lat"], s["lon"])
        with st.container(border=True):
            col_n, col_d = st.columns([3, 1])
            col_n.markdown(f"**{s['nombre']}**")
            col_n.caption(s["direccion"])
            col_d.metric("", f"{dist:.1f} km")

with col_mapa:
    # Siempre mostrar el mapa (se actualiza con los inputs)
    deck = mapa_sede_cercana(sedes, user_lat, user_lon)
    st.pydeck_chart(deck, use_container_width=True)

    from map_utils import sede_mas_cercana
    cercana = sede_mas_cercana(sedes, user_lat, user_lon)
    dist_cercana = distancia_km(user_lat, user_lon, cercana["lat"], cercana["lon"])

    st.success(
        f"🟢 Tu sede más cercana es **{cercana['nombre']}** "
        f"a **{dist_cercana:.1f} km** · {cercana['direccion']}"
    )
    with st.container(border=True):
        col_i1, col_i2 = st.columns(2)
        col_i1.write(f"🕐 {cercana['horario']}")
        col_i2.write(f"📞 {cercana['telefono']}")
