# plugins/inversionL2/evaluator.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict
import numpy as np
import pandas as pd
import json
import hashlib

from core.governance.decision_schedule import DecisionScheduler, TimeGridSchedule, apply_decision_mode_tri
from core.artifacts.decision_event_logger import DecisionEventLogger, DecisionEventLoggerConfig

@dataclass
class _PolicyMarketData:
    mid_prices: np.ndarray
    bid_volume: np.ndarray
    ask_volume: np.ndarray

@dataclass
class InvestmentEvaluator:
    domain: Dict[str, Any]
    dataset: Any  # puede ser df o dict con df
    dataset_desc: Dict[str, Any]

    def _get_df(self) -> pd.DataFrame:
        if isinstance(self.dataset, pd.DataFrame):
            return self.dataset
        if isinstance(self.dataset, dict) and "df" in self.dataset:
            return self.dataset["df"]
        raise TypeError("dataset must be a DataFrame or dict with key 'df'")

    def _signal_from_flat(self, *, params: Dict[str, Any], imb: pd.Series, context: Dict[str, Any]) -> np.ndarray:
        """
        Flat params vienen del search_space YAML:
        - rules: 'order_imbalance' | 'absorption'
        - order_imbalance.theta, order_imbalance.k
        - absorption.theta, absorption.k
        - compose_ops (a futuro)
        - horizon (a nivel root)
        """
        rule = params.get("rules", "order_imbalance")

        if rule == "order_imbalance":
            theta = float(params.get("order_imbalance.theta", 0.0))
            # k NO afecta aquí porque imb ya fue calculado con k (tu evaluador usa 'k' para top-k del libro)
            # Si quieres que k sea parte de la señal, debes recomputar imb por candidato (caro). De momento:
            # usa k fijo del evaluador o pásalo a la parte que computa imb.
        elif rule == "absorption":
            theta = float(params.get("absorption.theta", 0.0))
        else:
            theta = 0.0

        v = imb.values
        sig = np.zeros(len(v), dtype=float)
        sig[v > theta] = 1.0
        sig[v < -theta] = -1.0
        return sig

    def _signal_from_ast(self, *, ast: Dict[str, Any], imb: pd.Series, context: Dict[str, Any]) -> np.ndarray:
        """
        AST params vienen de tu decision_language (policy + left/right).
        Leaves: 'order_imbalance'/'absorption' con theta/k/horizon.
        Internal: 'AND'/'OR'.
        """
        pol = ast.get("policy")

        # leaf
        if pol in ("order_imbalance", "absorption"):
            theta = float(ast.get("theta", 0.0))
            v = imb.values
            sig = np.zeros(len(v), dtype=float)
            sig[v > theta] = 1.0
            sig[v < -theta] = -1.0
            return sig

        # binary combinators
        if pol in ("AND", "OR"):
            left = self._signal_from_ast(ast=ast["left"], imb=imb, context=context)
            right = self._signal_from_ast(ast=ast["right"], imb=imb, context=context)

            # AND: sólo señal si ambos no son 0; si difieren en signo -> 0
            if pol == "AND":
                out = np.zeros_like(left)
                both = (left != 0.0) & (right != 0.0)
                same = both & (np.sign(left) == np.sign(right))
                out[same] = np.sign(left[same])
                return out

            # OR: señal si alguno no es 0; si ambos no 0 y difieren -> 0 (conservador)
            out = np.zeros_like(left)
            any_ = (left != 0.0) | (right != 0.0)
            out[any_] = np.sign(left[any_] + right[any_])
            # si conflicto (sum=0 con ambos no 0) queda 0
            return out

        # unknown policy -> abstain
        return np.zeros(len(imb), dtype=float)

    def _load_decision_schedule(self) -> TimeGridSchedule:
        """
        domain.yaml → decision_schedule:
          decision_schedule: {type: time_grid, seconds: 180, mode: hold|sample}
        """
        ds = self.domain.get("decision_schedule") or {}
        seconds = int(ds.get("seconds", 180))
        mode = str(ds.get("mode", "hold")).lower()
        if mode not in ("sample", "hold"):
            mode = "hold"
        return TimeGridSchedule(seconds=seconds, mode=mode)

    def _should_audit_decisions(self) -> bool:
        """
        domain.yaml → audit.decision_events.enabled
        """
        audit = self.domain.get("audit", {}).get("decision_events", {})
        return bool(audit.get("enabled", True))
    
    def _decision_audit_mode(self) -> str:
        audit = self.domain.get("audit", {}).get("decision_events", {})
        if not bool(audit.get("enabled", True)):
            return "off"
        return str(audit.get("mode", "all")).lower()
    
    def _trend_up_mask(self, mid: pd.Series, n: int, strict: bool) -> np.ndarray:
        midv = mid.values.astype(np.float64)
        N = len(midv)
        mask = np.zeros(N, dtype=bool)
        if N == 0 or n < 1:
            return mask

        if strict:
            # no hay caídas en los últimos n increments (d>=0)
            d = np.diff(midv)
            nonneg = (d >= 0)
            k = n
            if len(nonneg) >= k:
                csum = np.cumsum(nonneg.astype(np.int32))
                win = csum[k-1:] - np.concatenate(([0], csum[:-k]))
                ok = (win == k)
                mask[k:] = ok
        else:
            # neto positivo: mid[t] - mid[t-n] > 0
            k = n
            if N > k:
                mask[k:] = (midv[k:] - midv[:-k]) > 0

        return mask

    def evaluate(self, *, params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        df = self._get_df().copy()

        # ---- DEBUG 1: dataset shape & columns ----
        """
        print("DBG[df] shape:", df.shape)
        print("DBG[df] cols:", list(df.columns))
        print("DBG[df] head:", df.head(3).to_dict("records"))
        print("DBG[df] side uniques:", sorted(df["side"].dropna().unique().tolist())[:20])
        print("DBG[df] fecha sample:", df["fecha"].head(3).tolist() if "fecha" in df.columns else None)
        """

        horizon = int(context.get("horizon") or params.get("horizon") or 3)

        # ---------------------------
        # 0) Normalización mínima
        # ---------------------------
        if "fecha" not in df.columns:
            return {"profit": 0.0, "risk": 0.0, "frequency": 0.0, "reason": "missing_fecha", "valid": False}

        df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
        df = df.dropna(subset=["fecha"])

        for col in ("priceL2", "sizeL2", "side"):
            if col not in df.columns:
                return {"profit": 0.0, "risk": 0.0, "frequency": 0.0, "reason": f"missing_{col}", "valid": False}

        df["priceL2"] = pd.to_numeric(df["priceL2"], errors="coerce")
        df["sizeL2"] = pd.to_numeric(df["sizeL2"], errors="coerce")
        df = df.dropna(subset=["priceL2", "sizeL2", "side"])

        # orden estable para groupby y para returns
        df = df.sort_values(["fecha", "side"])

        # ---------------------------
        # 1) Detectar encoding de side
        # ---------------------------
        side_vals = sorted(set(df["side"].dropna().unique().tolist()))
        if len(side_vals) < 2:
            # No hay ambos lados -> no hay midprice real -> returns degenerados
            return {"profit": 0.0, "risk": 0.0, "frequency": 0.0, "reason": "only_one_side_in_data", "valid": False}

        if set(side_vals).issubset({0, 1}):
            bid_side, ask_side = 1, 0
        elif set(side_vals).issubset({1, 2}):
            bid_side, ask_side = 1, 2
        elif set(side_vals).issubset({-1, 1}):
            bid_side, ask_side = 1, -1
        else:
            # Si llegan valores raros (p.ej. 3,4) lo tratamos como no soportado
            return {"profit": 0.0, "risk": 0.0, "frequency": 0.0, "reason": f"unsupported_side_values:{side_vals}", "valid": False}


        bid = df[df["side"] == bid_side]
        ask = df[df["side"] == ask_side]
        if bid.empty or ask.empty:
            return {"profit": 0.0, "risk": 0.0, "frequency": 0.0, "reason": "missing_bid_or_ask", "valid": False}
        """
        print("DBG[sides] bid_side:", bid_side, "ask_side:", ask_side)
        print("DBG[sides] bid rows:", len(bid), "ask rows:", len(ask))
        print("DBG[sides] bid fechas:", bid["fecha"].nunique(), "ask fechas:", ask["fecha"].nunique())
        """
        # ---------------------------
        # 2) Midprice por timestamp
        # ---------------------------
        # robusto: bids max(price), asks min(price)
        best_bid = bid.groupby("fecha")["priceL2"].max()
        best_ask = ask.groupby("fecha")["priceL2"].min()

        mid = ((best_bid + best_ask) / 2.0).dropna().sort_index()

        #print("DBG[mid] best_bid n:", int(best_bid.shape[0]), "best_ask n:", int(best_ask.shape[0]))
        #print("DBG[mid] mid n:", int(mid.shape[0]))
        if len(mid) > 0:
            mid_vals = mid.values
            #print("DBG[mid] first/last:", float(mid_vals[0]), float(mid_vals[-1]))
            #print("DBG[mid] std:", float(np.std(mid_vals)))
            #print("DBG[mid] uniq:", int(pd.Series(mid_vals).nunique()))
            #print("DBG[mid] head:", mid.head(5).to_dict())

        # ---------------------------
        # Detectar si params es AST (leaf o tree)
        # ---------------------------
        is_policy = isinstance(params, dict) and ("policy" in params)
        is_tree = is_policy and (("left" in params) or ("right" in params))

        # k dinámico por candidato (funciona para leaf y tree)
        if is_policy:
            def _max_k(node):
                p = node.get("policy")
                if p in ("AND", "OR"):
                    return max(_max_k(node["left"]), _max_k(node["right"]))
                return int(node.get("k", 1))
            k = _max_k(params)
        else:
            rule = params.get("rules", "order_imbalance")
            k = int(params.get(f"{rule}.k", 1))

        # ---------------------------
        # 3) Imbalance top-k por precio (NO por position)
        # ---------------------------
        # bids: k precios más altos; asks: k precios más bajos
        bid_k = bid.groupby("fecha", group_keys=False).apply(lambda x: x.nlargest(k, "priceL2"))
        ask_k = ask.groupby("fecha", group_keys=False).apply(lambda x: x.nsmallest(k, "priceL2"))

        bid_sz = bid_k.groupby("fecha")["sizeL2"].sum()
        ask_sz = ask_k.groupby("fecha")["sizeL2"].sum()

        denom = (bid_sz + ask_sz).replace(0.0, np.nan)
        imb = ((bid_sz - ask_sz) / denom).dropna().sort_index()

        #print("DBG[imb] imb n:", int(imb.shape[0]))
        if len(imb) > 0:
            v = imb.values
            #print("DBG[imb] min/max/std:", float(np.min(v)), float(np.max(v)), float(np.std(v)))
            #print("DBG[imb] head:", imb.head(5).to_dict())

        # ---------------------------
        # 4) Alinear índices
        # ---------------------------
        idx = mid.index.intersection(imb.index)
        mid = mid.loc[idx]
        imb = imb.loc[idx]
        bid_sz = bid_sz.reindex(idx)
        ask_sz = ask_sz.reindex(idx)

        if len(mid) <= horizon + 2:
            return {"profit": 0.0, "risk": 0.0, "frequency": 0.0, "reason": "not_enough_points", "valid": False}

        # 5) Señal raw
        #  - Modo A: policy_id (policy class del plugin) -> produce bool LONG-only
        #  - Modo B: AST/flat actuales -> tri {-1,0,+1}
        policy_id = params.get("policy_id") if isinstance(params, dict) else None

        # Gobernanza MapA 9: allowlist opcional desde domain.yaml
        pol_cfg = self.domain.get("policies") or {}
        allowed_ids = pol_cfg.get("allowed_ids") or []
        default_id = pol_cfg.get("default_id")

        if not policy_id and default_id:
            policy_id = default_id

        if policy_id and allowed_ids and policy_id not in allowed_ids:
            return {"profit": 0.0, "risk": 0.0, "frequency": 0.0, "reason": f"policy_not_allowed:{policy_id}", "valid": False}

        policy_class = None
        policy_code_hash = None

        if policy_id:
            # --- Modo A (policy class) ---
            try:
                PolicyCls = POLICY_REGISTRY[policy_id]
            except KeyError:
                return {"profit": 0.0, "risk": 0.0, "frequency": 0.0, "reason": f"unknown_policy_id:{policy_id}", "valid": False}

            policy_class = f"{PolicyCls.__module__}.{PolicyCls.__name__}"
            try:
                policy_src = inspect.getsource(PolicyCls).encode("utf-8")
                policy_code_hash = hashlib.sha256(policy_src).hexdigest()
            except Exception:
                policy_code_hash = None  # no rompemos ejecución si no hay source

            market_data = _PolicyMarketData(
                mid_prices=mid.values.astype(np.float64),
                bid_volume=bid_sz.values.astype(np.float64),
                ask_volume=ask_sz.values.astype(np.float64),
            )

            policy = PolicyCls(**params)
            out_bool = np.asarray(policy.decide_series(market_data), dtype=bool)

            # LONG-only: raw_signal tri -> 1 si True, 0 si False
            raw_signal = out_bool.astype(np.float64)

        else:
            # --- Modo B (tu comportamiento actual) ---
            if is_policy:
                raw_signal = self._signal_from_ast(ast=params, imb=imb, context=context)
            else:
                raw_signal = self._signal_from_flat(params=params, imb=imb, context=context)

            raw_signal = np.asarray(raw_signal, dtype=np.float64)

            # ---------------------------
            # 5.A) Gates (solo máscaras; NO aplicar a raw_signal aquí)
            # ---------------------------
            trend_enabled = bool(params.get("gate.trend.enabled", False))
            imb_gate_enabled = bool(params.get("gate.imbalance.enabled", False))

            trend_mask = None
            imb_mask = None

            if trend_enabled:
                n = int(params.get("gate.trend.n", 5))
                strict = bool(params.get("gate.trend.strict", True))
                trend_mask = self._trend_up_mask(mid=mid, n=n, strict=strict)  # np.ndarray[bool]

            if imb_gate_enabled:
                delta = float(params.get("gate.imbalance.delta", 0.25))
                mode = str(params.get("gate.imbalance.mode", "abs")).lower()

                v = imb.values.astype(np.float64)
                if mode == "abs":
                    imb_mask = (np.abs(v) >= delta)
                elif mode == "sell":
                    imb_mask = (v <= (-delta))
                elif mode == "buy":
                    imb_mask = (v >= delta)
                else:
                    return {"profit": 0.0, "risk": 0.0, "frequency": 0.0, "reason": f"unknown_imbalance_gate_mode:{mode}", "valid": False}

            imb_gate_enabled = bool(params.get("gate.imbalance.enabled", False))
            imb_mask = None

            if imb_gate_enabled:
                delta = float(params.get("gate.imbalance.delta", 0.25))
                mode = str(params.get("gate.imbalance.mode", "abs")).lower()

                v = imb.values.astype(np.float64)
                if mode == "abs":
                    imb_mask = (np.abs(v) >= delta)
                elif mode == "sell":
                    imb_mask = (v <= (-delta))
                elif mode == "buy":
                    imb_mask = (v >= delta)
                else:
                    return {"profit": 0.0, "risk": 0.0, "frequency": 0.0, "reason": f"unknown_imbalance_gate_mode:{mode}", "valid": False}

                raw_signal = np.where(imb_mask, raw_signal, 0.0)


        # 5.1) Decision schedule (gating)
        schedule = self._load_decision_schedule()
        scheduler = DecisionScheduler(schedule)
        timestamps = list(mid.index)  # ya alineado con imb
        gate = scheduler.gate(timestamps)

        # ---------------------------
        # 5.1.A) Effective gate (MapA 9): schedule AND gates
        # Esto evita que "hold" mantenga posición cuando el gate no lo permite.
        # ---------------------------
        effective_gate = gate.copy()
        if trend_mask is not None:
            effective_gate = effective_gate & trend_mask
        if imb_mask is not None:
            effective_gate = effective_gate & imb_mask

        # señal final gobernada por schedule usando effective_gate
        signal = apply_decision_mode_tri(raw_signal=raw_signal, gate=effective_gate, mode=schedule.mode)

        # seguridad: fuera del gate, no hay posición (crítico con mode=hold)
        signal = np.where(effective_gate, signal, 0.0)

        
        if self.domain.get("debug", {}).get("schedule", False):    
            # ---- DEBUG decision_schedule ----
            print("DBG[schedule] seconds:", schedule.seconds, "mode:", schedule.mode)
            print("DBG[schedule] gate_true_ratio:", float(np.mean(gate)))
            print("DBG[schedule] raw_nonzero_ratio:", float(np.mean(raw_signal != 0.0)))
            print("DBG[schedule] final_nonzero_ratio:", float(np.mean(signal != 0.0)))
            # --------------------------------

        # 5.2) Auditoría por snapshot (MapA 9)
        audit_mode = self._decision_audit_mode()
        if audit_mode == "all":
            params_json = json.dumps(params, sort_keys=True, ensure_ascii=False)
            params_hash = hashlib.sha256(params_json.encode("utf-8")).hexdigest()

            domain_json = json.dumps(self.domain, sort_keys=True, ensure_ascii=False)
            domain_hash = hashlib.sha256(domain_json.encode("utf-8")).hexdigest()

            dataset_id = context.get("dataset_id")
            problem_id = context.get("problem_id", "inversionL2")

            logger_cfg = DecisionEventLoggerConfig(root_dir="cache/audit/decision_events/v1")

            # spread aproximado (best_ask - best_bid), alineado con idx
            spread_series = (best_ask.loc[idx] - best_bid.loc[idx]).reindex(idx)

            with DecisionEventLogger(logger_cfg) as log:
                log.write_run_meta({
                    "problem_id": problem_id,
                    "dataset_id": dataset_id,
                    "params_hash": params_hash,
                    "domain_hash": domain_hash,
                    "schedule": {"type": "time_grid", "seconds": schedule.seconds, "mode": schedule.mode},
                    "horizon": int(horizon),
                    "gates": {
                        "trend": {
                            "enabled": bool(params.get("gate.trend.enabled", False)),
                            "n": int(params.get("gate.trend.n", 0) or 0),
                            "strict": bool(params.get("gate.trend.strict", False)),
                        },
                        "imbalance": {
                            "enabled": bool(params.get("gate.imbalance.enabled", False)),
                            "delta": float(params.get("gate.imbalance.delta", 0.0) or 0.0),
                            "mode": str(params.get("gate.imbalance.mode", "abs")),
                        },
                    },
                    "effective_gate_true_ratio": float(np.mean(effective_gate)),
                })

                imb_vals = imb.values.astype(float)
                mid_vals_for_log = mid.values.astype(float)
                spread_vals = spread_series.values.astype(float)

                for i, ts in enumerate(timestamps):

                    if self.domain.get("debug", {}).get("gates", False):
                        print("DBG[gates]", {k: params.get(k) for k in [
                            "gate.trend.enabled","gate.trend.n","gate.trend.strict",
                            "gate.imbalance.enabled","gate.imbalance.delta","gate.imbalance.mode"
                        ]})

                    rs = float(raw_signal[i])
                    g = bool(gate[i])
                    fs = float(signal[i])

                    if not g:
                        reason = "BLOCKED_BY_SCHEDULE"
                    else:
                        reason = "ALLOWED_FIRE" if rs != 0.0 else "ALLOWED_NOFIRE"

                    log.log({
                        "ts": pd.Timestamp(ts).isoformat(),
                        "i": int(i),
                        "policy_id": policy_id,
                        "raw_signal": rs,
                        "gate": g,
                        "final_signal": fs,
                        "reason_code": reason,
                        "features": {
                            "imbalance": float(imb_vals[i]),
                            "spread": float(spread_vals[i]),
                            "mid": float(mid_vals_for_log[i]),
                        },
                        "gate_schedule": bool(gate[i]),
                        "gate_trend": (bool(trend_mask[i]) if trend_mask is not None else None),
                        "gate_imbalance": (bool(imb_mask[i]) if imb_mask is not None else None),
                        "gate_effective": bool(effective_gate[i]),

                    })



        # ---------------------------
        # 6) Retorno a horizon
        # ---------------------------
        mid_vals = mid.values
        ret = (mid_vals[horizon:] - mid_vals[:-horizon]) / mid_vals[:-horizon]
        sig = signal[:-horizon]

        decision_rate = float(np.mean(effective_gate[:-horizon])) if len(sig) else 0.0
        exposure = float(np.mean(sig != 0.0)) if len(sig) else 0.0

        pnl = sig * ret

        freq = float(np.mean(sig != 0.0)) if len(sig) else 0.0
        profit = float(np.mean(pnl)) if len(pnl) else 0.0
        risk = float(np.std(pnl)) if len(pnl) else 0.0

        # Debug opcional (si quieres activarflo por YAML luego)
        # print("SANITY mid_std", float(np.std(mid_vals)), "ret_std", float(np.std(ret)), "freq", freq)
        metrics = {
            "profit": profit,
            "risk": risk,
            "frequency": exposure,          # frecuencia real de disparo / trade_rate
            "decision_rate": decision_rate, # informativo (cadencia del schedule)
            "exposure": exposure,
            "valid": True,
        }

        metrics["reason"] = None
        metrics["ev_net"] = metrics["profit"]

        # y si quieres invalidar:
        if exposure == 0.0:
            metrics["valid"] = False
            metrics["reason"] = "no_exposure"
        return metrics



def make_evaluator(*, domain: Dict[str, Any], dataset: Dict[str, Any], dataset_desc: Dict[str, Any]) -> InvestmentEvaluator:
    return InvestmentEvaluator(domain=domain, dataset=dataset, dataset_desc=dataset_desc)
