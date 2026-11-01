"""Restaura execuções do time a partir de um branch point-in-time do Lakebase.

1. Crie um branch no momento anterior à perda:
   databricks postgres create-branch projects/agentic-teams rec --json '{"spec":{"source_branch":"projects/agentic-teams/branches/production",
     "source_branch_time":"2026-11-01T16:26:30Z","ttl":"86400s"}}'
2. uv run --with databricks-sdk --with "psycopg[binary]" --with requests python scripts/restaurar_historico.py \
     --endpoint projects/agentic-teams/branches/rec/endpoints/primary
As execuções voltam pelo app (dono das tabelas); run_id que já existe é ignorado. Pendentes voltam como "descartado".
"""
import argparse
import datetime as dt
import decimal
import json

import psycopg
import requests
from databricks.sdk import WorkspaceClient
from psycopg.rows import dict_row

p = argparse.ArgumentParser()
p.add_argument("--profile", default="fevm-fc")
p.add_argument("--endpoint", required=True)
p.add_argument("--app", default="agentic-teams")
a = p.parse_args()
w = WorkspaceClient(profile=a.profile)

host = w.postgres.get_endpoint(name=a.endpoint).status.hosts.host
tok = w.postgres.generate_database_credential(endpoint=a.endpoint).token
dados = {}
with psycopg.connect(host=host, dbname="databricks_postgres", user=w.current_user.me().user_name, password=tok,
                     sslmode="require", row_factory=dict_row) as c:
    for t, ordem in [("runs", "criado_em"), ("steps", "step_id"), ("handoffs", "handoff_id"), ("approvals", "approval_id"),
                     ("dq_results", "dq_id"), ("artifacts", "artifact_id")]:
        dados[t] = c.execute(f"SELECT * FROM agentic_teams.{t} ORDER BY {ordem}").fetchall()
for r in dados["runs"]:
    if r["status"] not in ("concluido", "rejeitado", "descartado"):
        r["status"], r["etapa"] = "descartado", "descartado"
for ap in dados["approvals"]:
    if ap["status"] == "pendente":
        ap["status"] = "descartada"


def _conv(o):
    if isinstance(o, (dt.datetime, dt.date)):
        return o.isoformat()
    if isinstance(o, decimal.Decimal):
        return float(o)
    raise TypeError(type(o))


url = w.apps.get(a.app).url
r = requests.post(f"{url}/api/admin/importar", headers={"Authorization": w.config.authenticate()["Authorization"],
                  "Content-Type": "application/json"}, data=json.dumps(dados, default=_conv), timeout=300)
r.raise_for_status()
print("importado:", r.json(), "| runs:", [x["run_id"] for x in dados["runs"]])
