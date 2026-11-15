"""Verificacion (best-effort) de las cifras del texto generado contra los datos consultados."""
import re

TOKEN = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?")


def collect_numbers(obj, out=None):
    out = [] if out is None else out
    if isinstance(obj, bool):
        return out
    if isinstance(obj, (int, float)):
        out.append(abs(float(obj)))
    elif isinstance(obj, dict):
        for v in obj.values():
            collect_numbers(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            collect_numbers(v, out)
    elif isinstance(obj, str):
        out.extend(abs(float(t.replace(",", ""))) for t in TOKEN.findall(obj))
    return out


def unverified_numbers(text: str, results: list[dict], facts: list[str]) -> list[str]:
    """Cifras del texto (>= 10, que no sean anos) que no aparecen en los datos (tolerancia 1 %, escalas k/M)."""
    known = collect_numbers([r["data"] for r in results]) + collect_numbers(facts)
    bad = []
    for tok in TOKEN.findall(text or ""):
        v = float(tok.replace(",", ""))
        if v < 10 or (v == int(v) and 1900 <= v <= 2100):
            continue
        ok = any(abs(v - k / s) <= max(0.06, 0.01 * v) for k in known for s in (1, 1e3, 1e6))
        if not ok:
            bad.append(tok)
    return bad
