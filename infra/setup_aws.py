"""
infra/setup_aws.py
──────────────────
Script de setup único que crea todos los recursos AWS necesarios:
  - Cognito User Pool + App Client
  - DynamoDB tablas (pedidos, productos)
  - S3 bucket (comprobantes)
  - IAM Role para App Runner con permisos a Bedrock + DynamoDB + S3 + Cognito

Uso:
    python infra/setup_aws.py --region us-east-1 --prefix tienda-retail

Genera un archivo .env con todas las variables necesarias.
"""

import boto3
import json
import argparse
import os
import sys

def crear_cognito(client, prefix, region):
    print("→ Creando Cognito User Pool...")
    pool = client.create_user_pool(
        PoolName=f"{prefix}-users",
        Policies={
            "PasswordPolicy": {
                "MinimumLength": 8,
                "RequireUppercase": True,
                "RequireLowercase": True,
                "RequireNumbers": True,
                "RequireSymbols": False,
            }
        },
        Schema=[
            {"Name": "email",      "AttributeDataType": "String", "Required": True,  "Mutable": True},
            {"Name": "name",       "AttributeDataType": "String", "Required": False, "Mutable": True},
            {"Name": "rol",        "AttributeDataType": "String", "Required": False, "Mutable": True,
             "StringAttributeConstraints": {"MinLength": "1", "MaxLength": "20"}},
        ],
        AutoVerifiedAttributes=["email"],
        UsernameAttributes=["email"],
        AccountRecoverySetting={
            "RecoveryMechanisms": [{"Priority": 1, "Name": "verified_email"}]
        },
    )
    pool_id = pool["UserPool"]["Id"]
    print(f"  ✅ User Pool: {pool_id}")

    app_client = client.create_user_pool_client(
        UserPoolId=pool_id,
        ClientName=f"{prefix}-app",
        ExplicitAuthFlows=["ALLOW_USER_PASSWORD_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"],
        GenerateSecret=False,
    )
    client_id = app_client["UserPoolClient"]["ClientId"]
    print(f"  ✅ App Client: {client_id}")

    # Crear usuario admin por defecto
    try:
        client.admin_create_user(
            UserPoolId=pool_id,
            Username="admin@tienda.cl",
            TemporaryPassword="Admin123!",
            UserAttributes=[
                {"Name": "email",        "Value": "admin@tienda.cl"},
                {"Name": "name",         "Value": "Administrador"},
                {"Name": "custom:rol",   "Value": "admin"},
                {"Name": "email_verified","Value": "true"},
            ],
            MessageAction="SUPPRESS",
        )
        print("  ✅ Usuario admin creado: admin@tienda.cl / Admin123!")
    except Exception as e:
        print(f"  ⚠️  Admin ya existe o error: {e}")

    return pool_id, client_id


def crear_dynamodb(region, prefix):
    print("→ Creando tablas DynamoDB...")
    ddb = boto3.client("dynamodb", region_name=region)

    tablas = [
        {
            "TableName": f"{prefix}-pedidos",
            "KeySchema": [{"AttributeName": "id", "KeyType": "HASH"}],
            "AttributeDefinitions": [{"AttributeName": "id", "AttributeType": "S"}],
            "BillingMode": "PAY_PER_REQUEST",
        },
        {
            "TableName": f"{prefix}-productos",
            "KeySchema": [{"AttributeName": "id", "KeyType": "HASH"}],
            "AttributeDefinitions": [{"AttributeName": "id", "AttributeType": "S"}],
            "BillingMode": "PAY_PER_REQUEST",
        },
    ]

    nombres = []
    for t in tablas:
        try:
            ddb.create_table(**t)
            print(f"  ✅ Tabla: {t['TableName']}")
        except ddb.exceptions.ResourceInUseException:
            print(f"  ⚠️  Tabla ya existe: {t['TableName']}")
        nombres.append(t["TableName"])

    return nombres[0], nombres[1]


def crear_s3(region, prefix):
    print("→ Creando bucket S3...")
    s3     = boto3.client("s3", region_name=region)
    bucket = f"{prefix}-comprobantes"

    try:
        if region == "us-east-1":
            s3.create_bucket(Bucket=bucket)
        else:
            s3.create_bucket(
                Bucket=bucket,
                CreateBucketConfiguration={"LocationConstraint": region}
            )
        # Bloquear acceso público
        s3.put_public_access_block(
            Bucket=bucket,
            PublicAccessBlockConfiguration={
                "BlockPublicAcls": True, "IgnorePublicAcls": True,
                "BlockPublicPolicy": True, "RestrictPublicBuckets": True,
            }
        )
        print(f"  ✅ Bucket: {bucket}")
    except s3.exceptions.BucketAlreadyOwnedByYou:
        print(f"  ⚠️  Bucket ya existe: {bucket}")

    return bucket


def crear_iam_role(region, prefix, account_id, pool_id, tabla_pedidos, tabla_productos, bucket):
    print("→ Creando IAM Role para App Runner...")
    iam = boto3.client("iam")

    role_name   = f"{prefix}-apprunner-role"
    policy_name = f"{prefix}-apprunner-policy"

    trust = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "tasks.apprunner.amazonaws.com"},
            "Action": "sts:AssumeRole"
        }]
    }

    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "Bedrock",
                "Effect": "Allow",
                "Action": ["bedrock:InvokeModel"],
                "Resource": f"arn:aws:bedrock:{region}::foundation-model/anthropic.claude-3-haiku-20240307-v1:0"
            },
            {
                "Sid": "DynamoDB",
                "Effect": "Allow",
                "Action": ["dynamodb:PutItem","dynamodb:GetItem","dynamodb:Scan",
                           "dynamodb:UpdateItem","dynamodb:DeleteItem","dynamodb:BatchWriteItem"],
                "Resource": [
                    f"arn:aws:dynamodb:{region}:{account_id}:table/{tabla_pedidos}",
                    f"arn:aws:dynamodb:{region}:{account_id}:table/{tabla_productos}",
                ]
            },
            {
                "Sid": "S3",
                "Effect": "Allow",
                "Action": ["s3:PutObject","s3:GetObject","s3:ListBucket","s3:DeleteObject"],
                "Resource": [
                    f"arn:aws:s3:::{bucket}",
                    f"arn:aws:s3:::{bucket}/*",
                ]
            },
            {
                "Sid": "Cognito",
                "Effect": "Allow",
                "Action": ["cognito-idp:AdminConfirmSignUp","cognito-idp:AdminCreateUser",
                           "cognito-idp:AdminGetUser","cognito-idp:DescribeUserPool"],
                "Resource": f"arn:aws:cognito-idp:{region}:{account_id}:userpool/{pool_id}"
            },
        ]
    }

    try:
        role = iam.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(trust),
            Description=f"App Runner role for {prefix}",
        )
        role_arn = role["Role"]["Arn"]
    except iam.exceptions.EntityAlreadyExistsException:
        role_arn = f"arn:aws:iam::{account_id}:role/{role_name}"
        print(f"  ⚠️  Role ya existe: {role_name}")

    try:
        iam.put_role_policy(
            RoleName=role_name,
            PolicyName=policy_name,
            PolicyDocument=json.dumps(policy),
        )
        print(f"  ✅ Role: {role_arn}")
    except Exception as e:
        print(f"  ⚠️  Error en política: {e}")

    return role_arn


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--prefix", default="tienda-retail")
    args = parser.parse_args()

    region = args.region
    prefix = args.prefix

    sts        = boto3.client("sts")
    account_id = sts.get_caller_identity()["Account"]
    print(f"\n🚀 Setup AWS para '{prefix}' en {region} (cuenta: {account_id})\n")

    cognito_client = boto3.client("cognito-idp", region_name=region)
    pool_id, client_id = crear_cognito(cognito_client, prefix, region)
    tabla_pedidos, tabla_productos = crear_dynamodb(region, prefix)
    bucket = crear_s3(region, prefix)
    role_arn = crear_iam_role(region, prefix, account_id, pool_id,
                               tabla_pedidos, tabla_productos, bucket)

    # Generar .env
    env_content = f"""# Generado por infra/setup_aws.py
AWS_REGION={region}
COGNITO_USER_POOL_ID={pool_id}
COGNITO_APP_CLIENT_ID={client_id}
DYNAMO_TABLE_PEDIDOS={tabla_pedidos}
DYNAMO_TABLE_PRODUCTOS={tabla_productos}
S3_BUCKET_COMPROBANTES={bucket}
APPRUNNER_INSTANCE_ROLE_ARN={role_arn}
"""
    with open(".env", "w") as f:
        f.write(env_content)

    print(f"""
✅ Setup completo. Variables guardadas en .env

Próximos pasos:
  1. Carga el .env:  export $(cat .env | xargs)
  2. Corre la app:   streamlit run Tienda_Retail.py
  3. Para deploy:    git push origin main  (Amplify CI/CD → App Runner)

Admin Cognito: admin@tienda.cl / Admin123!
""")


if __name__ == "__main__":
    main()
