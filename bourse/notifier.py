"""Construction et envoi du mail d'alerte via le SMTP de Gmail."""

import os
import smtplib
import ssl
from email.message import EmailMessage
from html import escape

from .signals import ACHAT, LIBELLES, VENTE

AVERTISSEMENT = (
    "Signaux techniques générés automatiquement, sans valeur de conseil en investissement. "
    "La décision d'acheter ou de vendre vous appartient."
)


def _fmt(x: float, dec: int = 2) -> str:
    return f"{x:,.{dec}f}".replace(",", " ").replace(".", ",")


def _ligne(a: dict) -> dict:
    d = a["donnees"]
    return {
        "Instrument": f"{a['nom']} ({a['ticker']})",
        "Date": a["date"],
        "Signal": a["signal"] or "aucun",
        "État": LIBELLES[a["etat"]],
        "Précédent": LIBELLES.get(a["etat_precedent"], "inconnu"),
        "Clôture": _fmt(d["Close"]),
        "Conviction": f"{int(d['conviction'])} / 100",
        "Score": f"{int(d['score']):+d} / 4",
        "SAR": f"{_fmt(d['sar'])} ({'sous le' if d['sar_tendance'] == 1 else 'au-dessus du'} prix)",
        "MACD (hist.)": _fmt(d["macd_hist"], 3),
        "Momentum": f"{_fmt(d['momentum'])} %",
        "Bollinger %B": _fmt(d["bb_pct"]),
        "ADX": _fmt(d["adx"], 1),
    }


def construire(alertes: list[dict], prefixe: str) -> EmailMessage:
    nb_achat = sum(a["signal"] == ACHAT for a in alertes)
    nb_vente = sum(a["signal"] == VENTE for a in alertes)
    resume = []
    if nb_achat:
        resume.append(f"{nb_achat} achat")
    if nb_vente:
        resume.append(f"{nb_vente} vente")
    if not resume:
        resume.append(f"{len(alertes)} changement(s) d'état")
    msg = EmailMessage()
    msg["Subject"] = f"{prefixe} {', '.join(resume)} ({alertes[0]['date']})"

    lignes = [_ligne(a) for a in alertes]
    texte = "\n\n".join("\n".join(f"{k} : {v}" for k, v in l.items()) for l in lignes)
    msg.set_content(f"{texte}\n\n{AVERTISSEMENT}\n")

    couleur = {ACHAT: "#1a7f37", VENTE: "#cf222e"}
    blocs = []
    for a, l in zip(alertes, lignes):
        teinte = couleur.get(a["signal"], "#57606a")
        cellules = "".join(
            f"<tr><td style='padding:2px 12px 2px 0;color:#57606a'>{escape(k)}</td>"
            f"<td style='padding:2px 0'>{escape(str(v))}</td></tr>"
            for k, v in l.items()
            if k != "Instrument"
        )
        blocs.append(
            f"<div style='border-left:4px solid {teinte};padding:8px 12px;margin:0 0 16px'>"
            f"<div style='font-weight:600;font-size:15px'>{escape(l['Instrument'])}</div>"
            f"<table style='font-size:13px;border-collapse:collapse'>{cellules}</table></div>"
        )
    msg.add_alternative(
        "<html><body style='font-family:Segoe UI,Arial,sans-serif;color:#1f2328'>"
        + "".join(blocs)
        + f"<p style='font-size:12px;color:#57606a'>{escape(AVERTISSEMENT)}</p></body></html>",
        subtype="html",
    )
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
