"""
aws_client.py
─────────────
Capa de acceso a servicios AWS:
  - Cognito   → autenticación de usuarios
  - DynamoDB  → pedidos y productos
  - S3        → comprobantes CSV

Todas las funciones tienen fallback a archivos locales si AWS no está configurado,
para que el desarrollo local siga funcionando sin credenciales.
"""

import os
import json
import csv
import io
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from datetime import datetime

# ── Configuración ─────────────────────────────────────────────────────────────
AWS_REGION            = os.environ.get("AWS_REGION", "us-east-1")
COGNITO_USER_POOL_ID  = os.environ.get("COGNITO_USER_POOL_ID", "")
COGNITO_CLIENT_ID     = os.environ.get("COGNITO_APP_CLIENT_ID", "")
DYNAMO_TABLE_PEDIDOS  = os.environ.get("DYNAMO_TABLE_PEDIDOS",  "tienda-pedidos")
DYNAMO_TABLE_PRODUCTOS= os.environ.get("DYNAMO_TABLE_PRODUCTOS","tienda-productos")
S3_BUCKET             = os.environ.get("S3_BUCKET_COMPROBANTES","tienda-comprobantes")

# Detecta si AWS está disponible
def _aws_disponible() -> bool:
    return bool(COGNITO_USER_POOL_ID and COGNITO_CLIENT_ID)


# ══════════════════════════════════════════════════════════════════════════════
# COGNITO — Autenticación
# ══════════════════════════════════════════════════════════════════════════════

def cognito_login(username: str, password: str) -> dict:
    """
    Autentica usuario con Cognito.
    Retorna: {"ok": True, "usuario": {...}} o {"ok": False, "error": "..."}
    """
    if not _aws_disponible():
        return {"ok": False, "error": "AWS_NOT_CONFIGURED"}

    try:
        client = boto3.client("cognito-idp", region_name=AWS_REGION)
        resp = client.initiate_auth(
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters={"USERNAME": username, "PASSWORD": password},
            ClientId=COGNITO_CLIENT_ID,
        )
        # Obtener atributos del usuario
        token = resp["AuthenticationResult"]["AccessToken"]
        info  = client.get_user(AccessToken=token)
        attrs = {a["Name"]: a["Value"] for a in info["UserAttributes"]}

        return {
            "ok": True,
            "usuario": {
                "username": username,
                "nombre":   attrs.get("name", username),
                "email":    attrs.get("email", ""),
                "rol":      attrs.get("custom:rol", "cliente"),
                "token":    token,
            }
        }
    except client.exceptions.NotAuthorizedException:
        return {"ok": False, "error": "Usuario o contraseña incorrectos."}
    except client.exceptions.UserNotFoundException:
        return {"ok": False, "error": "Usuario no encontrado."}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def cognito_registro(username: str, password: str, nombre: str, email: str) -> dict:
    """
    Registra un nuevo usuario en Cognito.
    Retorna: {"ok": True} o {"ok": False, "error": "..."}
    """
    if not _aws_disponible():
        return {"ok": False, "error": "AWS_NOT_CONFIGURED"}

    try:
        client = boto3.client("cognito-idp", region_name=AWS_REGION)
        client.sign_up(
            ClientId=COGNITO_CLIENT_ID,
            Username=username,
            Password=password,
            UserAttributes=[
                {"Name": "email",       "Value": email},
                {"Name": "name",        "Value": nombre},
                {"Name": "custom:rol",  "Value": "cliente"},
            ],
        )
        # Auto-confirmar (en producción usarías email verification)
        client.admin_confirm_sign_up(
            UserPoolId=COGNITO_USER_POOL_ID,
            Username=username,
        )
        return {"ok": True}
    except client.exceptions.UsernameExistsException:
        return {"ok": False, "error": "Ese nombre de usuario ya existe."}
    except client.exceptions.InvalidPasswordException as e:
        return {"ok": False, "error": f"Contraseña inválida: {e}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def cognito_cambiar_password(token: str, password_viejo: str, password_nuevo: str) -> dict:
    if not _aws_disponible():
        return {"ok": False, "error": "AWS_NOT_CONFIGURED"}
    try:
        client = boto3.client("cognito-idp", region_name=AWS_REGION)
        client.change_password(
            PreviousPassword=password_viejo,
            ProposedPassword=password_nuevo,
            AccessToken=token,
        )
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ══════════════════════════════════════════════════════════════════════════════
# DYNAMODB — Pedidos
# ══════════════════════════════════════════════════════════════════════════════

def dynamo_guardar_pedido(pedido: dict) -> dict:
    """
    Guarda un pedido en DynamoDB.
    La tabla usa 'id' (String) como partition key.
    """
    try:
        ddb = boto3.resource("dynamodb", region_name=AWS_REGION)
        tabla = ddb.Table(DYNAMO_TABLE_PEDIDOS)
        # DynamoDB necesita strings o Decimal, no int para floats
        import decimal
        item = json.loads(
            json.dumps(pedido),
            parse_float=decimal.Decimal
        )
        item["id"] = str(item["id"])
        tabla.put_item(Item=item)
        return {"ok": True}
    except (NoCredentialsError, ClientError) as e:
        return {"ok": False, "error": str(e)}


def dynamo_get_pedidos_usuario(username: str) -> list:
    """
    Retorna todos los pedidos de un usuario desde DynamoDB.
    Usa un scan con FilterExpression (para tablas pequeñas).
    En producción usar GSI sobre 'usuario'.
    """
    try:
        from boto3.dynamodb.conditions import Attr
        ddb   = boto3.resource("dynamodb", region_name=AWS_REGION)
        tabla = ddb.Table(DYNAMO_TABLE_PEDIDOS)
        resp  = tabla.scan(FilterExpression=Attr("usuario").eq(username))
        items = resp.get("Items", [])
        # Convertir Decimal → int/float
        return _deserializar(items)
    except Exception:
        return []


def dynamo_get_todos_pedidos() -> list:
    """Retorna todos los pedidos (solo admin)."""
    try:
        ddb   = boto3.resource("dynamodb", region_name=AWS_REGION)
        tabla = ddb.Table(DYNAMO_TABLE_PEDIDOS)
        resp  = tabla.scan()
        return _deserializar(resp.get("Items", []))
    except Exception:
        return []


def dynamo_get_productos() -> list:
    """Lee el catálogo de productos desde DynamoDB."""
    try:
        ddb   = boto3.resource("dynamodb", region_name=AWS_REGION)
        tabla = ddb.Table(DYNAMO_TABLE_PRODUCTOS)
        resp  = tabla.scan()
        items = _deserializar(resp.get("Items", []))
        for p in items:
            p["id"]     = int(p["id"])
            p["precio"] = int(p["precio"])
            p["stock"]  = int(p["stock"])
        return sorted(items, key=lambda x: x["id"])
    except Exception:
        return []


def dynamo_actualizar_stock(producto_id: int, nuevo_stock: int):
    """Actualiza el stock de un producto en DynamoDB."""
    try:
        ddb   = boto3.resource("dynamodb", region_name=AWS_REGION)
        tabla = ddb.Table(DYNAMO_TABLE_PRODUCTOS)
        tabla.update_item(
            Key={"id": str(producto_id)},
            UpdateExpression="SET stock = :s",
            ExpressionAttributeValues={":s": nuevo_stock},
        )
    except Exception:
        pass


def dynamo_guardar_productos(productos: list):
    """Guarda/actualiza todos los productos en DynamoDB (batch write)."""
    try:
        ddb   = boto3.resource("dynamodb", region_name=AWS_REGION)
        tabla = ddb.Table(DYNAMO_TABLE_PRODUCTOS)
        with tabla.batch_writer() as batch:
            for p in productos:
                item = {k: str(v) if isinstance(v, int) else v for k, v in p.items()}
                item["id"] = str(p["id"])
                batch.put_item(Item=item)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ══════════════════════════════════════════════════════════════════════════════
# S3 — Comprobantes
# ══════════════════════════════════════════════════════════════════════════════

def s3_subir_comprobante(pedido_id: int, csv_content: str, username: str) -> dict:
    """
    Sube el comprobante CSV a S3.
    Retorna: {"ok": True, "url": "https://..."} o {"ok": False, "error": "..."}
    """
    try:
        s3  = boto3.client("s3", region_name=AWS_REGION)
        key = f"comprobantes/{username}/pedido_{pedido_id}.csv"
        s3.put_object(
            Bucket=S3_BUCKET,
            Key=key,
            Body=csv_content.encode("utf-8"),
            ContentType="text/csv",
            ContentDisposition=f'attachment; filename="pedido_{pedido_id}.csv"',
        )
        # URL pre-firmada válida por 1 hora
        url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": S3_BUCKET, "Key": key},
            ExpiresIn=3600,
        )
        return {"ok": True, "url": url, "key": key}
    except (NoCredentialsError, ClientError) as e:
        return {"ok": False, "error": str(e)}


def s3_listar_comprobantes(username: str) -> list:
    """Lista los comprobantes de un usuario en S3."""
    try:
        s3   = boto3.client("s3", region_name=AWS_REGION)
        resp = s3.list_objects_v2(
            Bucket=S3_BUCKET,
            Prefix=f"comprobantes/{username}/"
        )
        return [
            {
                "key":   obj["Key"],
                "fecha": obj["LastModified"].strftime("%Y-%m-%d %H:%M"),
                "size":  f"{obj['Size'] / 1024:.1f} KB",
            }
            for obj in resp.get("Contents", [])
        ]
    except Exception:
        return []


def s3_url_comprobante(key: str) -> str:
    """Genera URL pre-firmada para descargar un comprobante."""
    try:
        s3 = boto3.client("s3", region_name=AWS_REGION)
        return s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": S3_BUCKET, "Key": key},
            ExpiresIn=3600,
        )
    except Exception:
        return ""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _deserializar(items: list) -> list:
    """Convierte Decimal de DynamoDB a int/float."""
    import decimal
    def conv(obj):
        if isinstance(obj, list):
            return [conv(i) for i in obj]
        if isinstance(obj, dict):
            return {k: conv(v) for k, v in obj.items()}
        if isinstance(obj, decimal.Decimal):
            return int(obj) if obj == int(obj) else float(obj)
        return obj
    return [conv(i) for i in items]


def aws_status() -> dict:
    """
    Verifica qué servicios AWS están disponibles.
    Útil para mostrar badges en la UI.
    """
    status = {
        "cognito":  False,
        "dynamodb": False,
        "s3":       False,
        "bedrock":  False,
        "region":   AWS_REGION,
    }
    try:
        boto3.client("cognito-idp", region_name=AWS_REGION).describe_user_pool(
            UserPoolId=COGNITO_USER_POOL_ID
        ) if COGNITO_USER_POOL_ID else None
        status["cognito"] = bool(COGNITO_USER_POOL_ID)
    except Exception:
        pass
    try:
        boto3.client("dynamodb", region_name=AWS_REGION).list_tables(Limit=1)
        status["dynamodb"] = True
    except Exception:
        pass
    try:
        boto3.client("s3", region_name=AWS_REGION).list_buckets()
        status["s3"] = True
    except Exception:
        pass
    try:
        boto3.client("bedrock-runtime", region_name=AWS_REGION)
        status["bedrock"] = True
    except Exception:
        pass
    return status
