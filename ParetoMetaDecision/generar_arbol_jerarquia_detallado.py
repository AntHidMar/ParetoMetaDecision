#!/usr/bin/env python3
"""
Genera el árbol jerárquico de un proyecto y un "context pack" para pegar en ChatGPT.

Salida recomendada:
- project_context.md  (para pegar directamente)
- project_context.json (estructura para parseo)

Uso:
    python project_tree.py
    python project_tree.py /ruta/proyecto
    python project_tree.py . --max-depth 3
    python project_tree.py . -o arbol_proyecto.txt
    python project_tree.py . --context-md project_context.md
    python project_tree.py . --context-md project_context.md --context-json project_context.json
    python project_tree.py . --context-md project_context.md --max-file-chars 4000
"""

import os
import re
import json
import ast
import argparse
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


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
    ".pkl",
    # Nota: NO excluyo .csv aquí, porque a veces conviene conocer que existen.
    # Si quieres mantenerlo fuera del árbol, déjalo aquí; para contexto, normalmente no se pega.
}

# Archivos típicamente irrelevantes o muy ruidosos para pegar a ChatGPT
EXCLUDE_FILES_BY_NAME = {
    "poetry.lock",
    "package-lock.json",
    "yarn.lock",
}


TEXT_EXTENSIONS = {
    ".py", ".md", ".txt", ".yaml", ".yml", ".toml", ".json", ".ini", ".cfg"
}


def should_exclude(path: Path) -> bool:
    """Decide si se debe excluir un archivo o carpeta."""
    name = path.name

    # Excluir directorios por nombre
    if path.is_dir() and name in EXCLUDE_DIRS:
        return True

    # Excluir archivos por nombre (ruidosos)
    if path.is_file() and name in EXCLUDE_FILES_BY_NAME:
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

        if max_depth is not None and depth > max_depth:
            return

        entries = [p for p in current.iterdir() if not should_exclude(p)]
        entries.sort(key=lambda p: (not p.is_dir(), p.name.lower()))

        for i, entry in enumerate(entries):
            is_last = i == len(entries) - 1
            connector = "└── " if is_last else "├── "
            lines.append(f"{prefix}{connector}{entry.name}")

            if entry.is_dir():
                extension = "    " if is_last else "│   "
                _walk(entry, prefix + extension, depth + 1)

    lines.append(root.resolve().name + "/")
    _walk(root, "", 1)
    return "\n".join(lines)


# -----------------------------
# CONTEXT EXTRACTION
# -----------------------------

def safe_read_text(path: Path, max_chars: int) -> str:
    """
    Lee texto con tolerancia a encoding.
    Trunca a max_chars.
    """
    try:
        txt = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        txt = path.read_text(errors="replace")

    if max_chars is not None and len(txt) > max_chars:
        return txt[:max_chars] + "\n\n... [TRUNCATED]\n"
    return txt


def _is_probably_binary(path: Path, sample_size: int = 2048) -> bool:
    """
    Heurística simple para evitar binarios.
    """
    try:
        data = path.read_bytes()[:sample_size]
    except Exception:
        return True
    # muchos bytes nulos => binario
    return b"\x00" in data


def extract_python_signature_info(py_text: str, path_hint: str = "") -> Dict[str, Any]:
    """
    Extrae información estructural de Python usando AST:
    - imports
    - clases (y métodos)
    - funciones top-level
    - dataclasses/enums (heurística)
    - docstrings
    """
    info: Dict[str, Any] = {
        "module_docstring": None,
        "imports": [],
        "classes": [],
        "functions": [],
    }

    try:
        tree = ast.parse(py_text)
    except SyntaxError as e:
        info["parse_error"] = f"SyntaxError: {e}"
        return info

    info["module_docstring"] = ast.get_docstring(tree)

    imports: List[str] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name if alias.asname is None else f"{alias.name} as {alias.asname}")
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            names = []
            for alias in node.names:
                names.append(alias.name if alias.asname is None else f"{alias.name} as {alias.asname}")
            imports.append(f"from {mod} import {', '.join(names)}")

    info["imports"] = imports

    # helper para signature
    def _format_args(fn: ast.FunctionDef) -> str:
        args = []
        for a in fn.args.posonlyargs:
            args.append(a.arg)
        if fn.args.posonlyargs:
            args.append("/")
        for a in fn.args.args:
            args.append(a.arg)
        if fn.args.vararg:
            args.append("*" + fn.args.vararg.arg)
        elif fn.args.kwonlyargs:
            args.append("*")
        for a in fn.args.kwonlyargs:
            args.append(a.arg)
        if fn.args.kwarg:
            args.append("**" + fn.args.kwarg.arg)
        return "(" + ", ".join(args) + ")"

    # detectar decoradores por nombre simple
    def _decorator_names(node: ast.AST) -> List[str]:
        decs = []
        if not hasattr(node, "decorator_list"):
            return decs
        for d in getattr(node, "decorator_list", []):
            if isinstance(d, ast.Name):
                decs.append(d.id)
            elif isinstance(d, ast.Attribute):
                decs.append(d.attr)
            else:
                decs.append(ast.unparse(d) if hasattr(ast, "unparse") else "decorator")
        return decs

    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            info["functions"].append({
                "name": node.name,
                "signature": f"{node.name}{_format_args(node)}",
                "docstring": ast.get_docstring(node),
                "decorators": _decorator_names(node),
            })

        if isinstance(node, ast.ClassDef):
            methods = []
            for b in node.body:
                if isinstance(b, ast.FunctionDef):
                    methods.append({
                        "name": b.name,
                        "signature": f"{b.name}{_format_args(b)}",
                        "docstring": ast.get_docstring(b),
                        "decorators": _decorator_names(b),
                    })

            decs = _decorator_names(node)
            # heurísticas: dataclass/Enum
            bases = []
            for base in node.bases:
                if isinstance(base, ast.Name):
                    bases.append(base.id)
                elif isinstance(base, ast.Attribute):
                    bases.append(base.attr)
                else:
                    bases.append(ast.unparse(base) if hasattr(ast, "unparse") else "base")

            info["classes"].append({
                "name": node.name,
                "bases": bases,
                "decorators": decs,
                "docstring": ast.get_docstring(node),
                "methods": methods,
                "is_dataclass_like": ("dataclass" in decs),
                "is_enum_like": ("Enum" in bases or "Enum" in decs),
            })

    return info


def extract_yaml_keys(text: str, max_keys: int = 60) -> List[str]:
    """
    Extrae claves YAML aproximadas (sin parsear YAML) para contexto rápido.
    """
    keys = []
    for line in text.splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        # key: value
        m = re.match(r"^([A-Za-z0-9_\-]+)\s*:\s*", line)
        if m:
            keys.append(m.group(1))
        if len(keys) >= max_keys:
            break
    return keys


def summarize_file(path: Path, root: Path, max_file_chars: int) -> Optional[Dict[str, Any]]:
    """
    Genera un resumen por archivo (para incluir en md/json).
    """
    if should_exclude(path):
        return None
    if path.is_dir():
        return None

    rel = str(path.relative_to(root))
    stat = path.stat()
    ext = path.suffix.lower()

    # Evita binarios y tamaños absurdos
    if ext not in TEXT_EXTENSIONS:
        # permitir que aparezca en índice pero sin contenido
        return {
            "path": rel,
            "type": "binary_or_nontext",
            "size_bytes": stat.st_size,
            "mtime": stat.st_mtime,
            "summary": f"Non-text file ({ext})",
        }

    if _is_probably_binary(path):
        return {
            "path": rel,
            "type": "binary_or_nontext",
            "size_bytes": stat.st_size,
            "mtime": stat.st_mtime,
            "summary": "Likely binary (skipped)",
        }

    text = safe_read_text(path, max_chars=max_file_chars)

    entry: Dict[str, Any] = {
        "path": rel,
        "type": "text",
        "ext": ext,
        "size_bytes": stat.st_size,
        "mtime": stat.st_mtime,
    }

    # Python: AST summary + (opcional) snippet
    if ext == ".py":
        py_info = extract_python_signature_info(text, path_hint=rel)
        entry["python"] = py_info

        # snippet: primeras ~120 líneas, suficiente para situar el módulo
        lines = text.splitlines()
        snippet = "\n".join(lines[:120])
        entry["snippet_head"] = snippet

    elif ext in {".yaml", ".yml"}:
        entry["yaml_keys"] = extract_yaml_keys(text)
        entry["snippet_head"] = "\n".join(text.splitlines()[:160])

    elif ext == ".toml":
        entry["snippet_head"] = "\n".join(text.splitlines()[:200])

    elif ext in {".md", ".txt"}:
        entry["snippet_head"] = "\n".join(text.splitlines()[:220])

    elif ext == ".json":
        # no intentar parsear grandes json, solo cabecera
        entry["snippet_head"] = "\n".join(text.splitlines()[:200])

    else:
        entry["snippet_head"] = "\n".join(text.splitlines()[:200])

    return entry


def collect_context(root: Path, max_depth: Optional[int], max_file_chars: int) -> Dict[str, Any]:
    """
    Recorre el proyecto y genera un 'context pack'.
    """
    tree_str = build_tree(root, max_depth=max_depth)

    files: List[Dict[str, Any]] = []
    for p in root.rglob("*"):
        if should_exclude(p):
            continue
        if p.is_file():
            info = summarize_file(p, root, max_file_chars=max_file_chars)
            if info:
                files.append(info)

    # Orden: primero core, luego config, luego main, luego resto
    def sort_key(x: Dict[str, Any]) -> Tuple[int, str]:
        path = x["path"]
        if path.startswith("core/"):
            group = 0
        elif path.startswith("config/"):
            group = 1
        elif path == "main.py":
            group = 2
        else:
            group = 9
        return (group, path.lower())

    files.sort(key=sort_key)

    return {
        "root": root.resolve().name,
        "tree": tree_str,
        "files": files,
    }


def context_to_markdown(ctx: Dict[str, Any]) -> str:
    """
    Formato para pegar en ChatGPT: árbol + índice + resumen por archivo.
    """
    lines: List[str] = []
    lines.append(f"# Project Context Pack: {ctx['root']}")
    lines.append("")
    lines.append("## Project Tree")
    lines.append("```")
    lines.append(ctx["tree"])
    lines.append("```")
    lines.append("")

    lines.append("## File Index (summaries)")
    for f in ctx["files"]:
        lines.append(f"- `{f['path']}` ({f.get('size_bytes', 0)} bytes)")

    lines.append("")
    lines.append("## File Details")
    lines.append("")

    for f in ctx["files"]:
        lines.append(f"### `{f['path']}`")
        lines.append("")

        # Python structured summary
        if f.get("ext") == ".py" and "python" in f:
            py = f["python"]
            if py.get("module_docstring"):
                lines.append("**Module docstring:**")
                lines.append("")
                lines.append(py["module_docstring"].strip())
                lines.append("")

            if py.get("imports"):
                lines.append("**Imports:**")
                lines.append("")
                for imp in py["imports"][:40]:
                    lines.append(f"- {imp}")
                lines.append("")

            if py.get("classes"):
                lines.append("**Classes:**")
                lines.append("")
                for c in py["classes"]:
                    bases = f"({', '.join(c['bases'])})" if c.get("bases") else ""
                    tags = []
                    if c.get("is_dataclass_like"):
                        tags.append("dataclass")
                    if c.get("is_enum_like"):
                        tags.append("enum-like")
                    tag_str = f" [{' ,'.join(tags)}]" if tags else ""
                    lines.append(f"- `{c['name']}{bases}`{tag_str}")
                    if c.get("docstring"):
                        ds = c["docstring"].strip().splitlines()[0]
                        lines.append(f"  - doc: {ds}")
                    if c.get("methods"):
                        lines.append("  - methods:")
                        for m in c["methods"][:30]:
                            lines.append(f"    - `{m['signature']}`")
                lines.append("")

            if py.get("functions"):
                lines.append("**Functions:**")
                lines.append("")
                for fn in py["functions"][:40]:
                    lines.append(f"- `{fn['signature']}`")
                lines.append("")

        # YAML quick keys
        if f.get("ext") in {".yaml", ".yml"} and f.get("yaml_keys"):
            lines.append("**YAML top keys (approx):** " + ", ".join(f["yaml_keys"]))
            lines.append("")

        # Snippet head
        snippet = f.get("snippet_head")
        if snippet:
            lines.append("**Head snippet:**")
            lines.append("```")
            lines.append(snippet)
            lines.append("```")
            lines.append("")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Genera el árbol jerárquico y contexto para ChatGPT.")
    parser.add_argument("root", nargs="?", default=".", help="Directorio raíz del proyecto.")
    parser.add_argument("--max-depth", type=int, default=None, help="Profundidad máxima del árbol.")
    parser.add_argument("-o", "--output", type=str, default=None, help="Archivo de salida del árbol (solo árbol).")

    # Nuevos outputs
    parser.add_argument("--context-md", type=str, default=None, help="Genera un contexto en Markdown (recomendado).")
    parser.add_argument("--context-json", type=str, default=None, help="Genera un contexto en JSON.")

    parser.add_argument("--max-file-chars", type=int, default=6000, help="Máx caracteres por archivo en snippet.")

    args = parser.parse_args()

    root_path = Path(args.root).resolve()
    if not root_path.exists() or not root_path.is_dir():
        raise SystemExit(f"Ruta no válida o no es un directorio: {root_path}")

    # Árbol (comportamiento original)
    tree_str = build_tree(root_path, max_depth=args.max_depth)
    if args.output:
        Path(args.output).write_text(tree_str, encoding="utf-8")
        print(f"Árbol guardado en: {args.output}")
    else:
        print(tree_str)

    # Context pack (nuevo)
    if args.context_md or args.context_json:
        ctx = collect_context(root_path, max_depth=args.max_depth, max_file_chars=args.max_file_chars)

        if args.context_json:
            Path(args.context_json).write_text(json.dumps(ctx, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"Context JSON guardado en: {args.context_json}")

        if args.context_md:
            md = context_to_markdown(ctx)
            Path(args.context_md).write_text(md, encoding="utf-8")
            print(f"Context Markdown guardado en: {args.context_md}")


if __name__ == "__main__":
    main()

    # python generar_arbol_jerarquia_detallado.py . --context-md project_context.md --max-depth 10
    