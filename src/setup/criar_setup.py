"""Setup da camada agêntica: executa os .sql desta pasta em ordem, trocando {catalog}."""
import argparse
import glob
import os
import sys

from pyspark.sql import SparkSession

p = argparse.ArgumentParser()
p.add_argument("--catalog", required=True)
args = p.parse_args()

pasta = os.path.dirname(os.path.abspath(globals().get("__file__") or sys.argv[0]))
spark = SparkSession.builder.getOrCreate()
for arq in sorted(glob.glob(f"{pasta}/*.sql")):
    print(f"-> {os.path.basename(arq)}")
    spark.sql(open(arq, encoding="utf-8").read().replace("{catalog}", args.catalog).strip().rstrip(";"))
print(spark.sql(f"SELECT arquivo, length(texto) n FROM {args.catalog}.ecommerce.s_documentos").collect())
print("setup ok")
