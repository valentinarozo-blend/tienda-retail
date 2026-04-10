import streamlit as st
from utils import init_session, inject_css, load_json, save_json
from aws_client import cognito_login, cognito_registro, aws_status, _aws_disponible

st.set_page_config(page_title="Mi Cuenta", page_icon="👤", layout="centered")
init_session()
inject_css()

st.markdown("# 👤 Mi Cuenta")

# ── Badge de modo AWS / Local ─────────────────────────────────────────────────
aws_on = _aws_disponible()
if aws_on:
    st.markdown(
        '<span class="aws-badge aws-badge-ok">☁️ AWS Cognito activo</span>',
        unsafe_allow_html=True
    )
else:
    st.markdown(
        '<span class="aws-badge aws-badge-off">💾 Modo local (sin Cognito)</span>',
        unsafe_allow_html=True
    )
st.write("")

# ── Ya autenticado ────────────────────────────────────────────────────────────
if st.session_state.usuario:
    u = st.session_state.usuario
    st.success(f"Conectado como **{u['nombre']}**")

    col1, col2 = st.columns(2)
    with col1:
        with st.container(border=True):
            st.markdown("#### Perfil")
            st.write(f"👤 **Usuario:** {u['username']}")
            st.write(f"📛 **Nombre:** {u['nombre']}")
            st.write(f"📧 **Email:** {u['email']}")
            st.write(f"🔑 **Rol:** {u.get('rol', 'cliente')}")
            if aws_on:
                st.caption("🔐 Autenticado con AWS Cognito")
            else:
                st.caption("💾 Sesión local")

    with col2:
        with st.container(border=True):
            st.markdown("#### Estadísticas")
            from utils import get_pedidos_usuario, format_precio
            mis_pedidos = get_pedidos_usuario(u["username"])
            total_gastado = sum(p["total"] for p in mis_pedidos)
            st.metric("📦 Pedidos", len(mis_pedidos))
            st.metric("💰 Total gastado", format_precio(total_gastado))

    st.divider()
    if st.button("🚪 Cerrar sesión", type="primary"):
        st.session_state.usuario      = None
        st.session_state.carrito      = {}
        st.session_state.ultimo_pedido = None
        st.rerun()
    st.stop()

# ── Login / Registro ──────────────────────────────────────────────────────────
tab_login, tab_registro = st.tabs(["🔑 Iniciar Sesión", "📝 Registrarse"])

# ── TAB LOGIN ─────────────────────────────────────────────────────────────────
with tab_login:
    with st.form("form_login"):
        st.subheader("Iniciar Sesión")
        username = st.text_input("Usuario")
        password = st.text_input("Contraseña", type="password")
        submitted = st.form_submit_button("Entrar", use_container_width=True, type="primary")

    if submitted:
        if not username or not password:
            st.error("Completa todos los campos.")
        elif aws_on:
            # ── Cognito ──
            with st.spinner("Verificando con AWS Cognito..."):
                resultado = cognito_login(username, password)
            if resultado["ok"]:
                st.session_state.usuario = resultado["usuario"]
                st.session_state.aws_mode = True
                st.success(f"¡Bienvenido, {resultado['usuario']['nombre']}! ☁️")
                st.rerun()
            else:
                st.error(f"❌ {resultado['error']}")
        else:
            # ── Fallback local ──
            usuarios = load_json("usuarios.json")
            usuario  = next(
                (u for u in usuarios if u["username"] == username and u["password"] == password),
                None
            )
            if usuario:
                st.session_state.usuario  = usuario
                st.session_state.aws_mode = False
                st.success(f"¡Bienvenido, {usuario['nombre']}! 💾")
                st.rerun()
            else:
                st.error("Usuario o contraseña incorrectos.")

    st.caption("Usuario admin de prueba: **admin** / **admin123**")

# ── TAB REGISTRO ──────────────────────────────────────────────────────────────
with tab_registro:
    with st.form("form_registro"):
        st.subheader("Crear Cuenta")
        col1, col2 = st.columns(2)
        with col1:
            nuevo_username = st.text_input("Nombre de usuario")
            nuevo_nombre   = st.text_input("Nombre completo")
        with col2:
            nuevo_email    = st.text_input("Email")
            nueva_password = st.text_input("Contraseña", type="password")
        confirmar = st.text_input("Confirmar contraseña", type="password")
        submitted_reg = st.form_submit_button("Registrarse", use_container_width=True, type="primary")

    if submitted_reg:
        if not all([nuevo_username, nuevo_nombre, nuevo_email, nueva_password, confirmar]):
            st.error("Completa todos los campos.")
        elif nueva_password != confirmar:
            st.error("Las contraseñas no coinciden.")
        elif len(nueva_password) < 8:
            st.error("La contraseña debe tener al menos 8 caracteres.")
        elif aws_on:
            # ── Cognito ──
            with st.spinner("Registrando en AWS Cognito..."):
                resultado = cognito_registro(nuevo_username, nueva_password, nuevo_nombre, nuevo_email)
            if resultado["ok"]:
                # Login automático tras registro
                login_res = cognito_login(nuevo_username, nueva_password)
                if login_res["ok"]:
                    st.session_state.usuario  = login_res["usuario"]
                    st.session_state.aws_mode = True
                st.success("✅ Cuenta creada en AWS Cognito. ¡Bienvenido!")
                st.rerun()
            else:
                st.error(f"❌ {resultado['error']}")
        else:
            # ── Fallback local ──
            usuarios = load_json("usuarios.json")
            if any(u["username"] == nuevo_username for u in usuarios):
                st.error("Ese nombre de usuario ya existe.")
            elif any(u["email"] == nuevo_email for u in usuarios):
                st.error("Ese email ya está registrado.")
            else:
                nuevo_usuario = {
                    "username": nuevo_username,
                    "password": nueva_password,
                    "nombre":   nuevo_nombre,
                    "email":    nuevo_email,
                    "rol":      "cliente",
                }
                usuarios.append(nuevo_usuario)
                save_json("usuarios.json", usuarios)
                st.session_state.usuario  = nuevo_usuario
                st.session_state.aws_mode = False
                st.success("✅ Cuenta creada localmente.")
                st.rerun()
