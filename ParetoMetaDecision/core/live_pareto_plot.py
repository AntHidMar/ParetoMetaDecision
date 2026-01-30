# core/live_pareto_plot.py

import pandas as pd
import plotly.express as px
import os
import webbrowser

def _scatter_generic(df, *, x_col: str, y_col: str, title: str, hover_cols: list):

        # Si no existen columnas, no dibujamos
        if x_col not in df.columns or y_col not in df.columns:
            return None

        fig = px.scatter(
            df,
            x=x_col,
            y=y_col,
            color="metrics.support" if "metrics.support" in df.columns else None,
            title=title,
            hover_name="meta.language_sentence" if "meta.language_sentence" in df.columns else None,
            hover_data={c: True for c in hover_cols if c in df.columns},
        )
        return fig


class ParetoLivePlot:
    def __init__(self, output_file="pareto_live.html", output_file2="risk_benefit_live.html"):
        self.output_file = output_file
        self.output_file2 = output_file2
        self.browser_opened = False

    
    def update(self, evaluated, pareto_points, cycle, axes=None, plot_cfg=None):

        if not evaluated:
            return

        plot_cfg = plot_cfg or {}

        # Ejes configurables (MapA9): por defecto legacy
        if axes is None:
            axes = ("frequency", "mean_return")
        x_col, y_col = axes


        df = pd.DataFrame(evaluated)

        # -----------------------------
        # Expandir campos (params/metrics/meta) para hover
        # -----------------------------
        def _flatten(d, prefix):
            if not isinstance(d, dict):
                return {}
            out = {}
            for k, v in d.items():
                key = f"{prefix}.{k}"
                if isinstance(v, (dict, list)):
                    out[key] = str(v)
                else:
                    out[key] = v
            return out

        # Si en evaluated guardas params/metrics/meta (recomendado), los expandimos.
        # Si no existen, no pasa nada.
                # Si en evaluated guardas params/metrics/meta (recomendado), los expandimos.
        # Si no existen, no pasa nada.
        expanded_cols = []
        for prefix in ("params", "metrics", "meta"):
            if prefix in df.columns:
                exp = df[prefix].apply(lambda x: _flatten(x, prefix))
                exp_df = pd.json_normalize(exp)
                expanded_cols.append(exp_df)

        if expanded_cols:
            df = pd.concat([df] + expanded_cols, axis=1)

            # Aliases: si x/y están como metrics.<k>, crea columna plana <k>
            for k in {x_col, y_col, "utility"}:
                mk = f"metrics.{k}"
                if k not in df.columns and mk in df.columns:
                    df[k] = df[mk]



        # Alias útiles si vienen en meta
        # (meta.language_key, meta.context_key, meta.context, etc. aparecerán ya como columnas)
        df = df.dropna(subset=[x_col, y_col])

        # Si los ejes no existen en df, no podemos plotear (dominio distinto / métricas distintas)
        if x_col not in df.columns or y_col not in df.columns:
            return
        if df.empty:
            return

        df["is_pareto"] = False
        if pareto_points:
            pareto_df = pd.DataFrame(pareto_points)

            # asegurar mismas columnas y filtrar nulos
            if x_col in pareto_df.columns and y_col in pareto_df.columns:
                pareto_df = pareto_df.dropna(subset=[x_col, y_col])
            else:
                pareto_df = pareto_df.iloc[0:0]  # vacía

            if x_col in df.columns and y_col in df.columns:
                df2 = df.dropna(subset=[x_col, y_col])
            else:
                return


            if not pareto_df.empty and not df2.empty:
                idx_all = df2.set_index([x_col, y_col]).index
                idx_pareto = pareto_df.set_index([x_col, y_col]).index
                df.loc[idx_all.isin(idx_pareto), "is_pareto"] = True


        # Hover: selección controlada (evita campos enormes)
        # -----------------------------
        exclude_prefixes = (
            "metrics.extra",     # metrics.extra y subclaves
        )

        def _excluded(col: str) -> bool:
            return any(col == p or col.startswith(p + ".") for p in exclude_prefixes)

        # Base columns (siempre útiles)
        hover_cols = [
            x_col,
            y_col,
            "utility",
            "is_pareto",
        ]


        # Preferir la oración del lenguaje si existe (meta.language_sentence)
        # Preferir la oración del lenguaje si existe (meta.language_sentence)
        if "meta.language_sentence" in df.columns:
            hover_cols.insert(0, "meta.language_sentence")

        # Añadir columnas expandidas (params/metrics/meta) pero filtradas
        expanded = [
            c for c in df.columns
            if (c.startswith("params.") or c.startswith("metrics.") or c.startswith("meta."))
        ]
        expanded = [c for c in expanded if not _excluded(c)]

        # Evitar duplicados manteniendo orden
        seen = set()
        hover_cols = [
            c for c in (hover_cols + expanded)
            if (c in df.columns and not (c in seen or seen.add(c)))
        ]

        #print("n evals:", len(df))
        #print("n puntos únicos profit-risk:", df[["profit","risk"]].drop_duplicates().shape[0])
        #print(df.groupby(["profit","risk"]).size().sort_values(ascending=False).head(10))
        #df = df[df["utility"] > -1e6]
        # MapA-9: filtrar inválidos si existe la columna; si no, usar heurística segura
        if "valid" in df.columns:
            df = df[df["valid"] == True]
        else:
            # fallback: descartar los sentinelas/degenerados sin romper dominios antiguos
            if "metrics.support" in df.columns:
                df = df[df["metrics.support"] > 0]
            if "utility" in df.columns:
                df = df[df["utility"] > -1e6]


        fig1 = _scatter_generic(
            df,
            x_col=x_col,
            y_col=y_col,
            title=f"Pareto evolution — {cycle} evaluations",
            hover_cols=hover_cols,
        )

        if fig1 is not None:
            html1 = fig1.to_html(full_html=True, include_plotlyjs="cdn")
            html1 = html1.replace("</head>", "<meta http-equiv='refresh' content='10'></head>")

            with open(self.output_file, "w", encoding="utf-8") as f:
                f.write(html1)

        #print("Control 0")
        #print(df)
        # 🔑 ABRIR EL NAVEGADOR SOLO UNA VEZ
        #if not self.browser_opened:
            #webbrowser.open(f"file://{os.path.abspath(self.output_file)}")
            #self.browser_opened = True

        # --- Plot 2: Risk/Benefit (Decision Model) ---
        rb_axes = plot_cfg.get("risk_benefit_axes", None)
        #print(rb_axes)

        if rb_axes and len(rb_axes) == 2:
            rb_x = rb_axes[0]
            rb_y = rb_axes[1]
        else:
            rb_x, rb_y = "ev_net", "risk"

        # Normalizamos nombres: aceptamos "ev_net" o "metrics.ev_net"
        rb_x_col = rb_x if rb_x.startswith("metrics.") else f"metrics.{rb_x}"
        rb_y_col = rb_y if rb_y.startswith("metrics.") else f"metrics.{rb_y}"

        #print("RB columns check:", rb_x_col, rb_y_col)
        #print("Available cols sample:", [c for c in df.columns if c.startswith("metrics.")][:20])

        """if rb_x_col in df.columns and rb_y_col in df.columns:
            print(df[[rb_x_col, rb_y_col]].head(5))
        else:
            print("RB metrics not available yet:", rb_x_col, rb_y_col)"""

        fig2 = _scatter_generic(
            df,
            x_col=rb_x_col,
            y_col=rb_y_col,
            title=f"Risk–Benefit — {cycle} evaluations",
            hover_cols=hover_cols,
        )

        if fig2 is not None and self.output_file2:
            html2 = fig2.to_html(full_html=True, include_plotlyjs="cdn")
            html2 = html2.replace("</head>", "<meta http-equiv='refresh' content='10'></head>")

            with open(self.output_file2, "w", encoding="utf-8") as f:
                f.write(html2)
        #print("Control 1")