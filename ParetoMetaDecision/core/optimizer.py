# core/optimizer.py

from __future__ import annotations

import json
from collections import defaultdict
from core.optimization_tracker import OptimizationTracker
#from core.optimizers.grid import GridSearch
from core.optimizers.factory import build_candidate_generator
from core.live_pareto_plot import ParetoLivePlot
from core.pareto import pareto_front
from core.problem import Problem
from core.decision_language import params_to_ast
from core.context import context_key
from core.artifacts.store import ArtifactStore
from core.decision_language.registry import LanguageRegistry, LanguageId
from core.decision_language.constraints import (
    LanguageConstraints,
    validate_language,
    interpretability_metrics,
)
from core.generation.base import GenerationBudget
from core.generation.combinatorial import CombinatorialGenerator
from core.generation.sentence_ledger import SentenceLedger
from core.generation.discovery_guided import GuidedDiscoveryGenerator, GuidedDiscoveryConfig
from core.utility import compute_utility, UtilitySpec
from core.generation.flat_product import flat_product_candidates, FlatProductConfig
from core.optimizers.registry import get_optimizer_spec
import inspect

LAMBDA_COST = 0.0

SEARCH_SPACE = {
    "rules": ["absorption", "order_imbalance"],

    # Absorption (más granular)
    "absorption.theta": [0.01, 0.015, 0.02, 0.025, 0.03],
    "absorption.k": [1, 2, 3, 4],

    # Order imbalance (más granular)
    "order_imbalance.theta": [0.05, 0.075, 0.1, 0.125, 0.15, 0.175],
    "order_imbalance.k": [1, 2, 3, 4],

    "compose_ops": ["AND", "OR"],
    "horizon": [3, 5, 10],
}

def _nest_composite(p: dict) -> dict:
    """
    Convierte el formato plano left./right. (si aparece) a formato anidado.
    Si no es compuesto, devuelve tal cual.
    Mantiene horizon fuera del AST.
    """
    if p.get("policy") not in ("AND", "OR"):
        return p

    # Si ya viene anidado, no tocar
    if isinstance(p.get("left"), dict) and isinstance(p.get("right"), dict):
        return p

    left = {k.replace("left.", ""): v for k, v in p.items() if k.startswith("left.")}
    right = {k.replace("right.", ""): v for k, v in p.items() if k.startswith("right.")}

    horizon = p.get("horizon", None)
    out = {"policy": p["policy"], "left": left, "right": right}
    if horizon is not None:
        out["horizon"] = horizon
    return out

def _is_degenerate_composite_params(params: dict) -> bool:
    """
    True si params representa AND(X,X) o OR(X,X) con left/right idénticos.
    Usa el formato compuesto (policy + left/right dict) que soporta params_to_ast.
    """
    p = params.get("policy")
    if p not in ("AND", "OR"):
        return False
    left = params.get("left")
    right = params.get("right")
    if not isinstance(left, dict) or not isinstance(right, dict):
        return False
    # ignorar horizon si aparece dentro (no debería)
    left2 = {k: v for k, v in left.items() if k != "horizon"}
    right2 = {k: v for k, v in right.items() if k != "horizon"}
    return left2 == right2

def _safe_context(problem, params):
    ctx = getattr(problem, "context", None)
    if ctx is None:
        return {}
    if not callable(ctx):
        return ctx

    sig = inspect.signature(ctx)
    nreq = sum(
        1 for p in sig.parameters.values()
        if p.default is inspect._empty
        and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
    )
    return ctx() if nreq == 0 else ctx(params)

def optimize_parameters(
    problem: Problem,
    domain_cfg: dict,
    plot_every: int = 1,
    pareto_axes=("utility", "utility"),
    utility_spec: UtilitySpec | None = None,
    search_space: dict | None = None,
):

    if utility_spec is None:
        utility_spec = UtilitySpec(lambda_cost=0.0)
    if search_space is None:
        search_space = SEARCH_SPACE

    spec = get_optimizer_spec(domain_cfg)

    tracker = OptimizationTracker()

    store = ArtifactStore()
    registry = LanguageRegistry(store=store)

    sentences = SentenceLedger(store=store, key="audit/language_sentences/v1/events.jsonl")

    print("\n=== DEBUG optimizer resolution ===")
    print("domain_cfg keys:", list(domain_cfg.keys()))
    print("domain_cfg['optimizer']:", domain_cfg.get("optimizer"))
    print("=================================\n")

    # MapA-9: el core no conoce optimizadores concretos.
    # Selección y construcción del optimizador 100% por YAML (factory).
    optimizer = build_candidate_generator(
        cfg=domain_cfg,
        search_space=search_space,
    )

    print("INFO optimizer:", optimizer.__class__.__name__)
    
    generator = CombinatorialGenerator(optimizer)
    budget = GenerationBudget(max_candidates=300)  # pon un int si quieres limitar

    live_plot = ParetoLivePlot()
    evaluated = []

    # Dedup por (language_key + context_key)
    seen = set()

    # Contadores
    skipped = 0
    n_eval = 0
    n_generated = 0
    n_evaluated = 0
    n_skipped_dedup = 0

    # Summary por lenguaje
    lang_summary = defaultdict(
        lambda: {
            "sentence": None,
            "states": set(),
            "horizons": set(),
            "n_events": 0,
            "violations_counts": defaultdict(int),
            "max_ast_size": 0,
            "max_ast_depth": 0,
        }
    )

    # Constraints (MapA7 soft)
    constraints = LanguageConstraints(max_depth=2, max_size=7)

    def evaluate_one(params: dict, *, origin: str, _pareto_axes=pareto_axes) -> bool:
        nonlocal skipped, n_generated, n_evaluated, n_eval, n_skipped_dedup

        params = _nest_composite(params) 
        if _is_degenerate_composite_params(params):
            skipped += 1
            return False
        
        n_generated += 1

        try:
            ast = params_to_ast(params)
        except Exception:
            # fallback: tratar params como "lenguaje plano" (sin AST)
            ast = None
            language_key = json.dumps(params, sort_keys=True)

        # Evitar degenerados AND(X,X) / OR(X,X)
        if getattr(ast, "kind", None) in ("AND", "OR"):
            children = getattr(ast, "children", None)
            if children and len(children) == 2:
                if children[0].canonical_key() == children[1].canonical_key():
                    skipped += 1
                    return False

        if ast is not None:
            language_key = ast.canonical_key()
            violations = validate_language(ast, constraints)
            interp = interpretability_metrics(ast)
            sentence = ast.to_sentence()
        else:
            violations = []
            interp = {"ast_size": 1, "ast_depth": 1}
            sentence = f"FLAT({language_key})"

        # Registry (MapA6)
        lid = LanguageId(language_key=language_key, version="v1")
        #rec = registry.upsert_ast(lid=lid, ast_dict=ast.to_dict())
        
        # Puede haber candidatos sin AST (p.ej. flat params o generación incompleta).
        if ast is not None:
            rec = registry.upsert_ast(lid=lid, ast_dict=ast.to_dict())
        else:
            # MapA-9: registramos como "flat/no-ast" sin romper el pipeline
            rec = None

        # MapA-9: el registry debe devolver un record dict; si no, no bloqueamos la ejecución
        if rec is None:
            rec = {"state": "draft", "language_key": language_key}
            
        language_state = rec.get("state", "draft")

        # Gating suave
        if language_state == "banned":
            skipped += 1
            return False

        # Contexto (fuera del AST)
        #ctx = problem.context(params) if callable(problem.context) else problem.context
        ctx = _safe_context(problem, params)
        ctx_key = context_key(ctx)

        dedup_key = f"{language_key}:{ctx_key}"
        if dedup_key in seen:
            skipped += 1
            n_skipped_dedup += 1
            return False
        seen.add(dedup_key)

        # Evaluación
        m = problem.evaluate(params, ctx)
        
        # MapA-9: normalizar contrato mínimo para que plotting/auditoría no reviente
        if isinstance(m, dict):
            if "valid" not in m:
                # Regla general: si hay reason o utility sentinela o support==0 => invalid
                if m.get("reason") in ("no_support", "governance_violation", "not_enough_points"):
                    m["valid"] = False
                elif float(m.get("support", 0.0)) <= 0.0:
                    m["valid"] = False
                else:
                    m["valid"] = True

        if n_eval == 0:
            print("DEBUG metrics keys:", sorted(list(m.keys())))
        if not isinstance(m, dict):
            raise TypeError("problem.evaluate(params) must return a dict of metrics")

        # --- Generalista: el plugin devuelve objetivos; el core deriva utility ---
        if "utility" not in m:
            # MapA9-min: si el dominio no trae utility, la derivamos de métricas comunes
            try:
                if "mean_return" in m and "frequency" in m:
                    # legacy
                    utility = compute_utility(
                        profit=m["profit"],
                        risk=m["risk"],
                        frequency=m["frequency"],
                        spec=utility_spec,
                    )
                    m["utility"] = utility
                elif "profit" in m and "risk" in m and "frequency" in m:
                    # inversionL2
                    lambda_cost = float(getattr(utility_spec, "lambda_cost", 0.0)) if utility_spec else 0.0
                    # lee lambda_risk desde YAML pasando un float suelto (ver abajo) o hardcode temporal
                    lambda_risk = float(getattr(utility_spec, "lambda_risk", 1.0)) if utility_spec else 1.0
                    m["utility"] = float(m["profit"]) - lambda_risk * float(m["risk"]) - lambda_cost * float(m["frequency"])
                else:
                    m["utility"] = 0.0
            except Exception:
                m["utility"] = 0.0

        n_evaluated += 1
        utility = float(m["utility"])
        
        if n_eval < 3:
            print("DEBUG utility calc:", m)
        

        meta = {
            "language_version": "v1",
            "optimizer": origin,
            "language_key": language_key,
            "context_key": ctx_key,
            "context": ctx,
            "language_state": language_state,
            "ast_size": int(interp["ast_size"]),
            "ast_depth": int(interp["ast_depth"]),
            "constraints": {"max_depth": constraints.max_depth, "max_size": constraints.max_size},
            "violations": violations,
            "language_sentence": sentence,
        }

        # Ledger (auditoría de oraciones)
        # --- Generalista: guardamos TODAS las métricas sin exigir claves ---
        metrics_clean = {}
        for k, v in m.items():
            # Normalización suave: castea a float/int si puede, si no conserva el valor
            if isinstance(v, bool):
                metrics_clean[k] = int(v)
            else:
                try:
                    fv = float(v)
                    # si parece entero, guárdalo como int (opcional)
                    metrics_clean[k] = int(fv) if fv.is_integer() and not isinstance(v, str) else fv
                except Exception:
                    metrics_clean[k] = v

        # Asegurar utility (ya lo haces arriba, pero por coherencia)
        metrics_clean["utility"] = float(metrics_clean.get("utility", utility))

        from core.decision_models.expected_value import expected_value
        decision_cfg = domain_cfg.get("decision_model", {})
        gain = decision_cfg.get("gain", 1.0)
        loss = decision_cfg.get("loss", 1.0)
        cost = decision_cfg.get("cost", 0.0)

        ev = expected_value(
            ppv=m.get("ppv"),
            support=m.get("support"),
            gain=gain,
            loss=loss,
            cost=cost,
        )

        m["expected_value"] = ev


        evaluated.append(
            {
                "meta": meta,
                "metrics": metrics_clean,
                "params": params,
                "horizon": params.get("horizon"),
                "utility": float(metrics_clean["utility"]),
            }
        )

        # Summary por lenguaje
        s = lang_summary[language_key]
        s["sentence"] = sentence
        s["states"].add(language_state)
        s["horizons"].add(params.get("horizon"))
        s["n_events"] += 1
        s["max_ast_size"] = max(s["max_ast_size"], int(interp["ast_size"]))
        s["max_ast_depth"] = max(s["max_ast_depth"], int(interp["ast_depth"]))
        for v in violations:
            s["violations_counts"][str(v)] += 1

        tracker.log(params=params, metrics=m, utility=utility, meta=meta)

        n_eval += 1
        if plot_every and (n_eval % plot_every == 0):
            pareto = pareto_front(evaluated, axes=_pareto_axes)
            plot_cfg = domain_cfg.get("plot", {}) or {}
            live_plot.update(evaluated=evaluated, pareto_points=pareto, cycle=n_eval, axes=_pareto_axes, plot_cfg=plot_cfg)

        return True

    # =========================
    # FASE 1: combinatoria
    # =========================
    it = list(generator.generate(problem=problem, budget=budget))
    if len(it) == 0:
        # Fallback generalista (MapA 9): search_space plano
        it = list(flat_product_candidates(search_space, FlatProductConfig(max_candidates=budget.max_candidates)))

    for params in it:
        evaluate_one(params, origin=getattr(optimizer, "id", optimizer.__class__.__name__))


    # =========================
    # FASE 2: discovery guiado
    # =========================
    evaluated_sorted = sorted(evaluated, key=lambda r: r["utility"], reverse=True)
    best_params = [r["params"] for r in evaluated_sorted]

    disc = GuidedDiscoveryGenerator(
        search_space,
        GuidedDiscoveryConfig(seed=0, max_candidates=30, top_k=10, keep_horizon=False),
    )

    for params in disc.generate(best_params=best_params):
        evaluate_one(params, origin="discovery_guided")

    # =========================
    # Persistir summary.json
    # =========================
    summary_out = {}
    for lk, s in lang_summary.items():
        summary_out[lk] = {
            "sentence": s["sentence"],
            "states": sorted(list(s["states"])),
            "horizons": sorted([h for h in s["horizons"] if h is not None]),
            "n_events": s["n_events"],
            "violations_counts": dict(s["violations_counts"]),
            "max_ast_size": s["max_ast_size"],
            "max_ast_depth": s["max_ast_depth"],
        }

    store.append_text(
        "audit/language_sentences/v1/summary.json",
        json.dumps(summary_out, ensure_ascii=False, indent=2) + "\n",
    )
    """
    print("INFO: language summary written -> cache/audit/language_sentences/v1/summary.json")
    print(f"INFO: candidates_generated = {n_generated}")
    print(f"INFO: evaluated = {n_evaluated}")
    print(f"INFO: skipped_by_dedup = {skipped} (dedup={n_skipped_dedup})")
    """
    return evaluated, tracker

def build_optimizer(cfg, search_space):
    # Alias para compatibilidad con imports existentes
    return build_candidate_generator(cfg, search_space)
