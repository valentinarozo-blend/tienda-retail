"""
bedrock_client.py
─────────────────
Usa Amazon Nova Pro (amazon.nova-pro-v1:0) vía la API Converse de Bedrock.
Nova Pro es el modelo premium de Amazon — multimodal, contexto largo, alta precisión.

API: converse() — formato unificado, no requiere anthropic_version.
"""

import json
import os
import boto3
from botocore.exceptions import ClientError, NoCredentialsError

# ── Modelo ────────────────────────────────────────────────────────────────────
MODEL_ID = "amazon.nova-pro-v1:0"
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")


def _get_client():
    return boto3.client("bedrock-runtime", region_name=AWS_REGION)


def _invoke(system_prompt: str, user_prompt: str, max_tokens: int = 1024) -> str:
    """
    Llama a Nova Pro usando la API Converse.
    Soporta system prompt separado del mensaje de usuario.
    """
    client = _get_client()

    response = client.converse(
        modelId=MODEL_ID,
        system=[{"text": system_prompt}],
        messages=[
            {"role": "user", "content": [{"text": user_prompt}]}
        ],
        inferenceConfig={
            "maxTokens": max_tokens,
            "temperature": 0.3,   # más determinista para recomendaciones
            "topP": 0.9,
        },
    )

    return response["output"]["message"]["content"][0]["text"].strip()


# ══════════════════════════════════════════════════════════════════════════════
# Función 1 — Recomendador de productos
# ══════════════════════════════════════════════════════════════════════════════

def recomendar_productos(carrito_items: list, todos_productos: list, n: int = 3) -> list:
    """
    Dado el carrito actual y el catálogo, retorna hasta `n` productos
    recomendados con justificación.

    Retorna: [{"id": int, "razon": str}, ...]
    """
    if not carrito_items:
        return []

    carrito_str = "\n".join(
        f"- {i['producto']['nombre']} ({i['producto']['categoria']}, "
        f"${i['producto']['precio']:,})"
        for i in carrito_items
    )

    catalogo_str = "\n".join(
        f"- ID {p['id']}: {p['nombre']} | {p['categoria']} | "
        f"${p['precio']:,} | stock: {p['stock']}"
        for p in todos_productos
        if p["stock"] > 0
        and p["id"] not in {i["producto"]["id"] for i in carrito_items}
    )

    system = (
        "Eres un experto en ventas de moda y accesorios. "
        "Tu tarea es recomendar productos complementarios basándote en el carrito del cliente. "
        "Responde SIEMPRE con JSON válido, sin texto adicional antes ni después."
    )

    user = f"""El cliente tiene en su carrito:
{carrito_str}

Catálogo disponible (solo con stock):
{catalogo_str}

Recomienda exactamente {n} productos que complementen el carrito.
Responde ÚNICAMENTE con este JSON:
[
  {{"id": <número entero>, "razon": "<frase corta en español de máximo 10 palabras>"}},
  ...
]"""

    try:
        raw   = _invoke(system, user, max_tokens=512)
        start = raw.find("[")
        end   = raw.rfind("]") + 1
        recs  = json.loads(raw[start:end])
        ids_validos = {p["id"] for p in todos_productos}
        return [r for r in recs if r.get("id") in ids_validos][:n]
    except Exception:
        return []


# ══════════════════════════════════════════════════════════════════════════════
# Función 2 — Análisis de ventas
# ══════════════════════════════════════════════════════════════════════════════

def analizar_ventas(pedidos: list, productos: list) -> str:
    """
    Análisis ejecutivo de ventas con insights y recomendaciones.
    Usa Nova Pro para mayor profundidad analítica.
    """
    if not pedidos:
        return "No hay datos de ventas suficientes para analizar."

    total_ventas  = sum(p["total"] for p in pedidos)
    total_pedidos = len(pedidos)
    ticket_prom   = total_ventas / total_pedidos

    ventas_sede = {}
    for p in pedidos:
        ventas_sede[p["sede"]] = ventas_sede.get(p["sede"], 0) + p["total"]

    ventas_prod = {}
    for p in pedidos:
        for item in p["items"]:
            ventas_prod[item["nombre"]] = ventas_prod.get(item["nombre"], 0) + item["cantidad"]

    bajo_stock = [p["nombre"] for p in productos if 0 < p["stock"] <= 5]
    sin_stock  = [p["nombre"] for p in productos if p["stock"] == 0]

    system = (
        "Eres un analista de negocio senior especializado en retail de moda latinoamericano. "
        "Entregas informes ejecutivos concisos, basados en datos, con recomendaciones accionables. "
        "Usas markdown para estructurar el informe. Escribes en español."
    )

    user = f"""Analiza estos datos de ventas y entrega un informe ejecutivo:

**Datos:**
- Total ventas: ${total_ventas:,}
- Pedidos: {total_pedidos}
- Ticket promedio: ${ticket_prom:,.0f}
- Ventas por sede: {json.dumps(ventas_sede, ensure_ascii=False)}
- Unidades por producto: {json.dumps(ventas_prod, ensure_ascii=False)}
- Stock bajo (≤5 uds): {bajo_stock}
- Sin stock: {sin_stock}
- Productos en catálogo: {len(productos)}

**Estructura del informe:**
1. **Resumen ejecutivo** — 2 oraciones con los números clave
2. **Rendimiento por sede** — cuál lidera y por qué importa
3. **Productos estrella y rezagados** — top 3 y bottom 3
4. **Alertas de inventario** — riesgo de quiebre de stock
5. **3 recomendaciones accionables** — específicas y priorizadas por impacto"""

    try:
        return _invoke(system, user, max_tokens=1500)
    except NoCredentialsError:
        return "⚠️ No se encontraron credenciales AWS. Ejecuta `aws configure`."
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code == "AccessDeniedException":
            return (
                "⚠️ Sin acceso a Nova Pro. Ve a **Bedrock → Model access** "
                "y solicita acceso a `amazon.nova-pro-v1:0`."
            )
        return f"⚠️ Error Bedrock ({code}): {e.response['Error']['Message']}"
    except Exception as e:
        return f"⚠️ Error inesperado: {str(e)}"


# ══════════════════════════════════════════════════════════════════════════════
# Función 3 — Descripción de producto (bonus)
# ══════════════════════════════════════════════════════════════════════════════

def generar_descripcion_producto(nombre: str, categoria: str, precio: int) -> str:
    """
    Genera una descripción de marketing atractiva para un producto.
    Útil en el panel admin al crear nuevos productos.
    """
    system = (
        "Eres un copywriter experto en moda y retail. "
        "Escribes descripciones de productos atractivas, concisas (máximo 3 oraciones) "
        "y orientadas a la conversión. Español neutro latinoamericano."
    )
    user = (
        f"Escribe una descripción de producto para:\n"
        f"- Nombre: {nombre}\n"
        f"- Categoría: {categoria}\n"
        f"- Precio: ${precio:,}\n\n"
        f"Máximo 3 oraciones. Sin bullet points. Tono moderno y aspiracional."
    )
    try:
        return _invoke(system, user, max_tokens=256)
    except Exception as e:
        return f"⚠️ {str(e)}"
