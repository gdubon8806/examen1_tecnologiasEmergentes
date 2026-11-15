"""
Pipeline completo (orquestacion simple): extraccion incremental -> limpieza -> carga del DW.
Si un paso falla se detiene; corregir y volver a ejecutar es seguro (todo es idempotente).
Uso:  python etl/run_pipeline.py
"""
import subprocess
import sys
import time
from pathlib import Path

ETL = Path(__file__).resolve().parent
STEPS = [
    ("1/3 Extraccion incremental (origen -> raw)", "extract_incremental.py"),
    ("2/3 Limpieza y validacion (raw -> clean)", "clean_raw_to_clean.py"),
    ("3/3 Carga del Data Warehouse (clean -> dw)", "load_dw.py"),
]

if __name__ == "__main__":
    t0 = time.time()
    for label, script in STEPS:
        print(f"\n=== {label} ===", flush=True)
        if subprocess.run([sys.executable, str(ETL / script)]).returncode != 0:
            print(f"\nPIPELINE FALLO en {script}. Revisa audit.etl_run, corrige y vuelve a ejecutar.")
            sys.exit(1)
    print(f"\nPipeline completo en {time.time() - t0:.0f} s")
