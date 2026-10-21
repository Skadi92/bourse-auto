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
        "Repli depuis le plus haut 3 mois": f"{d['f_repli']:.1f} %".replace(".", ","),
        "Volatilité 3 mois": f"{_fmt(d['f_volatilite'], 1)} %",
        "État court terme": LIBELLES[a["etat"]],
    }


def construire(alertes: list[dict], prefixe: str, objet: str | None = None,
               autres: list[dict] | None = None) -> EmailMessage:
    """alertes : instruments détaillés ; autres : signaux du jour cités sans détail."""
    autres = autres or []
    tous = alertes + autres
    nb_achat = sum(a["signal"] == ACHAT for a in tous)
    nb_vente = sum(a["signal"] == VENTE for a in tous)
    resume = [s for s in (f"{nb_achat} achat" if nb_achat else "",
                          f"{nb_vente} vente" if nb_vente else "") if s]
    msg = EmailMessage()
    msg["Subject"] = f"{prefixe} {objet or ', '.join(resume)} ({alertes[0]['date']})"

    lignes = [_ligne(a) for a in alertes]
    note_autres = ""
    if autres:
        liste = ", ".join(f"{a['nom']} ({a['signal']}, force {int(a['force'])})" for a in autres)
        note_autres = f"Autres signaux du jour, non détaillés : {liste}."
    texte = "\n\n".join("\n".join(f"{k} : {v}" for k, v in l.items()) for l in lignes)
    msg.set_content(f"{texte}\n\n{note_autres}\n\n{AVERTISSEMENT}\n")

    couleur = {ACHAT: "#0ca30c", VENTE: "#d03b3b"}
    blocs, images = [], []
    for a, l in zip(alertes, lignes):
        image = ""
        if a.get("graphique"):
            cid = make_msgid(domain="bourse-auto")
            images.append((cid, a["graphique"]))
            image = (f"<img src='cid:{cid[1:-1]}' width='600' alt='Graphique de tendance "
                     f"{escape(a['ticker'])}' style='display:block;max-width:100%;height:auto;"
                     f"margin-top:8px'>")
        teinte = couleur.get(a["signal"], "#57606a")
        cellules = "".join(
            f"<tr><td style='padding:2px 12px 2px 0;color:#57606a'>{escape(k)}</td>"
            f"<td style='padding:2px 0'>{escape(str(v))}</td></tr>"
            for k, v in l.items()
            if k != "Instrument"
        )
        blocs.append(
            f"<div style='border-left:4px solid {teinte};padding:8px 12px;margin:0 0 20px'>"
            f"<div style='font-weight:600;font-size:15px'>{escape(l['Instrument'])}</div>"
            f"<table style='font-size:13px;border-collapse:collapse'>{cellules}</table>{image}</div>"
        )
    pied = f"<p style='font-size:13px'>{escape(note_autres)}</p>" if note_autres else ""
    msg.add_alternative(
        "<html><body style='font-family:Segoe UI,Arial,sans-serif;color:#1f2328'>"
        + "".join(blocs) + pied
        + f"<p style='font-size:12px;color:#57606a'>{escape(AVERTISSEMENT)}</p></body></html>",
        subtype="html",
    )
    html = msg.get_payload()[1]
    for cid, png in images:
        html.add_related(png, maintype="image", subtype="png", cid=cid)
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
