import math
import pydeck as pdk
import pandas as pd

# ── Paleta de colores ─────────────────────────────────────────────────────────
COLOR_SEDE_ACTIVA  = [233, 69,  96,  230]   # rojo tienda
COLOR_SEDE_NORMAL  = [26,  26,  46,  180]   # azul oscuro
COLOR_SEDE_CERCANA = [16,  185, 129, 220]   # verde
COLOR_USUARIO      = [99,  102, 241, 255]   # violeta
COLOR_RUTA         = [233, 69,  96,  200]   # rojo ruta


def distancia_km(lat1, lon1, lat2, lon2) -> float:
    """Haversine simplificado."""
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))


def sede_mas_cercana(sedes: list, lat: float, lon: float) -> dict:
    return min(sedes, key=lambda s: distancia_km(lat, lon, s["lat"], s["lon"]))


def mapa_sedes(sedes: list, sede_activa_nombre: str = None, zoom: int = 11) -> pdk.Deck:
    """
    Mapa 3D con todas las sedes. La sede activa se muestra más grande y en rojo.
    """
    data = []
    for s in sedes:
        activa = s["nombre"] == sede_activa_nombre
        data.append({
            "lat":    s["lat"],
            "lon":    s["lon"],
            "nombre": s["nombre"],
            "dir":    s["direccion"],
            "color":  COLOR_SEDE_ACTIVA if activa else COLOR_SEDE_NORMAL,
            "radio":  120 if activa else 60,
            "elev":   400 if activa else 150,
        })

    df = pd.DataFrame(data)
    centro_lat = sum(s["lat"] for s in sedes) / len(sedes)
    centro_lon = sum(s["lon"] for s in sedes) / len(sedes)

    capa_columnas = pdk.Layer(
        "ColumnLayer",
        data=df,
        get_position=["lon", "lat"],
        get_elevation="elev",
        elevation_scale=1,
        radius="radio",
        get_fill_color="color",
        pickable=True,
        auto_highlight=True,
    )

    capa_texto = pdk.Layer(
        "TextLayer",
        data=df,
        get_position=["lon", "lat"],
        get_text="nombre",
        get_size=14,
        get_color=[255, 255, 255, 220],
        get_alignment_baseline="'bottom'",
        get_pixel_offset=[0, -20],
    )

    vista = pdk.ViewState(
        latitude=centro_lat,
        longitude=centro_lon,
        zoom=zoom,
        pitch=45,
        bearing=0,
    )

    return pdk.Deck(
        layers=[capa_columnas, capa_texto],
        initial_view_state=vista,
        tooltip={"text": "📍 {nombre}\n{dir}"},
        map_style="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
    )


def mapa_sede_cercana(sedes: list, user_lat: float, user_lon: float) -> pdk.Deck:
    """
    Mapa que muestra la ubicación del usuario + todas las sedes,
    destacando la más cercana con una línea de conexión.
    """
    cercana = sede_mas_cercana(sedes, user_lat, user_lon)

    puntos = [{
        "lat": user_lat, "lon": user_lon,
        "nombre": "📍 Tu ubicación",
        "color": COLOR_USUARIO, "radio": 80, "elev": 300,
    }]
    for s in sedes:
        es_cercana = s["nombre"] == cercana["nombre"]
        puntos.append({
            "lat": s["lat"], "lon": s["lon"],
            "nombre": s["nombre"],
            "color": COLOR_SEDE_CERCANA if es_cercana else COLOR_SEDE_NORMAL,
            "radio": 100 if es_cercana else 55,
            "elev": 350 if es_cercana else 120,
        })

    df_puntos = pd.DataFrame(puntos)

    # Línea usuario → sede cercana
    df_linea = pd.DataFrame([{
        "inicio": [user_lon, user_lat],
        "fin":    [cercana["lon"], cercana["lat"]],
    }])

    capa_arco = pdk.Layer(
        "ArcLayer",
        data=df_linea,
        get_source_position="inicio",
        get_target_position="fin",
        get_source_color=COLOR_USUARIO,
        get_target_color=COLOR_SEDE_CERCANA,
        get_width=4,
        pickable=False,
    )

    capa_cols = pdk.Layer(
        "ColumnLayer",
        data=df_puntos,
        get_position=["lon", "lat"],
        get_elevation="elev",
        elevation_scale=1,
        radius="radio",
        get_fill_color="color",
        pickable=True,
        auto_highlight=True,
    )

    capa_texto = pdk.Layer(
        "TextLayer",
        data=df_puntos,
        get_position=["lon", "lat"],
        get_text="nombre",
        get_size=13,
        get_color=[255, 255, 255, 200],
        get_pixel_offset=[0, -18],
    )

    # Centrar entre usuario y sede cercana
    centro_lat = (user_lat + cercana["lat"]) / 2
    centro_lon = (user_lon + cercana["lon"]) / 2

    vista = pdk.ViewState(
        latitude=centro_lat,
        longitude=centro_lon,
        zoom=12,
        pitch=50,
        bearing=10,
    )

    return pdk.Deck(
        layers=[capa_arco, capa_cols, capa_texto],
        initial_view_state=vista,
        tooltip={"text": "{nombre}"},
        map_style="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
    )


def mapa_ruta_envio(user_lat: float, user_lon: float, sede_lat: float, sede_lon: float, sede_nombre: str) -> pdk.Deck:
    """
    Mapa de ruta de envío a domicilio: sede → domicilio del cliente.
    Muestra arco animado + puntos de origen y destino.
    """
    df_puntos = pd.DataFrame([
        {
            "lat": sede_lat, "lon": sede_lon,
            "nombre": f"🏪 {sede_nombre}",
            "color": COLOR_SEDE_ACTIVA, "radio": 90, "elev": 350,
        },
        {
            "lat": user_lat, "lon": user_lon,
            "nombre": "🏠 Tu domicilio",
            "color": COLOR_USUARIO, "radio": 90, "elev": 350,
        },
    ])

    # Puntos intermedios para simular ruta
    pasos = 8
    ruta_pts = []
    for k in range(pasos + 1):
        t = k / pasos
        ruta_pts.append({
            "lat": sede_lat + (user_lat - sede_lat) * t,
            "lon": sede_lon + (user_lon - sede_lon) * t,
        })

    df_ruta = pd.DataFrame([
        {"inicio": [ruta_pts[k]["lon"], ruta_pts[k]["lat"]],
         "fin":    [ruta_pts[k+1]["lon"], ruta_pts[k+1]["lat"]]}
        for k in range(pasos)
    ])

    capa_ruta = pdk.Layer(
        "ArcLayer",
        data=pd.DataFrame([{
            "inicio": [sede_lon, sede_lat],
            "fin":    [user_lon, user_lat],
        }]),
        get_source_position="inicio",
        get_target_position="fin",
        get_source_color=COLOR_SEDE_ACTIVA,
        get_target_color=COLOR_USUARIO,
        get_width=5,
        pickable=False,
    )

    capa_cols = pdk.Layer(
        "ColumnLayer",
        data=df_puntos,
        get_position=["lon", "lat"],
        get_elevation="elev",
        elevation_scale=1,
        radius="radio",
        get_fill_color="color",
        pickable=True,
        auto_highlight=True,
    )

    capa_texto = pdk.Layer(
        "TextLayer",
        data=df_puntos,
        get_position=["lon", "lat"],
        get_text="nombre",
        get_size=14,
        get_color=[255, 255, 255, 230],
        get_pixel_offset=[0, -22],
    )

    centro_lat = (sede_lat + user_lat) / 2
    centro_lon = (sede_lon + user_lon) / 2
    dist = distancia_km(sede_lat, sede_lon, user_lat, user_lon)
    zoom = 13 if dist < 3 else 12 if dist < 8 else 11

    vista = pdk.ViewState(
        latitude=centro_lat,
        longitude=centro_lon,
        zoom=zoom,
        pitch=55,
        bearing=-10,
    )

    return pdk.Deck(
        layers=[capa_ruta, capa_cols, capa_texto],
        initial_view_state=vista,
        tooltip={"text": "{nombre}"},
        map_style="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
    )
