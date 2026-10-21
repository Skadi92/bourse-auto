"""Graphique de tendance au format PNG, inséré dans le mail d'alerte.

Panneau haut : cours, moyenne mobile longue, bandes de Bollinger, SAR et signaux ACHAT / VENTE.
Panneau bas : histogramme MACD (positif au-dessus de zéro, négatif en dessous).
"""

import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from .signals import ACHAT, VENTE  # noqa: E402

# Palette de référence (fond clair : les clients mail n'adaptent pas les images au mode sombre).
SURFACE = "#fcfcfb"
ENCRE = "#0b0b0b"
ENCRE_SECONDAIRE = "#52514e"
ATTENUE = "#898781"
GRILLE = "#e1e0d9"
AXE = "#c3c2b7"
COURS = "#2a78d6"
POSITIF = "#2a78d6"
NEGATIF = "#e34948"
BON = "#0ca30c"
CRITIQUE = "#d03b3b"

MOIS = ["janv.", "févr.", "mars", "avr.", "mai", "juin",
        "juil.", "août", "sept.", "oct.", "nov.", "déc."]


def _format_mois(x, _pos=None) -> str:
    d = mdates.num2date(x)
    return MOIS[d.month - 1] if d.month != 1 else f"{MOIS[0]} {d.year}"


def _habiller(ax) -> None:
    ax.set_facecolor(SURFACE)
    for cote in ("top", "right", "left"):
        ax.spines[cote].set_visible(False)
    ax.spines["bottom"].set_color(AXE)
    ax.grid(axis="y", color=GRILLE, linewidth=0.6)
    ax.set_axisbelow(True)
    ax.tick_params(colors=ATTENUE, labelsize=8, length=0)
    ax.yaxis.tick_right()


def graphique(df: pd.DataFrame, jours: int = 250) -> bytes:
    """Renvoie le PNG des `jours` dernières séances (250 séances, environ un an)."""
    d = df.iloc[-jours:]
    x = d.index

    fig, (haut, bas) = plt.subplots(
        2, 1, figsize=(7, 3.8), dpi=150, sharex=True,
        gridspec_kw={"height_ratios": [3, 1], "hspace": 0.18},
    )
    fig.patch.set_facecolor(SURFACE)
    for ax in (haut, bas):
        _habiller(ax)

    haut.fill_between(x, d["bb_basse"], d["bb_haute"], color=COURS, alpha=0.10,
                      linewidth=0, label="Bandes de Bollinger")
    haut.plot(x, d["Close"], color=COURS, linewidth=1.6, label="Cours")
    if "f_mm" in d:
        haut.plot(x, d["f_mm"], color=ENCRE_SECONDAIRE, linewidth=1.0, linestyle=(0, (4, 2)),
                  label="MM200")
    # Le SAR lent est celui qui conditionne les signaux ; à défaut, le SAR standard.
    sar, nom_sar = (d["f_sar"], "SAR lent") if "f_sar" in d else (d["sar"], "SAR")
    haut.scatter(x, sar, s=2, color=ATTENUE, label=nom_sar)

    achats, ventes = d[d["signal"] == ACHAT], d[d["signal"] == VENTE]
    haut.scatter(achats.index, achats["Low"] * 0.985, marker="^", s=46, color=BON,
                 edgecolors=SURFACE, linewidths=0.8, zorder=5, label="Achat")
    haut.scatter(ventes.index, ventes["High"] * 1.015, marker="v", s=46, color=CRITIQUE,
                 edgecolors=SURFACE, linewidths=0.8, zorder=5, label="Vente")

    dernier = d["Close"].iloc[-1]
    haut.annotate(f"{dernier:,.2f}".replace(",", " ").replace(".", ","),
                  xy=(x[-1], dernier), xytext=(4, 0), textcoords="offset points",
                  va="center", fontsize=8, color=ENCRE, fontweight="bold")

    legende = haut.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=6, frameon=False,
                          fontsize=7.5, handlelength=1.4, columnspacing=1.2,
                          borderaxespad=0.2, labelcolor=ENCRE_SECONDAIRE)
    for poignee in legende.legend_handles:
        if hasattr(poignee, "set_sizes"):
            poignee.set_sizes([30])

    # Le MACD lent est celui qui conditionne les signaux ; à défaut, le MACD standard.
    lent = "f_macd_hist" in d
    hist = d["f_macd_hist"] if lent else d["macd_hist"]
    bas.bar(x, hist, width=1.0, linewidth=0, color=[POSITIF if v >= 0 else NEGATIF for v in hist])
    bas.axhline(0, color=AXE, linewidth=0.8)
    bas.set_title("Histogramme MACD lent" if lent else "Histogramme MACD", loc="left",
                  fontsize=7.5, color=ENCRE_SECONDAIRE, pad=3)
    bas.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 3, 5, 7, 9, 11]))
    bas.xaxis.set_major_formatter(_format_mois)

    tampon = io.BytesIO()
    fig.savefig(tampon, format="png", facecolor=SURFACE, bbox_inches="tight", pad_inches=0.12)
    plt.close(fig)
    return tampon.getvalue()
