#!/usr/bin/env python3
"""
Client CLI pour éditer la feuille de compte Google Sheets.
"""

import sys
from datetime import datetime

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


def saisir_ligne(ws):
    """Saisie interactive d'une nouvelle ligne."""
    print("\n--- Nouvelle opération ---\n")

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
                total = (fields.get("cath_paye", 0) + fields.get("phil_paye", 0)) / 2
                val = ask_float("PhilDoit", default_label=f"formule ={total:.2f}", allow_empty=True)

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
    print(f"\n  Ligne ajoutée (ligne {new_row_index}) ✓")


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
