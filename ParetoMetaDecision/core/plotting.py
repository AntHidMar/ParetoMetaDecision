# core/plotting.py

import matplotlib.pyplot as plt

def plot_utility_evolution(df):
    plt.figure()
    plt.plot(df["cycle"], df["utility"])
    plt.xlabel("Optimization cycle")
    plt.ylabel("Utility")
    plt.title("Utility evolution during optimization")
    plt.show()


def plot_frequency_vs_return(df):
    plt.figure()
    plt.scatter(df["frequency"], df["mean_return"])
    plt.xlabel("Frequency")
    plt.ylabel("Mean return")
    plt.title("Frequency vs Mean Return")
    plt.show()

def plot_pareto(points, pareto, title):
    plt.figure()
    plt.scatter(
        [p["frequency"] for p in points],
        [p["mean_return"] for p in points],
        alpha=0.3,
        label="Evaluated"
    )
    plt.scatter(
        [p["frequency"] for p in pareto],
        [p["mean_return"] for p in pareto],
        color="red",
        label="Pareto front"
    )
    plt.xlabel("Frequency")
    plt.ylabel("Mean return")
    plt.title(title)
    plt.legend()
    plt.show()

def plot_price_with_events(
    dates,
    mid_price,
    signal,
    returns,
    title="Price evolution with rule events"
):
    df = pd.DataFrame({
        "fecha": dates,
        "mid_price": mid_price,
        "signal": signal,
        "ret": returns
    })

    df = df[df["signal"] & df["ret"].notna()].copy()

    if df.empty:
        print("⚠ No hay eventos para visualizar")
        return

    df["result"] = np.where(df["ret"] > 0, "Win", "Loss")

    fig = go.Figure()

    # Precio
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=mid_price,
            mode="lines",
            name="Mid Price",
            line=dict(color="black", width=1)
        )
    )

    # Eventos
    fig.add_trace(
        go.Scatter(
            x=df["fecha"],
            y=df["mid_price"],
            mode="markers",
            name="Rule events",
            marker=dict(
                size=8,
                color=np.where(df["result"] == "Win", "green", "red")
            ),
            hovertemplate=(
                "Fecha: %{x}<br>"
                "Precio: %{y:.2f}<br>"
                "Retorno: %{customdata[0]:.6f}<br>"
                "Resultado: %{customdata[1]}<extra></extra>"
            ),
            customdata=np.stack([df["ret"], df["result"]], axis=1)
        )
    )

    fig.update_layout(
        title=title,
        xaxis_title="Fecha",
        yaxis_title="Precio",
        template="plotly_white",
        height=600
    )

    fig.show()

def show_utility_diagram(results_df, best=None):
    """
    results_df: DataFrame con columnas al menos: mean_return, frequency, utility
    best: dict opcional para resaltar el mejor punto
    """
    # Si utility no existe, aquí es donde se calcula (fuente única de verdad)
    if "utility" not in results_df.columns:
        results_df = results_df.copy()
        results_df["utility"] = compute_utility(results_df)  # usa tu función existente

    plt.figure()
    plt.plot(results_df["utility"].values)
    plt.title("Utility over evaluations")
    plt.xlabel("Evaluation index")
    plt.ylabel("Utility")

    if best is not None and "utility" in best:
        # marca el best si puedes obtener su índice o simplemente una línea horizontal
        plt.axhline(best["utility"])

    plt.show()