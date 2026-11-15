"""Empaqueta el proyecto para entregarlo SIN secretos ni archivos pesados.
Uso:  python tools/make_submission_zip.py    -> data-platform_entrega.zip (en la carpeta superior)"""
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".venv", "__pycache__", ".git", "node_modules", "logs"}
SKIP_NAMES = {".env"}
SKIP_SUFFIX = {".bak", ".pyc"}
SECRET = re.compile(r"(PASSWORD|API_KEY|SECRET_KEY)\s*=\s*(\S+)", re.I)
SAFE_VALUES = ("CambiaEsto", "pon-aqui", "ClaveApi", "ClaveDash", "<", "contrasena", "tu_", "")


def main():
    out = ROOT.parent / "data-platform_entrega.zip"
    warnings, count = [], 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(ROOT.rglob("*")):
            rel = p.relative_to(ROOT)
            if p.is_dir() or set(rel.parts) & SKIP_DIRS or p.name in SKIP_NAMES or p.suffix in SKIP_SUFFIX:
                continue
            if p.suffix in {".py", ".md", ".sql", ".yml", ".html", ".example", ".txt", ".ps1", ".sh"} or p.name.startswith(".env"):
                try:
                    for m in SECRET.finditer(p.read_text(encoding="utf-8", errors="ignore")):
                        v = m.group(2).strip("'\"#")
                        if v and not v.startswith(SAFE_VALUES) and "os.getenv" not in v and "os.environ" not in v \
                                and not v.startswith(("{", "$", "=")) and len(v) > 3 and v.isascii():
                            warnings.append(f"{rel}: posible secreto -> {m.group(1)}")
                except OSError:
                    pass
            z.write(p, Path("data-platform") / rel)
            count += 1
    print(f"{count} archivos en {out}")
    if warnings:
        print("\nREVISA estos archivos antes de entregar (posibles secretos):")
        print("\n".join(sorted(set(warnings))))
    else:
        print("No se detectaron secretos evidentes. (.env y los .bak se excluyeron.)")


if __name__ == "__main__":
    main()
