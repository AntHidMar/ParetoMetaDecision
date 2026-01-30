#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

try:
    import yaml  # type: ignore
except Exception:
    yaml = None


@dataclass
class Evidence:
    mapa_level: int
    evidence_id: str
    weight: float
    file: str
    line: int
    anchor: str
    snippet: str


@dataclass
class LevelSummary:
    level: int
    name: str
    score: float
    found_weight: float
    max_weight: float
    evidences: int
    missing: List[Dict[str, Any]]
    top_anchors: List[Dict[str, Any]]


# -----------------------------
# Config MapA: patrones y pesos
# -----------------------------
MAPA_DEFS = {
    0: {"name": "Reglas fijas", "evidences": [
        {"id": "fixed_rule_policy", "weight": 0.35,
         "patterns": [r"\bpolicy\b", r"\bdecide\b", r"\brule\b"],
         "file_globs": ["**/*.py"],
         "hint": "Faltan políticas/reglas base (policy/decide/rule)."},
        {"id": "single_run_eval", "weight": 0.35,
         "patterns": [r"evaluate\(", r"evaluate_one", r"compute_decisions", r"runner"],
         "file_globs": ["**/*.py"],
         "hint": "Falta pipeline básico de evaluación/runner."},
        {"id": "domain_yaml_presence", "weight": 0.30,
         "patterns": [r"problem_id:", r"factory:", r"search_space:", r"objectives:"],
         "file_globs": ["**/*.yaml", "**/*.yml"],
         "hint": "Falta configuración YAML de dominio (problem_id/factory/search_space/objectives)."},
    ]},
    1: {"name": "Optimización paramétrica", "evidences": [
        {"id": "grid_or_random", "weight": 0.50,
         "patterns": [r"\bGridSearch\b", r"optimizer:\s*\{?\s*id:\s*grid", r"\bid:\s*grid\b", r"\brandom\b", r"\bLHS\b", r"latin"],
         "file_globs": ["**/*.py", "**/*.yaml", "**/*.yml"],
         "hint": "Falta Grid/Random/LHS (id:grid o clase GridSearch)."},
        {"id": "search_space_flat", "weight": 0.50,
         "patterns": [r"search_space:", r"\.theta", r"\.k", r"\bhorizon\b"],
         "file_globs": ["**/*.yaml", "**/*.yml"],
         "hint": "Falta search_space flat (theta/k/horizon) en YAML."},
    ]},
    2: {"name": "Reglas compuestas (plantillas)", "evidences": [
        {"id": "compose_ops", "weight": 0.45,
         "patterns": [r"\bAND\b", r"\bOR\b", r"compose_ops", r"template"],
         "file_globs": ["**/*.yaml", "**/*.yml", "**/*.py"],
         "hint": "Falta composición declarada (AND/OR / compose_ops)."},
        {"id": "combine_logic_in_eval", "weight": 0.55,
         "patterns": [r"if pol in \(\s*\"AND\"\s*,\s*\"OR\"\s*\)", r"both\s*=\s*\(", r"conflict", r"apply_decision_mode_tri"],
         "file_globs": ["**/*.py"],
         "hint": "Falta lógica de combinación en runtime/evaluator."},
    ]},
    3: {"name": "Descubrimiento automático de reglas (AST)", "evidences": [
        {"id": "ast_nodes", "weight": 0.40,
         "patterns": [r"class\s+Atom", r"class\s+And", r"class\s+Or", r"canonical", r"decision_language/ast\.py"],
         "file_globs": ["**/*.py"],
         "hint": "Faltan nodos AST (Atom/And/Or) o canonicalización."},
        {"id": "ast_generation_or_sampling", "weight": 0.35,
         "patterns": [r"max_depth", r"max_nodes", r"sample_ast", r"generate_ast", r"grammar"],
         "file_globs": ["**/*.py", "**/*.yaml", "**/*.yml"],
         "hint": "Falta generación/muestreo de AST (max_depth/max_nodes/sample_ast)."},
        {"id": "params_policy_left_right", "weight": 0.25,
         "patterns": [r"\"policy\"", r"\"left\"", r"\"right\"", r"is_ast", r"is_policy"],
         "file_globs": ["**/*.py"],
         "hint": "Falta soporte params AST (policy/left/right) en código."},
    ]},
    4: {"name": "Multiobjetivo y Pareto", "evidences": [
        {"id": "pareto_front", "weight": 0.40,
         "patterns": [r"pareto", r"non[_-]?dom", r"front", r"hypervolume", r"\bHV\b"],
         "file_globs": ["**/*.py", "**/*.md"],
         "hint": "Falta cálculo Pareto/no-dominancia/HV."},
        {"id": "nsga2_or_moea", "weight": 0.40,
         "patterns": [r"NSGA2", r"tournament_k", r"crossover_rate", r"mutation_rate", r"offspring_size"],
         "file_globs": ["**/*.py", "**/*.yaml", "**/*.yml"],
         "hint": "Falta optimizador multiobjetivo (NSGA2 u operador evolutivo)."},
        {"id": "objectives_yaml", "weight": 0.20,
         "patterns": [r"objectives:", r"direction:\s*(min|max)", r"name:\s*(profit|risk|ppv|recall|utility)"],
         "file_globs": ["**/*.yaml", "**/*.yml"],
         "hint": "Falta declaración de objetivos en YAML."},
    ]},
    5: {"name": "Acto de decidir (abstención, costes, scheduling)", "evidences": [
        {"id": "abstain_or_hold_sample", "weight": 0.35,
         "patterns": [r"ABSTAIN", r"\babstain\b", r"\bhold\b", r"\bsample\b", r"decision_schedule", r"DecisionScheduler", r"\bgate\b"],
         "file_globs": ["**/*.py", "**/*.yaml", "**/*.yml"],
         "hint": "Falta abstención/scheduling/gating (decision_schedule/DecisionScheduler)."},
        {"id": "cost_model", "weight": 0.35,
         "patterns": [r"cost_model", r"slippage", r"fees", r"cost_per_signal", r"lambda_cost"],
         "file_globs": ["**/*.py", "**/*.yaml", "**/*.yml"],
         "hint": "Falta modelado de coste (fees/slippage/cost_per_signal)."},
        {"id": "exposure_frequency_metrics", "weight": 0.30,
         "patterns": [r"\bexposure\b", r"\bfrequency\b", r"decision_rate", r"trade_rate"],
         "file_globs": ["**/*.py"],
         "hint": "Faltan métricas del acto de decidir (exposure/frequency/decision_rate)."},
    ]},
    6: {"name": "Optimización del lenguaje (parsimony/constraints)", "evidences": [
        {"id": "complexity_metric", "weight": 0.35,
         "patterns": [r"complexity", r"complexity_of", r"parsimony", r"dedup"],
         "file_globs": ["**/*.py"],
         "hint": "Falta complejidad/parsimony/deduplicación."},
        {"id": "governance_constraints", "weight": 0.35,
         "patterns": [r"governance", r"violation", r"constraints", r"\ballowed\b", r"\bban\b"],
         "file_globs": ["**/*.py", "**/*.yaml", "**/*.yml"],
         "hint": "Falta gobernanza/violaciones/constraints del lenguaje."},
        {"id": "canonicalization_commutative", "weight": 0.30,
         "patterns": [r"commut", r"canonical", r"sort", r"child keys"],
         "file_globs": ["**/*.py", "**/*.md"],
         "hint": "Falta canonicalización (equivalencias, conmutatividad AND/OR)."},
    ]},
    7: {"name": "Explicabilidad como objetivo", "evidences": [
        {"id": "explainability_objective", "weight": 0.50,
         "patterns": [r"explain", r"explainability", r"rationale", r"interpret", r"justification"],
         "file_globs": ["**/*.py", "**/*.md", "**/*.yaml", "**/*.yml"],
         "hint": "Falta pipeline de explicaciones/rationale/interpretabilidad."},
        {"id": "objective_complexity", "weight": 0.50,
         "patterns": [r"name:\s*complexity", r"objective.*complexity", r"explainability.*objective"],
         "file_globs": ["**/*.yaml", "**/*.yml", "**/*.py"],
         "hint": "Falta integrar complejidad/explicabilidad como objetivo."},
    ]},
    8: {"name": "Humano–sistema (HITL)", "evidences": [
        {"id": "human_in_loop", "weight": 0.60,
         "patterns": [r"human", r"approve", r"reject", r"feedback", r"shortlist", r"preference"],
         "file_globs": ["**/*.py", "**/*.md", "**/*.yaml", "**/*.yml"],
         "hint": "Falta capa HITL (approve/reject/feedback/shortlist)."},
        {"id": "interactive_or_ui", "weight": 0.40,
         "patterns": [r"dashboard", r"\bui\b", r"streamlit", r"\bdash\b", r"gradio", r"webapp"],
         "file_globs": ["**/*.py", "**/*.md"],
         "hint": "Falta interfaz (dashboard/UI) para interacción humana."},
    ]},
    9: {"name": "Meta-decisiones y gobernanza operativa", "evidences": [
        # A) Evidencia operativa: artefactos de auditoría generados en run (NO solo código)
        {"id": "audit_artifacts_present", "weight": 0.40,
        "patterns": [],  # se evalúa por gate operativo, no por texto
        "file_globs": [],
        "hint": "No se encontraron artefactos de auditoría en cache/audit/** (decision_events/pattern_events)."},
        
        # B) Identidad fuerte: hashing de params/domain/dataset o decision_id
        {"id": "strong_identity", "weight": 0.25,
        "patterns": [r"sha256\(", r"params_hash", r"domain_hash", r"decision_id", r"dataset_id"],
        "file_globs": ["**/*.py"],
        "hint": "Falta identidad fuerte (params_hash/domain_hash/decision_id/dataset_id)."},
        
        # C) Razón explícita y gate (permitir vs decidir): reason_code + gate/schedule override
        {"id": "governance_gate_reason", "weight": 0.20,
        "patterns": [r"reason_code", r"BLOCKED_BY_", r"ALLOWED_", r"DecisionScheduler", r"\.gate\("],
        "file_globs": ["**/*.py"],
        "hint": "Falta trazabilidad de permiso/bloqueo (gate + reason_code semántico)."},
        
        # D) Lifecycle operativo (no solo strings): promote/freeze/rollback/shadow implementado en core
        {"id": "lifecycle_ops", "weight": 0.15,
        "patterns": [r"\bpromote\b", r"\bfrozen\b", r"\bdeprecated\b", r"\brollback\b", r"\bshadow\b"],
        "file_globs": ["core/**/*.py"],
        "hint": "Falta ciclo de vida operativo (promote/freeze/rollback/shadow) en core."},
    ]},

}

DEFAULT_EXCLUDES = [
    ".git", ".venv", "venv", "__pycache__", ".pytest_cache",
    "dist", "build", "node_modules", ".mypy_cache", ".ruff_cache",
    "cache", "outputs", "artifacts"
]
TEXT_EXTS = {".py", ".md", ".yaml", ".yml", ".json", ".txt", ".toml", ".ini"}

AUDIT_DIR_HINTS = [
    "cache/audit",
    "cache\\audit",
]

def has_any_files_under(root: Path, rel_dir: str, exts: Tuple[str, ...] = (".json", ".jsonl")) -> bool:
    p = root / rel_dir
    if not p.exists() or not p.is_dir():
        return False
    for f in p.rglob("*"):
        if f.is_file() and f.suffix.lower() in exts and f.stat().st_size > 0:
            return True
    return False

def audit_artifacts_ok(root: Path) -> bool:
    # rutas típicas (ajusta si tu logger escribe en otra)
    return (
        has_any_files_under(root, "cache/audit/decision_events")
        or has_any_files_under(root, "cache/audit/pattern_events")
        or has_any_files_under(root, "cache\\audit\\decision_events")
        or has_any_files_under(root, "cache\\audit\\pattern_events")
    )

def file_exists_any(root: Path, rel_candidates: List[str]) -> bool:
    for rel in rel_candidates:
        if (root / rel).exists():
            return True
    return False

def has_any_files_under(root: Path, rel_dir: str, exts: Tuple[str, ...] = (".json", ".jsonl")) -> bool:
    p = root / rel_dir
    if not p.exists() or not p.is_dir():
        return False
    for f in p.rglob("*"):
        if f.is_file() and f.suffix.lower() in exts:
            return True
    return False

def load_domain_yamls(root: Path) -> List[Tuple[str, dict]]:
    """Carga YAMLs tipo domain.yaml si PyYAML está disponible."""
    if yaml is None:
        return []
    out = []
    for p in root.rglob("*.yaml"):
        try:
            txt = p.read_text(encoding="utf-8", errors="replace")
            data = yaml.safe_load(txt)
            if isinstance(data, dict) and ("problem_id" in data or "factory" in data or "search_space" in data):
                out.append((str(p.relative_to(root)), data))
        except Exception:
            Srin = None
    for p in root.rglob("*.yml"):
        try:
            txt = p.read_text(encoding="utf-8", errors="replace")
            data = yaml.safe_load(txt)
            if isinstance(data, dict) and ("problem_id" in data or "factory" in data or "search_space" in data):
                out.append((str(p.relative_to(root)), data))
        except Exception:
            pass
    return out

def iter_files(root: Path, excludes: List[str]) -> List[Path]:
    files: List[Path] = []
    for p in root.rglob("*"):
        if p.is_dir():
            continue
        rel = str(p.relative_to(root))
        if any(part in rel.split(os.sep) for part in excludes):
            continue
        if p.suffix.lower() in TEXT_EXTS:
            files.append(p)
    return files


def read_text_safe(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None


def find_matches(text: str, pattern: str) -> List[Tuple[int, str]]:
    out = []
    rx = re.compile(pattern)
    for i, line in enumerate(text.splitlines(), start=1):
        if rx.search(line):
            out.append((i, line.strip()[:300]))
    return out


def scan_level(root: Path, files: List[Path], level: int) -> List[Evidence]:
    level_def = MAPA_DEFS[level]
    evidences: List[Evidence] = []

    for ev in level_def["evidences"]:
        ev_id = ev["id"]
        weight = float(ev["weight"])
        patterns = ev.get("patterns", [])
        file_globs = ev.get("file_globs", [])

        local_files: List[Path] = []
        for g in file_globs:
            local_files.extend([p for p in root.glob(g) if p.is_file() and p.suffix.lower() in TEXT_EXTS])

        # si no hay globs, usa todos
        if not local_files:
            local_files = files

        found = []
        for p in local_files:
            txt = read_text_safe(p)
            if not txt:
                continue
            for pat in patterns:
                hits = find_matches(txt, pat)
                for (ln, line) in hits:
                    found.append((p, ln, pat, line))
                    if len(found) >= 10:
                        break
                if len(found) >= 10:
                    break
            if len(found) >= 10:
                break

        for (p, ln, pat, line) in found:
            evidences.append(Evidence(
                mapa_level=level,
                evidence_id=ev_id,
                weight=weight,
                file=str(p.relative_to(root)),
                line=ln,
                anchor=pat,
                snippet=line
            ))

    return evidences


def score_level(root: Path, level: int, evidences: List[Evidence]) -> LevelSummary:

    level_def = MAPA_DEFS[level]
    max_weight = sum(float(ev["weight"]) for ev in level_def["evidences"])
    found_ids = {e.evidence_id for e in evidences}

        # Gate operativo MapA-9: artefactos de auditoría reales
    if level == 9:
        s, missing = check_mapa9_operational(root)
        # Construimos el LevelSummary sin usar evidences por strings
        return LevelSummary(
            level=9,
            name=MAPA_DEFS[9]["name"],
            score=s,
            missing=missing
        )

    found_weight = 0.0
    missing = []
    for ev in level_def["evidences"]:
        if ev["id"] in found_ids:
            found_weight += float(ev["weight"])
        else:
            missing.append({
                "evidence_id": ev["id"],
                "weight": float(ev["weight"]),
                "hint": ev.get("hint", ""),
                "expected_globs": ev.get("file_globs", []),
                "patterns": ev.get("patterns", []),
            })

    score = 0.0 if max_weight <= 0 else min(1.0, found_weight / max_weight)

    top = []
    for ev in level_def["evidences"]:
        ev_id = ev["id"]
        matches = [e for e in evidences if e.evidence_id == ev_id][:2]
        top.append({
            "evidence_id": ev_id,
            "weight": float(ev["weight"]),
            "found": ev_id in found_ids,
            "examples": [
                {"file": m.file, "line": m.line, "anchor": m.anchor, "snippet": m.snippet}
                for m in matches
            ],
        })

    return LevelSummary(
        level=level,
        name=level_def["name"],
        score=score,
        found_weight=found_weight,
        max_weight=max_weight,
        evidences=len(evidences),
        missing=missing,
        top_anchors=top
    )


def _format_missing_comments(missing: List[Dict[str, Any]], max_items: int = 3) -> str:
    
    if not missing:
        return "OK"
    # Nuevo: missing puede ser lista[str]
    if isinstance(missing, list) and missing and isinstance(missing[0], str):
        return "- " + "\n- ".join(missing)
    ...

    parts = []
    for m in missing[:max_items]:
        gl = m.get("expected_globs", [])
        hint = m.get("hint", m["evidence_id"])
        where = f" (p.ej. {gl[0]})" if gl else ""
        parts.append(f"- {hint}{where}")
    if len(missing) > max_items:
        parts.append(f"... +{len(missing) - max_items} más")
    return " ".join(parts)


def print_table_markdown(summaries: List[LevelSummary]) -> None:
    print("\n| Nivel | Descripción | % cumplimiento | Falta / Comentarios |")
    print("|---:|---|---:|---|")
    for s in summaries:
        pct = round(s.score * 100, 1)
        comments = _format_missing_comments(s.missing)
        print(f"| {s.level} | {s.name} | {pct}% | {comments} |")
    print("")


def print_table_csv(summaries: List[LevelSummary]) -> None:
    print("nivel,descripcion,porcentaje,comentarios")
    for s in summaries:
        pct = round(s.score * 100, 1)
        comments = _format_missing_comments(s.missing).replace('"', '""')
        print(f'{s.level},"{s.name}",{pct},"{comments}"')

def _yaml_files(root: Path):
    for p in root.rglob("*.yaml"):
        yield p
    for p in root.rglob("*.yml"):
        yield p


def _load_yaml(path: Path):
    if yaml is None:
        return None
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None


def _any_domain_cfgs(root: Path) -> list[tuple[str, dict]]:
    """
    Domain YAMLs: heurística por claves estructurales (NO strings en código).
    """
    out = []
    if yaml is None:
        return out
    for p in _yaml_files(root):
        data = _load_yaml(p)
        if isinstance(data, dict) and (
            "problem_id" in data or "factory" in data or "search_space" in data or "optimizer" in data
        ):
            out.append((str(p.relative_to(root)), data))
    return out


def _has_nonempty_files_under(root: Path, rel_dir: str, exts=(".json", ".jsonl")) -> bool:
    d = root / rel_dir
    if not d.exists() or not d.is_dir():
        return False
    for f in d.rglob("*"):
        if f.is_file() and f.suffix.lower() in exts and f.stat().st_size > 0:
            return True
    return False


def _has_any_file(root: Path, rel_paths: list[str]) -> bool:
    return any((root / rp).exists() for rp in rel_paths)


def check_mapa9_operational(root: Path) -> tuple[float, list[str]]:
    """
    MapA-9 operativo (sin strings):
      - Requiere: config YAML de auditoría + config YAML de gobernanza + artefactos en disco.
      - Opcional: optimizer audit artifacts / run manifests (sube score si existen).
    Devuelve (score_0_1, missing_messages).
    """

    missing = []
    score = 0.0

    domain_cfgs = _any_domain_cfgs(root)

    # 1) Política YAML de auditoría habilitada (requerido)
    audit_cfg_ok = False
    for _, d in domain_cfgs:
        audit = (d.get("audit") or {}).get("decision_events") or {}
        if bool(audit.get("enabled", False)):
            audit_cfg_ok = True
            break
    if not audit_cfg_ok:
        missing.append("Falta policy YAML: audit.decision_events.enabled=true en algún domain.yaml.")
    else:
        score += 0.15

    # 2) Política YAML de gobernanza (requerido en MapA-9): bloque governance con al menos 1 regla de veto/override
    # (ej.: max_risk, max_decisions_per_hour, shadow_mode, allow_live, rollback_policy)
    governance_cfg_ok = False
    for _, d in domain_cfgs:
        gov = d.get("governance") or d.get("decision_governance") or {}
        if isinstance(gov, dict) and len(gov.keys()) > 0:
            governance_cfg_ok = True
            break
    if not governance_cfg_ok:
        missing.append("Falta policy YAML de gobernanza: bloque 'governance:' con reglas (veto/override).")
    else:
        score += 0.15

    # 3) Artefactos de auditoría generados en disco (requerido)
    # rutas típicas de tu proyecto
    artifacts_ok = (
        _has_nonempty_files_under(root, "cache/audit/decision_events")
        or _has_nonempty_files_under(root, "cache/audit/pattern_events")
        or _has_nonempty_files_under(root, "cache/audit/decision_events/v1")
        or _has_nonempty_files_under(root, "cache/audit/pattern_events/v1")
    )
    if not artifacts_ok:
        missing.append("No hay evidencia operativa: no se encontraron artefactos en cache/audit/** (json/jsonl no vacíos).")
    else:
        score += 0.40

    # 4) Evidencia de auditoría del optimizador / lineage (muy recomendable MapA-9)
    optimizer_audit_ok = (
        _has_nonempty_files_under(root, "cache/audit/optimizer")
        or _has_nonempty_files_under(root, "cache/audit/optimizer_audit")
        or _has_nonempty_files_under(root, "cache/audit/runs")
    )
    if not optimizer_audit_ok:
        missing.append("Recomendado: faltan artefactos de lineage/run: cache/audit/optimizer* o cache/audit/runs.")
    else:
        score += 0.15

    # 5) Persistencia de lifecycle/estado de políticas (muy recomendable MapA-9)
    # No miramos strings en .py; miramos “soportes” persistentes típicos.
    lifecycle_store_ok = _has_any_file(root, [
        "cache/policies/policy_registry.json",
        "cache/policies/policies.json",
        "cache/governance/policy_states.json",
        "cache/governance/policies.json",
    ])
    if not lifecycle_store_ok:
        missing.append("Recomendado: falta store persistente de lifecycle (policy_registry/policy_states en cache/**).")
    else:
        score += 0.15

    # Cap final
    score = max(0.0, min(1.0, score))

    # Regla dura: si no hay artefactos, MapA-9 operativo queda en 0 (o muy bajo si quieres)
    if not artifacts_ok:
        score = 0.0

    return score, missing

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=str, default=".", help="Raíz del repo/proyecto")
    ap.add_argument("--out", type=str, default="mapa_audit.json", help="Salida JSON completa")
    ap.add_argument("--exclude", type=str, nargs="*", default=DEFAULT_EXCLUDES)
    ap.add_argument("--table", choices=["md", "csv", "none"], default="md", help="Imprime tabla final")
    ap.add_argument("--print-details", action="store_true", help="Imprime evidencias (primeras 200)")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    files = iter_files(root, excludes=args.exclude)

    all_evidences: List[Evidence] = []
    summaries: List[LevelSummary] = []

    for level in range(0, 10):
        evs = scan_level(root, files, level)
        all_evidences.extend(evs)
        summaries.append(score_level(root, level, evs))


    # Tabla final (lo que pides)
    if args.table == "md":
        print_table_markdown(summaries)
    elif args.table == "csv":
        print_table_csv(summaries)

        # -----------------------------
    # Post-gates conservadores (anti falsos positivos)
    # -----------------------------
    domains = load_domain_yamls(root)

    # Gate MapA-5: decision_schedule real (YAML + code)
    # - YAML: decision_schedule existe
    # - Code: DecisionScheduler.gate + apply_decision_mode_tri aparecen en algún .py
    py_text = ""
    for p in root.rglob("*.py"):
        if any(part in str(p) for part in args.exclude):
            continue
        t = read_text_safe(p)
        if t:
            py_text += "\n" + t

    has_scheduler = bool(re.search(r"DecisionScheduler", py_text)) and bool(re.search(r"\.gate\(", py_text))
    has_apply_tri = bool(re.search(r"apply_decision_mode_tri", py_text))

    has_ds_yaml = False
    for _, d in domains:
        ds = d.get("decision_schedule")
        if isinstance(ds, dict) and ("type" in ds) and ("mode" in ds):
            has_ds_yaml = True
            break

    # Si no cumple gate, cap MapA-5 a <= 0.33 (capacidad parcial)
    for s in summaries:
        if s.level == 5:
            if not (has_ds_yaml and has_scheduler and has_apply_tri):
                s.score = min(s.score, 0.33)

    # Gate MapA-9: auditoría operativa (artefactos)
    # Requiere que exista cache/audit/decision_events (o equivalente) con ficheros json/jsonl
    audit_ok = (
        has_any_files_under(root, "cache/audit/decision_events")
        or has_any_files_under(root, "cache/audit/pattern_events")
        or has_any_files_under(root, "cache\\audit\\decision_events")
        or has_any_files_under(root, "cache\\audit\\pattern_events")
    )

    for s in summaries:
        if s.level == 9:
            # sin artefactos -> sólo capacidad parcial
            if not audit_ok:
                s.score = min(s.score, 0.25)

    # Detalle opcional
    if args.print_details:
        print("\n=== Evidence Details (first 200) ===\n")
        for e in all_evidences[:200]:
            print(f"[MapA{e.mapa_level}] {e.evidence_id} w={e.weight} :: {e.file}:{e.line} :: {e.snippet}")

    # JSON de salida con todo
    payload = {
        "root": str(root),
        "excluded": args.exclude,
        "summary": [asdict(s) for s in summaries],
        "evidences": [asdict(e) for e in all_evidences],
    }

    out_path = Path(args.out).resolve()
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote JSON: {out_path}\n")


if __name__ == "__main__":
    main()
