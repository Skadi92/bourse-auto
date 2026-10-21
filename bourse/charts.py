"""Graphique de tendance au format PNG, inséré dans le mail d'alerte.

Panneau haut : cours, MM20, MM50, bandes de Bollinger, SAR (0,02) et signaux ACHAT / VENTE.
Panneau milieu : MACD (12, 26, 9), ligne MACD et ligne de signal.
Panneau bas : RSI, avec les seuils de 30 et 70.
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
ENCRE_SECONDAIRE = "#52514e"
ATTENUE = "#898781"
GRILLE = "#e1e0d9"
AXE = "#c3c2b7"
SERIE_1 = "#2a78d6"  # bleu : cours, ligne MACD
SERIE_2 = "#eb6834"  # orange : MM20, ligne de signal
SERIE_3 = "#1baf7a"  # aqua : MM50 (en tirets, pour ne pas dépendre de la couleur)
SERIE_RSI = "#6250d6"
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


def _legende(ax, ncol: int, dedans: bool = False) -> None:
    """Légende au-dessus du panneau, ou dans son coin haut gauche pour les petits panneaux."""
    place = {"loc": "upper left", "bbox_to_anchor": (0, 1.08)} if dedans else {
        "loc": "lower left", "bbox_to_anchor": (0, 1.0)}
    leg = ax.legend(**place, ncol=ncol, frameon=False,
                    fontsize=6, handlelength=1.2, columnspacing=0.8, handletextpad=0.4,
                    labelspacing=0.2, borderaxespad=0.2, labelcolor=ENCRE_SECONDAIRE)
    for poignee in leg.legend_handles:
        if hasattr(poignee, "set_sizes"):
            poignee.set_sizes([14])


def graphique(df: pd.DataFrame, jours: int = 63) -> bytes:
    """Renvoie le PNG des `jours` dernières séances (63 séances, environ trois mois)."""
    d = df.iloc[-jours:]
    x = d.index

    fig, (haut, milieu, bas) = plt.subplots(
        3, 1, figsize=(3.6, 3.2), dpi=200, sharex=True,
        gridspec_kw={"height_ratios": [3, 1.2, 1], "hspace": 0.12},
    )
    fig.patch.set_facecolor(SURFACE)
    for ax in (haut, milieu, bas):
        _habiller(ax)

    haut.fill_between(x, d["bb_basse"], d["bb_haute"], color=SERIE_1, alpha=0.10,
                      linewidth=0, label="Bollinger")
    haut.plot(x, d["Close"], color=SERIE_1, linewidth=1.2, label="Cours")
    if "mm20" in d:
        haut.plot(x, d["mm20"], color=SERIE_2, linewidth=0.9, label="MM20")
    if "mm50" in d:
        haut.plot(x, d["mm50"], color=SERIE_3, linewidth=0.9, linestyle=(0, (4, 2)), label="MM50")
    haut.scatter(x, d["sar"], s=1.5, color=ATTENUE, label="SAR")

    achats, ventes = d[d["signal"] == ACHAT], d[d["signal"] == VENTE]
    if len(achats):
        haut.scatter(achats.index, achats["Low"] * 0.985, marker="^", s=30, color=BON,
                     edgecolors=SURFACE, linewidths=0.8, zorder=5, label="Achat")
    if len(ventes):
        haut.scatter(ventes.index, ventes["High"] * 1.015, marker="v", s=30, color=CRITIQUE,
                     edgecolors=SURFACE, linewidths=0.8, zorder=5, label="Vente")
    _legende(haut, ncol=4)

    milieu.plot(x, d["macd"], color=SERIE_1, linewidth=0.9, label="MACD (12, 26, 9)")
    milieu.plot(x, d["macd_signal"], color=SERIE_2, linewidth=0.9, label="Signal")
    milieu.axhline(0, color=AXE, linewidth=0.6)
    bas_m, haut_m = milieu.get_ylim()
    milieu.set_ylim(bas_m, haut_m + (haut_m - bas_m) * 0.45)  # marge haute pour la légende
    _legende(milieu, ncol=2, dedans=True)

    bas.axhspan(30, 70, color=SERIE_RSI, alpha=0.06, linewidth=0)
    for seuil in (30, 70):
        bas.axhline(seuil, color=AXE, linewidth=0.6, linestyle=(0, (2, 2)))
    bas.plot(x, d["rsi"], color=SERIE_RSI, linewidth=0.9, label="RSI (14)")
    bas.set_ylim(0, 115)  # marge haute pour la légende
    bas.set_yticks([30, 70])
    _legende(bas, ncol=1, dedans=True)

    bas.xaxis.set_major_locator(mdates.MonthLocator())
    bas.xaxis.set_major_formatter(_format_mois)

    tampon = io.BytesIO()
    fig.savefig(tampon, format="png", facecolor=SURFACE, bbox_inches="tight", pad_inches=0.06)
    plt.close(fig)
    return tampon.getvalue()
