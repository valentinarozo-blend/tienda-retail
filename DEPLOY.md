# Deploy en AWS Amplify + App Runner

## Arquitectura

```
GitHub/CodeCommit
      ↓
AWS Amplify (CI/CD pipeline)
      ↓ build Docker image
Amazon ECR (registro de imágenes)
      ↓ deploy
AWS App Runner (corre Streamlit en :8501)
      ↓
URL pública HTTPS automática
```

## Pasos previos en AWS (una sola vez)

### 1. Crear rol IAM para App Runner → ECR

```bash
# Crear el rol
aws iam create-role \
  --role-name AppRunnerECRAccessRole \
  --assume-role-policy-document file://infra/ecr_apprunner_role.json

# Adjuntar política administrada de ECR
aws iam attach-role-policy \
  --role-name AppRunnerECRAccessRole \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess

# Guardar el ARN del rol (lo necesitas en el paso 3)
aws iam get-role --role-name AppRunnerECRAccessRole --query "Role.Arn" --output text
```

### 2. Adjuntar permisos al rol de build de Amplify

En la consola de Amplify → tu app → General → Service role,
adjunta la política en `infra/amplify_build_policy.json`.

O via CLI:
```bash
aws iam put-role-policy \
  --role-name AmplifyServiceRole \
  --policy-name AmplifyBuildPolicy \
  --policy-document file://infra/amplify_build_policy.json
```

### 3. Configurar variables de entorno en Amplify

En la consola: Amplify → tu app → Environment variables

| Variable                  | Valor ejemplo                          |
|---------------------------|----------------------------------------|
| `AWS_ACCOUNT_ID`          | `123456789012`                         |
| `AWS_REGION`              | `us-east-1`                            |
| `ECR_REPO_NAME`           | `tienda-retail`                        |
| `APPRUNNER_SERVICE_NAME`  | `tienda-retail-app`                    |
| `APPRUNNER_ECR_ROLE_ARN`  | `arn:aws:iam::123456789012:role/AppRunnerECRAccessRole` |

### 4. Conectar repositorio en Amplify

1. Consola AWS → Amplify → "New app" → "Host web app"
2. Conectar GitHub/CodeCommit con tu repositorio
3. Seleccionar rama (`main`)
4. Amplify detectará el `amplify.yml` automáticamente
5. Guardar y hacer deploy

## Primer deploy

```bash
git add .
git commit -m "feat: initial deploy config"
git push origin main
```

Amplify disparará el pipeline automáticamente en cada push.

## URL de la app

Una vez desplegado, App Runner provee una URL HTTPS del tipo:
`https://xxxxxxxxxx.us-east-1.awsapprunner.com`

## Notas importantes

- Los archivos en `data/` (pedidos, usuarios) son efímeros en contenedores.
  Para producción real, migrar a DynamoDB o RDS.
- El primer deploy tarda ~5 min en crear el servicio App Runner.
- Los deploys siguientes toman ~2-3 min.
