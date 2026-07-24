from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(r"C:\Users\audgh\OneDrive\문서\GPT Codex")
PROJECT = ROOT / "cad_ai_preprocessor_php"
OUT = ROOT / "cad_ai_preprocessor_php_fullstack_v2.1.zip"
EXCLUDED_DIRS = {
    "actual_cad_instance",
    "auth_instance",
    "instance",
    "integration_instance",
    "validation_work",
    "render",
    "__pycache__",
    "vendor",
}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".log"}

with ZipFile(OUT, "w", ZIP_DEFLATED) as archive:
    for path in sorted(PROJECT.rglob("*")):
        relative = path.relative_to(PROJECT)
        if path.is_dir():
            continue
        if any(
            part in EXCLUDED_DIRS
            or part.startswith("integration_instance")
            or part.startswith("render")
            for part in relative.parts
        ):
            continue
        if relative.parts[0] == "validation_reports" and len(relative.parts) > 2:
            continue
        if relative.parts[0] == "validation_reports" and path.name not in {
            "validation_10000_runs.json",
            "validation_10000_runs.md",
        }:
            continue
        if path.suffix.lower() in EXCLUDED_SUFFIXES:
            continue
        if path.name == "DETJZ.DOCX" or path.name.startswith("~$"):
            continue
        try:
            archive.write(path, Path(PROJECT.name) / relative)
        except FileNotFoundError:
            # OneDrive/Word can expose a transient lock placeholder while rglob runs.
            continue

print(OUT)
