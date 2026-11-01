"""Cria a gold (g_*): executa os .sql desta pasta em ordem, trocando {cs} por catalog.schema."""
import argparse
import glob
import os
import sys

from pyspark.sql import SparkSession

p = argparse.ArgumentParser()
p.add_argument("--catalog", required=True)
p.add_argument("--schema", required=True)
p.add_argument("--leitores", default="", help="principais (vírgula) com SELECT em s_* e g_* (CREATE OR REPLACE apaga grants)")
args = p.parse_args()
cs = f"{args.catalog}.{args.schema}"

pasta = os.path.dirname(os.path.abspath(globals().get("__file__") or sys.argv[0]))
spark = SparkSession.builder.getOrCreate()
for arq in sorted(glob.glob(f"{pasta}/*.sql")):
    print(f"-> {os.path.basename(arq)}")
    spark.sql(open(arq, encoding="utf-8").read().replace("{cs}", cs).strip().rstrip(";"))
# CREATE OR REPLACE VIEW apaga os grants: reaplica para quem consome (hoje o SP do app; depois os grupos)
leitores = [x.strip() for x in args.leitores.split(",") if x.strip()]
if leitores:
    objs = [r.tableName for r in spark.sql(f"SHOW TABLES IN {cs}").collect() if r.tableName.startswith(("s_", "g_"))]
    for principal in leitores:
        for o in objs:
            spark.sql(f"GRANT SELECT ON TABLE {cs}.{o} TO `{principal}`")
    print(f"SELECT reaplicado em {len(objs)} objetos para {leitores}")
print("gold ok")
