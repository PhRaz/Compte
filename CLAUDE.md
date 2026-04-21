# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Setup
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run
source .venv/bin/activate
python compte.py
```

## Architecture

Single-file CLI (`compte.py`) that appends rows to a Google Sheets spreadsheet tracking shared expenses between two people (Catherine and Philippe).

**Auth**: Google service account via `credentials.json` (must be shared as Editor on the spreadsheet).

**Sheet structure** (columns A–K): Date, Quoi, Catégorie, CathPaye, PhilPaye, CathDoit, PhilDoit, SoldeCath (formula), SoldePhil (formula), TotalCath (formula), TotalPhil (formula).

**Key constants** at top of `compte.py`: `SPREADSHEET_ID`, `SHEET_NAME` (year, e.g. `"2025"`), `CREDENTIALS_FILE`.

**CathDoit / PhilDoit logic**: If user leaves CathDoit blank → both use formula `=(D+E)/2`. If user enters a value → PhilDoit is auto-computed as `CathPaye + PhilPaye - CathDoit`. A balance check warns if totals don't match.

**Formulas written to sheet** (via `USER_ENTERED`): cumulative totals use `SUM($H$2:Hn)` with an absolute start to survive row insertions.
