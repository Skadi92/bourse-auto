"""Graphique de tendance au format PNG, inséré dans le mail d'alerte.

Panneau haut : cours, moyenne mobile longue, bandes de Bollinger, SAR et signaux ACHAT / VENTE.
Panneau bas : histogramme MACD (positif au-dessus de zéro, négatif en dessous).
"""

import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402
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
    ax.tick_params(colors=ATTENUE, labelsize=6.5, length=0, pad=2)
    ax.yaxis.tick_right()
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}".replace(".", ",")))


def graphique(df: pd.DataFrame, jours: int = 250) -> bytes:
    """Renvoie le PNG des `jours` dernières séances (250 séances, environ un an)."""
    d = df.iloc[-jours:]
    x = d.index

    fig, (haut, bas) = plt.subplots(
        2, 1, figsize=(3.6, 2.5), dpi=200, sharex=True,
        gridspec_kw={"height_ratios": [3, 1], "hspace": 0.28},
    )
    fig.patch.set_facecolor(SURFACE)
    for ax in (haut, bas):
        _habiller(ax)

    haut.fill_between(x, d["bb_basse"], d["bb_haute"], color=COURS, alpha=0.10,
                      linewidth=0, label="Bandes de Bollinger")
    haut.plot(x, d["Close"], color=COURS, linewidth=1.2, label="Cours")
    if "f_mm" in d:
        haut.plot(x, d["f_mm"], color=ENCRE_SECONDAIRE, linewidth=0.8, linestyle=(0, (4, 2)),
                  label="MM200")
    # Le SAR lent est celui qui conditionne les signaux ; à défaut, le SAR standard.
    sar, nom_sar = (d["f_sar"], "SAR lent") if "f_sar" in d else (d["sar"], "SAR")
    haut.scatter(x, sar, s=0.8, color=ATTENUE, label=nom_sar)

    achats, ventes = d[d["signal"] == ACHAT], d[d["signal"] == VENTE]
    haut.scatter(achats.index, achats["Low"] * 0.985, marker="^", s=30, color=BON,
                 edgecolors=SURFACE, linewidths=0.8, zorder=5, label="Achat")
    haut.scatter(ventes.index, ventes["High"] * 1.015, marker="v", s=30, color=CRITIQUE,
                 edgecolors=SURFACE, linewidths=0.8, zorder=5, label="Vente")

    legende = haut.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=3, frameon=False,
                          fontsize=6, handlelength=1.2, columnspacing=0.8, handletextpad=0.4,
                          labelspacing=0.2,
                          borderaxespad=0.2, labelcolor=ENCRE_SECONDAIRE)
    for poignee in legende.legend_handles:
        if hasattr(poignee, "set_sizes"):
            poignee.set_sizes([14])

    # Le MACD lent est celui qui conditionne les signaux ; à défaut, le MACD standard.
    lent = "f_macd_hist" in d
    hist = d["f_macd_hist"] if lent else d["macd_hist"]
    bas.bar(x, hist, width=1.0, linewidth=0, color=[POSITIF if v >= 0 else NEGATIF for v in hist])
    bas.axhline(0, color=AXE, linewidth=0.8)
    bas.set_title("Histogramme MACD lent" if lent else "Histogramme MACD", loc="left",
                  fontsize=6, color=ENCRE_SECONDAIRE, pad=2)
    bas.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 4, 7, 10]))
    bas.xaxis.set_major_formatter(_format_mois)

    tampon = io.BytesIO()
    fig.savefig(tampon, format="png", facecolor=SURFACE, bbox_inches="tight", pad_inches=0.06)
    plt.close(fig)
    return tampon.getvalue()
