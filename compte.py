#!/usr/bin/env python3
"""
Client CLI pour éditer la feuille de compte Google Sheets.
"""

import calendar
import os
import sys
import tomllib
from datetime import datetime, date, timedelta

import gspread
from prompt_toolkit import prompt
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.validation import Validator, ValidationError

# --- Configuration ---
SPREADSHEET_ID = "1y9G01fk9gU63cOQWbSPj4p24P86uZ1xBEsQi-L7jxhc"
CREDENTIALS_FILE = "credentials.json"
SHEET_NAME = "2025"  # Adapter si besoin

# Colonnes (ordre dans la feuille)
COL_DATE = 1
COL_QUOI = 2
COL_CATEGORIE = 3
COL_CATH_PAYE = 4
COL_PHIL_PAYE = 5
COL_CATH_DOIT = 6
COL_PHIL_DOIT = 7
# COL_SOLDE_CATH = 8  (formule)
# COL_SOLDE_PHIL = 9  (formule)
# COL_TOTAL_CATH = 10 (formule)
# COL_TOTAL_PHIL = 11 (formule)


HEADERS = ["Date", "Quoi", "Catégorie", "CathPaye", "PhilPaye", "CathDoit", "PhilDoit", "SoldeCath", "SoldePhil", "TotalCath", "TotalPhil"]
COL_WIDTHS = [10, 22, 13,  8,  8,  8,  8,  9,  9,  9,  9]
SOLDE_COLS = {7, 8, 9, 10}  # indices de SoldeCath, SoldePhil, TotalCath, TotalPhil

ANSI_GREEN = "\033[32m"
ANSI_RED   = "\033[31m"
ANSI_RESET = "\033[0m"


def get_last_rows(ws, n=10):
    """Retourne les n dernières lignes de données (sans l'en-tête)."""
    all_values = ws.get_all_values()
    data = all_values[1:]  # skip header
    return data[-n:] if len(data) >= n else data


def display_last_rows(rows):
    """Affiche un tableau formaté des dernières lignes dans le terminal."""
    os.system("clear")
    sep = "+" + "+".join("-" * (w + 2) for w in COL_WIDTHS) + "+"

    def fmt_cell(cell, width, colored=False):
        text = str(cell)[:width]
        try:
            float(str(cell).replace(",", ".").replace(" ", ""))
            padded = f"{text:>{width}}"  # aligné à droite pour les nombres
        except ValueError:
            padded = f"{text:<{width}}"  # aligné à gauche pour le texte
        if colored:
            try:
                val = float(str(cell).replace(",", ".").replace(" ", ""))
                color = ANSI_GREEN if val > 0 else ANSI_RED if val < 0 else ""
                return f" {color}{padded}{ANSI_RESET if color else ''} "
            except ValueError:
                pass
        return f" {padded} "

    def fmt_row(cells, header=False):
        padded = list(cells) + [""] * (len(HEADERS) - len(cells))
        parts = [
            fmt_cell(padded[i], w, colored=(not header and i in SOLDE_COLS))
            for i, w in enumerate(COL_WIDTHS)
        ]
        return "|" + "|".join(parts) + "|"

    print(sep)
    print(fmt_row(HEADERS, header=True))
    print(sep)
    for row in rows:
        print(fmt_row(row))
    print(sep)
    print()


def connect_sheet():
    """Connexion à Google Sheets via compte de service."""
    gc = gspread.service_account(filename=CREDENTIALS_FILE)
    sh = gc.open_by_key(SPREADSHEET_ID)
    return sh.worksheet(SHEET_NAME)


def get_existing_values(ws, col_index):
    """Récupère les valeurs uniques et non vides d'une colonne (sans l'entête)."""
    values = ws.col_values(col_index)[1:]  # skip header
    return sorted(set(v.strip() for v in values if v.strip()))


def parse_date(raw):
    """
    Parse une date saisie sous forme 'jour mois [année]'.
    Ex: '6 4', '6 4 2026', '6' (jour courant du mois courant)
    Retourne une chaîne 'DD/MM/YYYY'.
    """
    now = datetime.now()
    parts = raw.strip().split()
    try:
        if len(parts) == 1:
            day = int(parts[0])
            month = now.month
            year = now.year
        elif len(parts) == 2:
            day, month = int(parts[0]), int(parts[1])
            year = now.year
        elif len(parts) == 3:
            day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
            if year < 100:
                year += 2000
        else:
            raise ValueError
        datetime(year, month, day)  # validation
        return f"{day:02d}/{month:02d}/{year}"
    except (ValueError, IndexError):
        return None


def ask_float(label, default=None, default_label=None, allow_empty=False):
    """Demande un nombre flottant. Retourne default si vide (ou None si allow_empty)."""
    hint = f" [{default_label or default}]" if (default is not None or default_label) else ""
    while True:
        raw = prompt(f"{label}{hint} : ").strip()
        if raw == "":
            if allow_empty:
                return None
            if default is not None:
                return default
        try:
            return float(raw.replace(",", "."))
        except ValueError:
            print("  Valeur invalide, entrez un nombre (ex: 12.50)")


def ask_date():
    """Demande la date avec gestion des raccourcis."""
    now = datetime.now()
    default_str = f"{now.day} {now.month} {now.year}"
    while True:
        raw = prompt(f"Date (j m [a]) [{default_str}] : ").strip()
        if raw == "":
            raw = default_str
        result = parse_date(raw)
        if result:
            return result
        print("  Format invalide. Exemples : '6', '6 4', '6 4 2026'")


def ask_text(label, completer_values):
    """Demande une chaîne avec autocomplétion."""
    completer = WordCompleter(completer_values, ignore_case=True, sentence=True)
    while True:
        raw = prompt(f"{label} : ", completer=completer).strip()
        if raw:
            return raw
        print(f"  {label} ne peut pas être vide.")


def build_row(ws, new_row_index):
    """Construit la ligne avec les formules pour les colonnes calculées."""
    r = new_row_index

    # Formules relatives à la ligne courante
    cath_doit_formula = f"=(D{r}+E{r})/2"
    phil_doit_formula = f"=(D{r}+E{r})/2"
    solde_cath_formula = f"=D{r}-F{r}"
    solde_phil_formula = f"=E{r}-G{r}"
    total_cath_formula = f"=SUM($H$2:H{r})"
    total_phil_formula = f"=SUM($I$2:I{r})"

    return (
        cath_doit_formula,
        phil_doit_formula,
        solde_cath_formula,
        solde_phil_formula,
        total_cath_formula,
        total_phil_formula,
    )


JOURS_SEMAINE = {
    "lundi": 0, "mardi": 1, "mercredi": 2, "jeudi": 3,
    "vendredi": 4, "samedi": 5, "dimanche": 6,
}


def sync_recurrents(ws):
    """Insère les opérations récurrentes manquantes depuis recurrents.toml."""
    config_path = "recurrents.toml"
    if not os.path.exists(config_path):
        return

    with open(config_path, "rb") as f:
        config = tomllib.load(f)

    recurrents = config.get("recurrent", [])
    if not recurrents:
        return

    all_values = ws.get_all_values()
    existing = {
        (row[0].strip(), row[1].strip().lower(), row[2].strip().lower())
        for row in all_values[1:]
        if len(row) >= 3
    }

    today = date.today()
    sheet_year = int(SHEET_NAME)
    rows_to_add = []

    for rec in recurrents:
        quoi = rec["quoi"]
        categorie = rec["categorie"]
        cath_paye = float(rec.get("cath_paye", 0))
        phil_paye = float(rec.get("phil_paye", 0))
        cath_doit = rec.get("cath_doit", None)

        if "depuis" in rec:
            depuis = datetime.strptime(rec["depuis"], "%d/%m/%Y").date()
        else:
            depuis = date(sheet_year, 1, 1)

        chaque = rec.get("chaque", "").lower()
        chaque_mois = rec.get("chaque_mois", None)

        if chaque_mois is not None:
            jour = int(chaque_mois)
            if not (1 <= jour <= 31):
                print(f"  recurrents.toml : chaque_mois '{jour}' invalide pour '{quoi}', ignoré.")
                continue
            y, m = depuis.year, depuis.month
            while True:
                if jour <= calendar.monthrange(y, m)[1]:
                    current = date(y, m, jour)
                    if current >= depuis:
                        break
                if m == 12:
                    y, m = y + 1, 1
                else:
                    m += 1
            while current < today:
                date_str = f"{current.day:02d}/{current.month:02d}/{current.year}"
                if (date_str, quoi.lower(), categorie.lower()) not in existing:
                    rows_to_add.append((current, date_str, quoi, categorie, cath_paye, phil_paye, cath_doit))
                if current.month == 12:
                    y, m = current.year + 1, 1
                else:
                    y, m = current.year, current.month + 1
                # Cherche le prochain mois où ce jour existe
                for _ in range(12):
                    if jour <= calendar.monthrange(y, m)[1]:
                        current = date(y, m, jour)
                        break
                    if m == 12:
                        y, m = y + 1, 1
                    else:
                        m += 1
                else:
                    break

        elif chaque in JOURS_SEMAINE:
            weekday = JOURS_SEMAINE[chaque]
            delta = (weekday - depuis.weekday()) % 7
            current = depuis + timedelta(days=delta)
            while current < today:
                date_str = f"{current.day:02d}/{current.month:02d}/{current.year}"
                if (date_str, quoi.lower(), categorie.lower()) not in existing:
                    rows_to_add.append((current, date_str, quoi, categorie, cath_paye, phil_paye, cath_doit))
                current += timedelta(days=7)

        else:
            print(f"  recurrents.toml : 'chaque' ou 'chaque_mois' manquant/invalide pour '{quoi}', ignoré.")
            continue

    if not rows_to_add:
        return

    rows_to_add.sort(key=lambda x: x[0])
    print(f"  {len(rows_to_add)} opération(s) récurrente(s) manquante(s) → insertion en cours...")

    next_row = len(all_values) + 1
    batch = []
    for _, date_str, quoi, categorie, cath_paye, phil_paye, cath_doit in rows_to_add:
        r = next_row
        if cath_doit is None:
            cd = f"=(D{r}+E{r})/2"
            pd_val = f"=(D{r}+E{r})/2"
        else:
            cd = float(cath_doit)
            pd_val = cath_paye + phil_paye - cd
        batch.append([
            date_str, quoi, categorie,
            cath_paye or 0,
            phil_paye or 0,
            cd, pd_val,
            f"=D{r}-F{r}",
            f"=E{r}-G{r}",
            f"=SUM($H$2:H{r})",
            f"=SUM($I$2:I{r})",
        ])
        next_row += 1

    ws.append_rows(batch, value_input_option="USER_ENTERED")
    print(f"  {len(batch)} ligne(s) ajoutée(s).\n")


def saisir_ligne(ws):
    """Saisie interactive d'une nouvelle ligne."""
    display_last_rows(get_last_rows(ws))
    print("--- Nouvelle opération ---\n")

    # Récupération des valeurs existantes pour autocomplétion
    quoi_values = get_existing_values(ws, COL_QUOI)
    cat_values = get_existing_values(ws, COL_CATEGORIE)

    fields = {}
    field_order = ["date", "quoi", "categorie", "cath_paye", "phil_paye", "cath_doit", "phil_doit"]
    current = 0

    while current < len(field_order):
        field = field_order[current]

        if field == "date":
            val = ask_date()
        elif field == "quoi":
            val = ask_text("Quoi", quoi_values)
        elif field == "categorie":
            val = ask_text("Catégorie", cat_values)
        elif field == "cath_paye":
            val = ask_float("CathPaye", default=0.0)
        elif field == "phil_paye":
            val = ask_float("PhilPaye", default=0.0)
        elif field == "cath_doit":
            total = (fields.get("cath_paye", 0) + fields.get("phil_paye", 0)) / 2
            val = ask_float("CathDoit", default_label=f"formule ={total:.2f}", allow_empty=True)
        elif field == "phil_doit":
            if fields.get("cath_doit") is None:
                # CathDoit = formule → PhilDoit = formule aussi, on ne demande pas
                val = None
            else:
                # CathDoit saisi → PhilDoit calculé automatiquement
                val = fields["cath_paye"] + fields["phil_paye"] - fields["cath_doit"]
                print(f"PhilDoit : {val:.2f}  (= CathPaye + PhilPaye - CathDoit)")

        fields[field] = val
        current += 1

    # Validation si CathDoit/PhilDoit saisis manuellement
    cath_paye = fields["cath_paye"]
    phil_paye = fields["phil_paye"]
    cath_doit = fields.get("cath_doit")
    phil_doit = fields.get("phil_doit")

    if cath_doit is not None and phil_doit is not None:
        total_paye = cath_paye + phil_paye
        total_du = cath_doit + phil_doit
        if abs(total_paye - total_du) > 0.01:
            print(f"\n  Attention : CathPaye+PhilPaye ({total_paye:.2f}) ≠ CathDoit+PhilDoit ({total_du:.2f})")
            confirm = prompt("  Continuer quand même ? (o/N) : ").strip().lower()
            if confirm != "o":
                print("  Ligne annulée.")
                return

    # Détermination du numéro de ligne
    all_values = ws.get_all_values()
    new_row_index = len(all_values) + 1

    (
        cath_doit_formula,
        phil_doit_formula,
        solde_cath_formula,
        solde_phil_formula,
        total_cath_formula,
        total_phil_formula,
    ) = build_row(ws, new_row_index)

    # Construction de la ligne à insérer
    row = [
        fields["date"],
        fields["quoi"],
        fields["categorie"],
        fields["cath_paye"] if fields["cath_paye"] != 0.0 else 0,
        fields["phil_paye"] if fields["phil_paye"] != 0.0 else 0,
        fields["cath_doit"] if fields["cath_doit"] is not None else cath_doit_formula,
        fields["phil_doit"] if fields["phil_doit"] is not None else phil_doit_formula,
        solde_cath_formula,
        solde_phil_formula,
        total_cath_formula,
        total_phil_formula,
    ]

    ws.append_row(row, value_input_option="USER_ENTERED")
    display_last_rows(get_last_rows(ws))
    print(f"  Ligne ajoutée (ligne {new_row_index}) ✓")


def main():
    print("Connexion à Google Sheets...")
    try:
        ws = connect_sheet()
    except Exception as e:
        import traceback
        print(f"Erreur de connexion : {e}")
        traceback.print_exc()
        sys.exit(1)

    print(f"Connecté à : {ws.spreadsheet.title} / {ws.title}")
    sync_recurrents(ws)

    while True:
        try:
            saisir_ligne(ws)
            again = prompt("\nAjouter une autre opération ? (O/n) : ").strip().lower()
            if again == "n":
                break
        except KeyboardInterrupt:
            print("\nArrêt.")
            break


if __name__ == "__main__":
    main()
