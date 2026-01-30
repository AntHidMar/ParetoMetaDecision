#!/usr/bin/env python3
"""
Genera el árbol jerárquico de un proyecto para poder copiarlo y pegarlo en ChatGPT.

Uso:
    python project_tree.py              # árbol del directorio actual
    python project_tree.py /ruta/proyecto
    python project_tree.py . --max-depth 3
    python project_tree.py . -o arbol_proyecto.txt
"""

import os
import argparse
from pathlib import Path

# Carpetas que normalmente no queremos incluir en el árbol
EXCLUDE_DIRS = {
    ".git",
    "__pycache__",
    ".idea",
    ".vscode",
    "venv",
    ".venv",
    "env",
    ".env",
    "node_modules",
    "dist",
    "build",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
}

# Patrones de archivo a excluir (log, binarios, etc. si quieres ampliarlo)
EXCLUDE_FILE_EXT = {
    ".pyc",
    ".pyo",
    ".log",
    ".tmp",
    ".csv",
}


def should_exclude(path: Path) -> bool:
    """Decide si se debe excluir un archivo o carpeta."""
    name = path.name

    # Excluir directorios por nombre
    if path.is_dir() and name in EXCLUDE_DIRS:
        return True

    # Excluir archivos por extensión
    if path.is_file() and path.suffix in EXCLUDE_FILE_EXT:
        return True

    return False


def build_tree(root: Path, max_depth: int | None = None) -> str:
    """Construye el árbol jerárquico como string."""
    lines: list[str] = []

    def _walk(current: Path, prefix: str = "", depth: int = 0) -> None:
        nonlocal lines

        # Si tenemos límite de profundidad y lo hemos alcanzado, no profundizamos más
        if max_depth is not None and depth > max_depth:
            return

        # Filtramos entradas, excluyendo lo que no queramos
        entries = [
            p
            for p in current.iterdir()
            if not should_exclude(p)
        ]

        # Directorios primero, luego archivos; orden alfabético
        entries.sort(key=lambda p: (not p.is_dir(), p.name.lower()))

        for i, entry in enumerate(entries):
            is_last = i == len(entries) - 1
            connector = "└── " if is_last else "├── "

            lines.append(f"{prefix}{connector}{entry.name}")

            if entry.is_dir():
                extension = "    " if is_last else "│   "
                _walk(entry, prefix + extension, depth + 1)

    # Cabecera con el nombre del directorio raíz
    lines.append(root.resolve().name + "/")
    _walk(root, "", 1)

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Genera el árbol jerárquico de un proyecto."
    )
    parser.add_argument(
        "root",
        nargs="?",
        default=".",
        help="Directorio raíz del proyecto (por defecto: directorio actual).",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=None,
        help="Profundidad máxima del árbol (1 = solo carpetas de primer nivel).",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=None,
        help="Archivo de salida (si no se indica, se muestra por pantalla).",
    )

    args = parser.parse_args()

    root_path = Path(args.root).resolve()
    if not root_path.exists() or not root_path.is_dir():
        raise SystemExit(f"Ruta no válida o no es un directorio: {root_path}")

    tree_str = build_tree(root_path, max_depth=args.max_depth)

    if args.output:
        out_path = Path(args.output)
        out_path.write_text(tree_str, encoding="utf-8")
        print(f"Árbol guardado en: {out_path}")
    else:
        print(tree_str)


if __name__ == "__main__":
    main()
