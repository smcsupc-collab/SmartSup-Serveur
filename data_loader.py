"""
Charge l'historique d'incidents depuis incidents_data.xlsx et construit
des agrégats par service utilisés pour l'auto-complétion dans le frontend.
"""

import pandas as pd
from pathlib import Path
from collections import Counter

FAILED_SHEETS: list[str] = []

EXCEL_PATH = Path(__file__).parent / "data" / "incidents_data.xlsx"

COL_TICKET      = "N°ticket"
COL_PRIORITY    = "Priorité"
COL_SERVICE     = "Nom de service"
COL_DESCRIPTION = "Description"
COL_CAUSE       = "Cause de l'incident"
COL_ACTION      = "Actions correctives"
COL_TMC         = "TMC"

# Valeur par défaut — peut être surchargée depuis config.json via l'argument skip_sheets
_DEFAULT_SKIP_SHEETS = {
    "Plan d'action", "Suivi Perfomances", "Objectifs_2022",
    "Synthese_2018", "objectifs_Semestre_2_2018"
}


def _normalise(val) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    return str(val).replace("\xa0", " ").strip()


def _most_common(values: list[str]) -> str:
    filtered = [v for v in values if v]
    if not filtered:
        return ""
    return Counter(filtered).most_common(1)[0][0]


def load_all_sheets(skip_sheets: set[str] | None = None) -> pd.DataFrame:
    """
    Lit tous les onglets mensuels et les concatène en un seul DataFrame.
    Le paramètre skip_sheets permet de configurer dynamiquement les onglets
    à ignorer (par ex. depuis config.json) sans modifier le code source.
    """
    if skip_sheets is None:
        skip_sheets = _DEFAULT_SKIP_SHEETS

    xl = pd.ExcelFile(EXCEL_PATH)
    frames = []

    for sheet in xl.sheet_names:
        if sheet in skip_sheets:
            continue
        try:
            df = xl.parse(sheet, header=0)
            rename_map = {}
            for col in df.columns:
                col_str = _normalise(col)
                if "ticket" in col_str.lower():
                    rename_map[col] = COL_TICKET
                elif "priorit" in col_str.lower():
                    rename_map[col] = COL_PRIORITY
                elif "nom de service" in col_str.lower():
                    rename_map[col] = COL_SERVICE
                elif col_str.lower() == "description":
                    rename_map[col] = COL_DESCRIPTION
                elif "cause" in col_str.lower() and "incident" in col_str.lower():
                    rename_map[col] = COL_CAUSE
                elif "action" in col_str.lower():
                    rename_map[col] = COL_ACTION
                elif col_str.lower() == "tmc":
                    rename_map[col] = COL_TMC
            df = df.rename(columns=rename_map)
            keep = [c for c in [COL_TICKET, COL_PRIORITY, COL_SERVICE,
                                 COL_DESCRIPTION, COL_CAUSE, COL_ACTION, COL_TMC]
                    if c in df.columns]
            frames.append(df[keep])
        except Exception as exc:
            FAILED_SHEETS.append(f"{sheet}: {exc}")
            continue

    if not frames:
        return pd.DataFrame(columns=[COL_TICKET, COL_PRIORITY, COL_SERVICE,
                                      COL_DESCRIPTION, COL_CAUSE, COL_ACTION, COL_TMC])
    return pd.concat(frames, ignore_index=True)


def build_service_catalog(skip_sheets: set[str] | None = None) -> dict:
    """
    Retourne un dict indexé par nom de service avec des valeurs agrégées.

    {
      "Orange Money add-on Local / EDG Prepaid": {
        "description": "Impossible d'effectuer des paiements...",
        "tmc":         "DSI",
        "priority":    "P1",
        "causes":      ["Inconnue", "Problème réseau..."],   # top-10 par fréquence
        "actions":     ["Inconnue", "Redémarrage service..."]
      },
      ...
    }
    """
    df = load_all_sheets(skip_sheets=skip_sheets)

    for col in [COL_SERVICE, COL_DESCRIPTION, COL_CAUSE, COL_ACTION, COL_TMC, COL_PRIORITY]:
        if col in df.columns:
            df[col] = df[col].apply(_normalise)

    catalog: dict = {}

    for service, group in df.groupby(COL_SERVICE):
        if not service or len(service) < 3 or service.strip(":. -") == "":
            continue
        if "\n" in service or service.count("/") > 3 or len(service) > 120:
            continue

        descriptions = group[COL_DESCRIPTION].tolist() if COL_DESCRIPTION in group else []
        tmcs         = group[COL_TMC].tolist()         if COL_TMC         in group else []
        priorities   = group[COL_PRIORITY].tolist()    if COL_PRIORITY    in group else []
        causes_raw   = group[COL_CAUSE].tolist()       if COL_CAUSE       in group else []
        actions_raw  = group[COL_ACTION].tolist()      if COL_ACTION      in group else []

        causes_ranked = [v for v, _ in Counter(
            c for c in causes_raw  if c and c.lower() != "inconnue"
        ).most_common(10)]
        actions_ranked = [v for v, _ in Counter(
            a for a in actions_raw if a and a.lower() != "inconnue"
        ).most_common(10)]

        catalog[service] = {
            "description": _most_common(descriptions),
            "tmc":         _most_common(tmcs),
            "priority":    _most_common(priorities),
            "causes":      causes_ranked,
            "actions":     actions_ranked,
        }

    return catalog


# ── Quick self-test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    cat = build_service_catalog()
    print(f"\n{len(cat)} services chargés.\n")
    for name, data in list(cat.items())[:5]:
        print(f"Service : {name}")
        print(f"  TMC         : {data['tmc']}")
        print(f"  Priorité    : {data['priority']}")
        print(f"  Description : {data['description'][:80]}...")
        print(f"  Top causes  : {data['causes'][:3]}")
        print(f"  Top actions : {data['actions'][:3]}")
        print()
