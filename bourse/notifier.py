"""Construction et envoi du mail d'alerte via le SMTP de Gmail."""

import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import make_msgid
from html import escape

from .signals import ACHAT, BAISSE, HAUSSE, LIBELLES, NEUTRE, VENTE

AVERTISSEMENT = (
    "Signaux techniques générés automatiquement, sans valeur de conseil en investissement. "
    "La décision d'acheter ou de vendre vous appartient."
)
REGIMES = {HAUSSE: "Haussier (exposé)", BAISSE: "Défensif (hors marché)", NEUTRE: "Indéterminé"}
MOTIFS = {"tendance": "changement de tendance de fond", "krach": "protection contre un krach"}


def _fmt(x: float, dec: int = 2) -> str:
    return f"{x:,.{dec}f}".replace(",", " ").replace(".", ",")


def _ligne(a: dict) -> dict:
    d = a["donnees"]
    ecart_mm = (d["Close"] / d["f_mm"] - 1) * 100
    return {
        "Instrument": f"{a['nom']} ({a['ticker']})",
        "Date": a["date"],
        "Signal": f"{a['signal']}, {MOTIFS[a['motif']]}" if a["signal"] else "aucun",
        "Force du mouvement": f"{int(a['force'])} / 100",
        "Régime de fond": REGIMES[a["regime"]],
        "Régime précédent": REGIMES.get(a.get("regime_precedent"), "inconnu"),
        "Clôture": _fmt(d["Close"]),
        "Écart à la MM200": f"{ecart_mm:+.1f} %".replace(".", ","),
        "Momentum 3 mois": f"{d['f_momentum']:+.1f} %".replace(".", ","),
        "Repli vs plus haut 3 mois": f"{d['f_repli']:.1f} %".replace(".", ","),
        "Volatilité 3 mois": f"{_fmt(d['f_volatilite'], 1)} %",
        "RSI (14)": _fmt(d["rsi"], 0),
        "État court terme": LIBELLES[a["etat"]],
    }


LARGEUR_GRAPHIQUE = 340
COULEURS = {ACHAT: "#0ca30c", VENTE: "#d03b3b"}


def _bloc(a: dict, l: dict, images: list) -> str:
    """Un instrument : statistiques à gauche, graphique à droite (tableau, pour les clients mail)."""
    image = ""
    if a.get("graphique"):
        cid = make_msgid(domain="bourse-auto")
        images.append((cid, a["graphique"]))
        image = (f"<img src='cid:{cid[1:-1]}' width='{LARGEUR_GRAPHIQUE}' "
                 f"alt='Graphique de tendance {escape(a['ticker'])}' "
                 f"style='display:block;width:{LARGEUR_GRAPHIQUE}px;max-width:100%;height:auto'>")
    cellules = "".join(
        f"<tr><td style='padding:1px 10px 1px 0;color:#57606a;white-space:nowrap'>{escape(k)}</td>"
        f"<td style='padding:1px 0'>{escape(str(v))}</td></tr>"
        for k, v in l.items()
        if k != "Instrument"
    )
    teinte = COULEURS.get(a["signal"], "#c3c2b7")
    return (
        f"<table role='presentation' cellpadding='0' cellspacing='0' "
        f"style='border-collapse:collapse;border-left:4px solid {teinte};margin:0 0 16px;width:100%;"
        f"max-width:{LARGEUR_GRAPHIQUE + 400}px'><tr>"
        f"<td valign='top' style='padding:6px 12px'>"
        f"<div style='font-weight:600;font-size:14px;margin-bottom:4px'>{escape(l['Instrument'])}</div>"
        f"<table style='font-size:12px;border-collapse:collapse'>{cellules}</table></td>"
        f"<td valign='top' width='{LARGEUR_GRAPHIQUE}' style='padding:6px 0'>{image}</td>"
        f"</tr></table>"
    )


def _texte(lignes: list[dict]) -> str:
    return "\n\n".join("\n".join(f"{k} : {v}" for k, v in l.items()) for l in lignes)


def construire(alertes: list[dict], prefixe: str, objet: str | None = None,
               autres: list[dict] | None = None, suivis: list[dict] | None = None) -> EmailMessage:
    """alertes : signaux détaillés ; autres : signaux cités sans détail ;
    suivis : instruments inclus dans chaque mail (ETF), même sans signal."""
    autres, suivis = autres or [], suivis or []
    tous = alertes + autres
    nb_achat = sum(a["signal"] == ACHAT for a in tous)
    nb_vente = sum(a["signal"] == VENTE for a in tous)
    resume = [s for s in (f"{nb_achat} achat" if nb_achat else "",
                          f"{nb_vente} vente" if nb_vente else "") if s]
    date = (alertes or suivis)[0]["date"]
    msg = EmailMessage()
    msg["Subject"] = f"{prefixe} {objet or ', '.join(resume)} ({date})"

    lignes_alertes = [_ligne(a) for a in alertes]
    lignes_suivis = [_ligne(a) for a in suivis]
    note_autres = ""
    if autres:
        liste = ", ".join(f"{a['nom']} ({a['signal']}, force {int(a['force'])})" for a in autres)
        note_autres = f"Autres signaux du jour, non détaillés : {liste}."

    titre_alertes = "Mouvements les plus forts" if objet else "Signaux du jour"
    parties_texte = []
    if alertes:
        parties_texte.append(f"{titre_alertes.upper()}\n\n{_texte(lignes_alertes)}")
    if note_autres:
        parties_texte.append(note_autres)
    if suivis:
        parties_texte.append(f"ETF SUIVIS\n\n{_texte(lignes_suivis)}")
    msg.set_content("\n\n".join(parties_texte) + f"\n\n{AVERTISSEMENT}\n")

    images: list = []
    titre = "<h2 style='font-size:16px;margin:20px 0 10px;color:#1f2328'>{}</h2>"
    html = []
    if alertes:
        html.append(titre.format(titre_alertes))
        html += [_bloc(a, l, images) for a, l in zip(alertes, lignes_alertes)]
    if note_autres:
        html.append(f"<p style='font-size:13px'>{escape(note_autres)}</p>")
    if suivis:
        html.append(titre.format("ETF suivis"))
        html += [_bloc(a, l, images) for a, l in zip(suivis, lignes_suivis)]
    msg.add_alternative(
        "<html><body style='font-family:Segoe UI,Arial,sans-serif;color:#1f2328'>"
        + "".join(html)
        + f"<p style='font-size:12px;color:#57606a'>{escape(AVERTISSEMENT)}</p></body></html>",
        subtype="html",
    )
    partie_html = msg.get_payload()[1]
    for cid, png in images:
        partie_html.add_related(png, maintype="image", subtype="png", cid=cid)
    return msg


def envoyer(msg: EmailMessage) -> None:
    """Envoie le message. Variables d'environnement : GMAIL_USER, GMAIL_APP_PASSWORD, MAIL_TO."""
    utilisateur = os.environ["GMAIL_USER"]
    mot_de_passe = os.environ["GMAIL_APP_PASSWORD"]
    msg["From"] = utilisateur
    msg["To"] = os.environ.get("MAIL_TO") or utilisateur
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context()) as smtp:
        smtp.login(utilisateur, mot_de_passe)
        smtp.send_message(msg)
