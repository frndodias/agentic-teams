"""Configuração do app (tudo via variáveis de ambiente; ver app.yaml)."""
import os

CATALOG = os.getenv("CATALOG", "fc_catalog")
SCHEMA_DADOS = os.getenv("SCHEMA_DADOS", "ecommerce")
SCHEMA_AGENTES = os.getenv("SCHEMA_AGENTES", "agentic_teams")
SCHEMA_SANDBOX = os.getenv("SCHEMA_SANDBOX", "agentic_teams_sandbox")
WAREHOUSE_ID = os.getenv("DATABRICKS_WAREHOUSE_ID", "")
LLM_MODEL = os.getenv("LLM_MODEL", f"{CATALOG}.{SCHEMA_AGENTES}.agentic_teams_llm")
GENIE_SPACE_ID = os.getenv("GENIE_SPACE_ID", "")
PROMOVER_JOB_ID = os.getenv("PROMOVER_JOB_ID", "")
PR_REPO = os.getenv("PR_REPO", "frndodias/agentic-teams-pr")  # owner/repo, configurável
PR_BRANCH_BASE = os.getenv("PR_BRANCH_BASE", "main")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
# "app_token": o app aprova/mergeia com o token configurado (enquanto o GitHub App com OAuth não existe)
# "github_user": aprovação com a identidade GitHub do engenheiro (OAuth do GitHub App)
GITHUB_APPROVAL_MODE = os.getenv("GITHUB_APPROVAL_MODE", "app_token")
REVISORES = [e.strip().lower() for e in os.getenv("REVISORES", "").split(",") if e.strip()]
MAX_ITERACOES = int(os.getenv("MAX_ITERACOES", "3"))
PG_SCHEMA = os.getenv("PG_SCHEMA", "agentic_teams")
MLFLOW_EXPERIMENT = os.getenv("MLFLOW_EXPERIMENT_ID", "")

FQ_DADOS = f"{CATALOG}.{SCHEMA_DADOS}"
FQ_AGENTES = f"{CATALOG}.{SCHEMA_AGENTES}"
FQ_SANDBOX = f"{CATALOG}.{SCHEMA_SANDBOX}"
