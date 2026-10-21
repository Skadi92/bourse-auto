# Bourse-auto

Outil d'alertes par mail sur le CAC 40 (indice et 40 valeurs) et quelques ETF. L'analyse est journalière, mais les alertes sont réservées aux mouvements de fond : l'objectif est de se protéger des krachs et de capter les vraies tendances, avec environ un aller-retour par an et par actif. L'outil tourne chaque soir de semaine sur GitHub Actions.

Les signaux sont techniques et automatiques. Ils ne constituent pas un conseil en investissement.

## Logique

### Régime de fond (seul à déclencher les alertes)

Les indicateurs sont réglés sur des horizons longs : moyenne mobile 200 séances (MM200), momentum trois mois, MACD lent (60/130/45, équivalent d'un MACD hebdomadaire) et SAR lent.

- **ACHAT** : cours au-dessus de la MM200, momentum trois mois positif, MACD lent positif et SAR lent haussier, pendant trois séances consécutives, et au moins dix séances après la dernière vente ;
- **VENTE, tendance** : cours plus de 2 % sous la MM200, momentum et MACD lents négatifs, pendant trois séances consécutives ;
- **VENTE, krach** : repli depuis le plus haut des trois derniers mois supérieur à 1,5 fois la volatilité trois mois de l'actif, sans attendre de confirmation.

Entre les seuils d'achat et de vente, rien ne se déclenche (hystérésis) : c'est ce qui supprime les allers-retours.

La **force du mouvement** (0 à 100) mesure l'ampleur du momentum et de l'écart à la MM200, rapportés à la volatilité de l'actif, ainsi que la force de tendance (ADX). Elle permet de comparer une action nerveuse et un ETF calme.

### État court terme (descriptif)

Les indicateurs standards (MACD 12/26/9, Bollinger 20, SAR, momentum 10 jours, ADX) qualifient l'état du jour : hausse, baisse, retournement, stabilité ou neutre. Cet état est affiché dans le mail à titre d'information et ne déclenche aucune alerte.

### Mail

Un mail n'est envoyé que les jours où au moins un signal ACHAT ou VENTE apparaît. Seuls les cinq signaux les plus forts sont détaillés. Les autres signaux du jour sont cités ensuite. Les instruments marqués `toujours = true` dans `config.toml` (les ETF WPEA, CW8 et QQQ) figurent dans chaque mail envoyé, dans une section « ETF suivis », même sans signal. Chaque instrument est présenté avec ses statistiques à gauche et un graphique sur un an à droite (cours, MM200, bandes de Bollinger, SAR lent, signaux, MACD lent). Le paramètre `force_min_achat` permet d'écarter les achats les plus faibles ; les ventes passent toujours. Le fichier `etat/etat.json`, mis à jour par le workflow, évite les doublons.

### Résultats du backtest (20 ans, 44 actifs, frais de 0,10 % par ordre)

Médianes sur les 44 actifs, mesurées en octobre 2026 :

| | Stratégie | Achat-conservation |
|---|---|---|
| Rendement annualisé | 4,5 % | 8,1 % |
| Perte maximale | -46,9 % | -59,2 % |
| Allers-retours par an | 0,9 | 0 |

Sur l'indice et les ETF, la protection est nette (CAC 40 : perte maximale -30 % contre -57 % ; Nasdaq-100 : -29 % contre -53 %), pour un rendement inférieur de 1 à 3 points par an. Sur les actions isolées, le rendement est inférieur dans la majorité des cas. La stratégie est une assurance contre les krachs, qui a un coût, pas une méthode pour battre le marché.

## Utilisation locale

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m bourse backtest              # rejoue les règles sur 20 ans
.venv\Scripts\python -m bourse backtest --periode 5y
.venv\Scripts\python -m bourse analyser --essai      # affiche le mail sans l'envoyer
.venv\Scripts\python -m pytest -q
```

Les instruments, les paramètres et les seuils se règlent dans `config.toml`. Les tickers suivent la nomenclature Yahoo Finance, avec le suffixe `.PA` pour Euronext Paris.

## Mise en place sur GitHub

1. Activez la validation en deux étapes sur le compte Gmail, puis créez un mot de passe d'application (Compte Google, Sécurité, Mots de passe des applications).
2. Créez un dépôt **privé** sur GitHub et poussez-y le projet.
3. Dans Settings, Secrets and variables, Actions, ajoutez les secrets suivants : `GMAIL_USER` (adresse Gmail), `GMAIL_APP_PASSWORD` (mot de passe d'application) et, si les alertes doivent partir vers une autre adresse, `MAIL_TO`.
4. Dans l'onglet Actions, lancez « Alertes bourse » à la main avec la commande `test-mail`. Elle envoie un mail au format réel avec les cinq actifs dont le mouvement est le plus fort, sans modifier l'état mémorisé, ce qui valide les secrets Gmail même sans signal du jour.
5. Lancez ensuite la commande `analyser` avec `essai` coché, puis sans.

Le workflow s'exécute du lundi au vendredi à 22 h 30 UTC. Une bougie de la séance en cours n'est jamais analysée.

## Limites connues

- yfinance n'est pas une API officielle : il peut cesser de fonctionner ou renvoyer des données incomplètes. Le fichier `bourse/data.py` est le seul à modifier pour changer de source.
- GitHub peut retarder les déclenchements planifiés. Il désactive aussi les workflows planifiés des dépôts sans activité pendant 60 jours (règle documentée pour les dépôts publics, à vérifier pour un dépôt privé). Les commits quotidiens de l'état devraient suffire à maintenir l'activité.
- La composition du CAC 40 est revue chaque trimestre par Euronext : la liste de `config.toml` est à mettre à jour à la main après chaque revue (mars, juin, septembre, décembre). `^FCHI` est un indice de prix, hors dividendes : il sous-estime le rendement réel.
- Le backtest est long uniquement. Il exécute les ordres à l'ouverture du lendemain et compte des frais fixes. Il ne modélise ni le glissement de prix ni la fiscalité.
