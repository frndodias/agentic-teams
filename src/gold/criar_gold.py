"""Cria a gold (g_*): executa os .sql desta pasta em ordem, trocando {cs} por catalog.schema."""
import argparse
import glob
import os
import sys

from pyspark.sql import SparkSession

p = argparse.ArgumentParser()
p.add_argument("--catalog", required=True)
p.add_argument("--schema", required=True)
args = p.parse_args()
cs = f"{args.catalog}.{args.schema}"

pasta = os.path.dirname(os.path.abspath(globals().get("__file__") or sys.argv[0]))
spark = SparkSession.builder.getOrCreate()
for arq in sorted(glob.glob(f"{pasta}/*.sql")):
    print(f"-> {os.path.basename(arq)}")
    spark.sql(open(arq, encoding="utf-8").read().replace("{cs}", cs).strip().rstrip(";"))
print("gold ok")
