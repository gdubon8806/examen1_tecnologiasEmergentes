"""Ejecuta TODAS las pruebas automaticas (no necesitan base de datos) y guarda el resultado.
Uso:  python tests/run_all.py     -> documentation/tests/unit_test_results.md"""
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SUITES = [("test_cleaning_rules.py", "Reglas de limpieza y calidad (staging)"),
          ("test_backend_logic.py", "API: consultas parametrizadas, paginación, periodos, tokens"),
          ("test_forecast_lib.py", "Machine Learning: división temporal, baselines, pronóstico"),
          ("test_alert_rules.py", "Alertas: condición verdadera/falsa, simulación, claves únicas"),
          ("test_assistant.py", "IA generativa: herramientas, rechazo, verificación de cifras")]

if __name__ == "__main__":
    rows, failed = [], 0
    for file, desc in SUITES:
        r = subprocess.run([sys.executable, str(ROOT / "tests" / file)], capture_output=True, text=True, cwd=ROOT)
        ok = r.returncode == 0
        failed += not ok
        last = (r.stdout.strip().splitlines() or ["(sin salida)"])[-1] if ok else (r.stderr.strip().splitlines() or ["error"])[-1]
        rows.append((file, desc, "PASA" if ok else "FALLA", last))
        print(f"{'PASA ' if ok else 'FALLA'} {file:<28} {last}")
    out = ROOT / "documentation" / "tests"
    out.mkdir(parents=True, exist_ok=True)
    md = [f"# Resultados de pruebas automáticas", "", f"Ejecutado: {datetime.now():%Y-%m-%d %H:%M}", "",
          "| Archivo | Qué prueba | Resultado | Detalle |", "|---|---|---|---|"]
    md += [f"| {f} | {d} | {s} | {l} |" for f, d, s, l in rows]
    (out / "unit_test_results.md").write_text("\n".join(md), encoding="utf-8")
    print(f"\n{len(SUITES) - failed}/{len(SUITES)} suites pasan. Reporte: documentation/tests/unit_test_results.md")
    sys.exit(1 if failed else 0)
