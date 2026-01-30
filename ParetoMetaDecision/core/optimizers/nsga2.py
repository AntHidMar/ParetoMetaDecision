# core/optimizers/nsga2.py
from __future__ import annotations

import copy
import json
import random
from typing import Any, Dict, List, Optional


def _normalize_leaf_policies(search_space: Dict[str, Any]) -> List[str]:
    """
    MapA-9: Normalización determinista.
    Acepta:
    - flat_rules: lista explícita (nuevo)
    - rules: lista explícita (legacy)
    - inferencia: a partir de claves '<policy>.theta' y '<policy>.k'
    """
    # 1) preferente: flat_rules explícito
    fr = search_space.get("flat_rules")
    if fr:
        return [str(x) for x in fr]

    # 2) compat: rules explícito
    rules = search_space.get("rules")
    if rules:
        return [str(x) for x in rules]

    # 3) inferencia (determinista): policies que tienen theta y k
    keys = set(search_space.keys())
    policies = set()

    for k in keys:
        if k.endswith(".theta"):
            p = k[:-len(".theta")]
            if f"{p}.k" in keys:
                policies.add(p)

    return sorted(policies)

def _make_param_domains(search_space: Dict[str, Any]) -> Dict[str, List[Any]]:
    """
    MapA-9: dominios de parámetros.
    Si viene 'parameters' (nuevo), úsalo.
    Si no, construye un dict con todas las claves listables del search_space
    excepto las de control ('rules', 'flat_rules', 'compose_ops', 'horizon', etc).
    """
    params = search_space.get("parameters")
    if isinstance(params, dict) and params:
        # copiar para evitar mutaciones externas
        return {str(k): list(v) for k, v in params.items()}

    # fallback legacy: todo lo que sea lista/tuple se considera dominio
    control = {"rules", "flat_rules", "compose_ops", "horizon", "decision_schedule", "audit", "debug", "optimizer"}
    out: Dict[str, List[Any]] = {}
    for k, v in search_space.items():
        if k in control:
            continue
        if isinstance(v, (list, tuple)) and v:
            out[str(k)] = list(v)
    return out


class NSGA2Optimizer:
    """
    Opción B (MapA-9 mínimo funcional):
    - Genera SIEMPRE candidatos en formato AST canónico (policy/left/right/params)
    - Para NSGA-II real hará falta feedback (tell). De momento genera población + offspring válidos.
    """

    id = "nsga2"

    def __init__(
        self,
        search_space: Dict[str, Any],
        max_evals: int = 500,
        seed: int = 0,
        pop_size: int = 80,
        offspring_size: int = 80,
        tournament_k: int = 2,
        crossover_rate: float = 0.9,
        mutation_rate: float = 0.2,
        max_depth: int = 4,
        max_nodes: int = 15,
    ):
        self.search_space = search_space
        self.max_evals = int(max_evals)
        self.rng = random.Random(seed)

        self.pop_size = int(pop_size)
        self.offspring_size = int(offspring_size)
        self.tournament_k = int(tournament_k)
        self.crossover_rate = float(crossover_rate)
        self.mutation_rate = float(mutation_rate)

        # Por ahora garantizamos AST “simple” (depth<=2) aunque te permitan más.
        self.max_depth = int(max_depth)
        self.max_nodes = int(max_nodes)

        # Cache de dominios de parámetros
        # Cache de dominios de parámetros (MapA-9 normalized)
        self._param_domains = _make_param_domains(self.search_space)

        # Hojas (policies terminales, MapA-9 normalized)
        self._leaf_policies = _normalize_leaf_policies(self.search_space)

        # Operadores de composición y horizontes
        self._compose_ops = list(self.search_space.get("compose_ops", []) or [])
        self._horizons = list(self.search_space.get("horizon", []) or [])


        if not self._leaf_policies:
            raise ValueError("search_space.flat_rules vacío: no puedo generar hojas")
        if not self._horizons:
            # si no está en search_space, toleramos (pero tu plugin usa horizon)
            self._horizons = [1]


    # -------------------------
    # Helpers: sampling
    # -------------------------

    def _sample_horizon(self) -> int:
        return int(self.rng.choice(self._horizons))

    def _domain_for(self, key: str) -> List[Any]:
        dom = self._param_domains.get(key)
        if dom is None:
            raise KeyError(f"Missing parameter domain for '{key}' in search_space.parameters")
        return list(dom)
    
    def _sample_leaf(self, horizon: Optional[int] = None) -> Dict[str, Any]:
        h = int(horizon if horizon is not None else self._sample_horizon())
        policy = str(self.rng.choice(self._leaf_policies))

        theta_dom_key = f"{policy}.theta"
        k_dom_key = f"{policy}.k"

        leaf: Dict[str, Any] = {
            "policy": policy,
            "theta": float(self.rng.choice(self._domain_for(theta_dom_key))),
            "horizon": h,
        }

        # k es opcional: si no hay dominio, no lo metemos (lo decide el evaluator vía context)
        try:
            k_dom = self._param_domains.get(k_dom_key)
            if k_dom is not None and len(k_dom) > 0:
                leaf["k"] = int(self.rng.choice(list(k_dom)))
        except Exception:
            # no hacemos nada: k no aplica en este dominio
            pass

        return leaf


    def _sample_ast(self) -> Dict[str, Any]:
        """
        Genera AST válido. Para evitar problemas, arrancamos con:
        - o hoja
        - o composición binaria con dos hojas (depth=2)
        """
        h = self._sample_horizon()

        # Si no hay ops de composición, devolvemos hoja
        if not self._compose_ops:
            return self._sample_leaf(horizon=h)

        # Probabilidad simple: 50% hoja, 50% AND/OR con dos hojas
        if self.rng.random() < 0.5:
            return self._sample_leaf(horizon=h)

        op = str(self.rng.choice(self._compose_ops))
        left = self._sample_leaf(horizon=h)
        right = self._sample_leaf(horizon=h)

        ast = {
            "policy": op,      # "AND" | "OR"
            "left": left,
            "right": right,
            "horizon": h,
        }
        return ast

    def _canonical_key(self, cand: Dict[str, Any]) -> str:
        return json.dumps(cand, sort_keys=True, ensure_ascii=False)

    # -------------------------
    # Variation operators (AST-safe)
    # -------------------------

    def _mutate_leaf(self, leaf: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(leaf)
        policy = out["policy"]
        h = int(out.get("horizon", self._sample_horizon()))

        # Mutación simple: cambia theta o k o policy (manteniendo dominios)
        r = self.rng.random()
        if r < 0.34:
            out["theta"] = float(self.rng.choice(self._domain_for(f"{policy}.theta")))
        elif r < 0.67:
            out["k"] = int(self.rng.choice(self._domain_for(f"{policy}.k")))
        else:
            policy2 = str(self.rng.choice(self._leaf_policies))
            out["policy"] = policy2
            out["theta"] = float(self.rng.choice(self._domain_for(f"{policy2}.theta")))
            out["k"] = int(self.rng.choice(self._domain_for(f"{policy2}.k")))
        out["horizon"] = h
        return out

    def _mutate_ast(self, ast: Dict[str, Any]) -> Dict[str, Any]:
        out = copy.deepcopy(ast)
        h = int(out.get("horizon", self._sample_horizon()))

        # Si es hoja
        if out.get("policy") not in ("AND", "OR"):
            return self._mutate_leaf(out)

        # Nodo AND/OR
        if self.rng.random() < 0.25 and self._compose_ops:
            out["policy"] = str(self.rng.choice(self._compose_ops))

        # mutar un hijo
        if self.rng.random() < 0.5:
            out["left"] = self._mutate_ast(out["left"])
        else:
            out["right"] = self._mutate_ast(out["right"])

        out["horizon"] = h
        return out

    def _crossover(self, a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
        """
        Crossover AST-safe muy simple:
        - si ambos son compuestos, intercambia left o right
        - si no, devuelve una copia de uno de los padres
        """
        A = copy.deepcopy(a)
        B = copy.deepcopy(b)

        a_comp = A.get("policy") in ("AND", "OR")
        b_comp = B.get("policy") in ("AND", "OR")

        if a_comp and b_comp:
            if self.rng.random() < 0.5:
                A["left"], B["left"] = B["left"], A["left"]
            else:
                A["right"], B["right"] = B["right"], A["right"]
            return A

        return A if self.rng.random() < 0.5 else B

    # -------------------------
    # Public API used by core: generate()
    # -------------------------

    def generate(self):
        """
        Genera candidatos AST válidos hasta max_evals.
        Nota: NSGA-II real requiere feedback (tell). Aquí damos mínimo funcional AST-safe.
        """
        seen = set()

        # 1) Población inicial
        for gen_i in range(min(self.pop_size, self.max_evals)):
            cand = self._sample_ast()
            key = self._canonical_key(cand)
            if key in seen:
                continue
            seen.add(key)

            cand["__meta__"] = {
                "optimizer": self.id,
                "generation": 0,
                "operator": "init",
                "parent_ids": [],
            }
            yield cand

        produced = len(seen)
        generation = 1

        # 2) Offspring (sin selección real aún)
        # (cuando integremos tell(), aquí vendrá torneo+rank+crowding)
        while produced < self.max_evals:
            # padres: sample aleatorio de los ya vistos (suficiente para empezar)
            parents = list(seen)
            if len(parents) < 2:
                p1 = self._sample_ast()
                p2 = self._sample_ast()
            else:
                # OJO: `seen` guarda keys, necesitamos reconstruir candidatos => no lo hacemos aquí.
                # Para mínimo funcional, volvemos a samplear. (Luego lo haremos con memoria poblacional.)
                p1 = self._sample_ast()
                p2 = self._sample_ast()

            child = p1
            op = "clone"

            if self.rng.random() < self.crossover_rate:
                child = self._crossover(p1, p2)
                op = "crossover"

            if self.rng.random() < self.mutation_rate:
                child = self._mutate_ast(child)
                op = "mutation" if op == "clone" else f"{op}+mutation"

            key = self._canonical_key(child)
            if key in seen:
                continue
            seen.add(key)
            produced += 1

            child["__meta__"] = {
                "optimizer": self.id,
                "generation": generation,
                "operator": op,
                "parent_ids": [],  # en v2: ids reales
            }
            yield child

            # “generations” simbólicas mientras no haya selección real
            if produced % max(1, self.offspring_size) == 0:
                generation += 1
