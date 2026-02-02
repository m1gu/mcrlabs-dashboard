"""
Script standalone para sincronizar datos del tab RS a glims_rs_results_raw.

Uso:
    python scripts/run_sync_rs_raw.py [--spreadsheet-id <ID>] [--dry-run]

Este script es para testing. Una vez aprobado, la lógica se integrará
en run_sync_glims.py
"""

from __future__ import annotations

import argparse
import os
import re
import logging
from typing import Any

import gspread
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(message)s",
)
LOGGER = logging.getLogger(__name__)

TAB_RS = "RS"


def load_env() -> None:
    load_dotenv(override=False)


def build_engine() -> Engine:
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db = os.environ["POSTGRES_DB"]
    user = os.environ["POSTGRES_USER"]
    password = os.environ["POSTGRES_PASSWORD"]
    url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"
    return create_engine(url, future=True, pool_pre_ping=True)


def connect_sheet(spreadsheet_id: str) -> gspread.Spreadsheet:
    sa_path = os.environ.get("GSHEETS_SERVICE_ACCOUNT_FILE")
    if not sa_path:
        raise RuntimeError("GSHEETS_SERVICE_ACCOUNT_FILE must be set")
    client = gspread.service_account(filename=sa_path)
    return client.open_by_key(spreadsheet_id)


def fetch_df(sh: gspread.Spreadsheet, tab: str) -> pd.DataFrame:
    """Return a DataFrame from the given tab."""
    ws = sh.worksheet(tab)
    values = ws.get_all_values()
    if not values:
        return pd.DataFrame()

    raw_headers = values[0]
    seen: dict[str, int] = {}
    headers: list[str] = []
    for idx, h in enumerate(raw_headers):
        base = h.strip() if h else f"unnamed_{idx}"
        count = seen.get(base, 0)
        name = base if count == 0 else f"{base}_{count}"
        headers.append(name)
        seen[base] = count + 1

    rows = []
    for row in values[1:]:
        if len(row) < len(headers):
            row = row + [""] * (len(headers) - len(row))
        elif len(row) > len(headers):
            row = row[: len(headers)]
        rows.append(row)

    return pd.DataFrame(rows, columns=headers)


def to_date_only(value: Any):
    """Parse date value."""
    if value is None or value == "":
        return None
    if isinstance(value, str) and value.strip().lower() in {"n/a", "na", "nan"}:
        return None
    if isinstance(value, str):
        value = value.strip().strip("()")
    try:
        parsed = pd.to_datetime(value, errors="coerce")
    except Exception:
        return None
    if pd.isna(parsed):
        return None
    return parsed.date()


def to_num(value: Any) -> float | None:
    """Parse numeric value."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    if isinstance(value, str):
        val = value.strip()
        if val == "":
            return None
        lowered = val.lower()
        if lowered in {"na", "n/a", "nan", "nd", "bql"}:
            return None
        if val.startswith("<"):
            return None
        try:
            return float(val.replace(",", ""))
        except (TypeError, ValueError):
            return None
    return None


def normalize_sample_id_clean(raw: str) -> str:
    """Limpia el sample_id para agrupación en RS raw.
    
    Maneja casos como:
    - S26-00354-1 -> S26-00354
    - 00337-20mg -> S26-00337
    - dup-00380 -> S26-00380
    - Dup-00378 -> S26-00378
    """
    if not raw:
        return ""
    sid = raw.strip()
    
    # Remover prefijo dup-/Dup-
    sid = re.sub(r"^[Dd]up-", "", sid)
    
    # Remover sufijo -20mg
    sid = re.sub(r"-\d+mg$", "", sid, flags=re.IGNORECASE)
    
    # Solo remover el sufijo numérico (-1, -2) si hay al menos 2 guiones
    # para evitar romper el ID base S25-XXXXX
    if sid.count("-") >= 2:
        sid = re.sub(r"-\d+$", "", sid)
    
    # Si no tiene prefijo de año (S24-, S25-, S26-), agregar S26-
    if not re.match(r"^S\d{2}-", sid, flags=re.IGNORECASE):
        sid = f"S26-{sid}"
    
    return sid.upper()


def sync_rs_raw(engine: Engine, df: pd.DataFrame, dry_run: bool = False) -> int:
    """Inserta datos del tab RS en glims_rs_results_raw."""
    if df.empty or "Sample ID" not in df.columns:
        LOGGER.warning("DataFrame vacío o sin columna 'Sample ID'")
        return 0
    
    col_mapping = {
        "sample_id": "Sample ID",
        "prep_date": "RS Analysis Prep Date",
        "start_date": "RS Analysis Start Date",
        "lab_analyst": "Lab Analyst",
        "instrument": "Instrument",
        "sample_weight_mg": "Sample Weight (mg)",
        "dilution": "Dilution",
        "acetone": "Acetone",
        "acetonitrile": "Acetonitrile",
        "benzene": "Benzene",
        "butane": "Butane",
        "chloroform": "Chloroform",
        "dichloroethane_1_2": "1,2-Dichloroethane",
        "ethanol": "Ethanol",
        "ethyl_acetate": "Ethyl acetate",
        "ethyl_ether": "Ethyl ether",
        "ethylene_oxide": "Ethylene oxide",
        "heptane": "Heptane",
        "hexane": "Hexane",
        "isopropyl_alcohol": "Isopropyl alcohol",
        "methanol": "Methanol",
        "methylene_chloride": "Methylene chloride",
        "pentane": "Pentane",
        "propane": "Propane",
        "toluene": "Toluene",
        "total_xylenes": "Total xylenes",
        "trichloroethylene": "Trichloroethylene",
        "client": "Client",
        "data_analyst": "Data Analyst",
        "rerun_category": "Rerun Category",
        "note": "Note",
        "batch_id": "Batch ID",
    }
    
    rows = []
    for idx, row in df.iterrows():
        raw_sid = str(row.get("Sample ID") or "").strip()
        if not raw_sid:
            continue
        
        prep = to_date_only(row.get("RS Analysis Prep Date"))
        start = to_date_only(row.get("RS Analysis Start Date"))
        if not prep and not start:
            continue
        
        clean_sid = normalize_sample_id_clean(raw_sid)
        payload = {
            "sample_id": raw_sid,
            "sample_id_clean": clean_sid,
        }
        
        for db_col, sheet_col in col_mapping.items():
            if db_col == "sample_id":
                continue
            val = row.get(sheet_col)
            if db_col in ("prep_date", "start_date"):
                payload[db_col] = to_date_only(val)
            elif db_col in ("sample_weight_mg", "dilution"):
                payload[db_col] = to_num(val)
            else:
                payload[db_col] = val if val and str(val).strip() else None
        
        rows.append(payload)
        
        # Log primeras 5 filas para debug
        if len(rows) <= 5:
            LOGGER.info("Row %d: %s -> %s", idx, raw_sid, clean_sid)
    
    LOGGER.info("Total filas procesadas: %d", len(rows))
    
    if dry_run:
        LOGGER.info("[DRY RUN] No se insertarán datos en la base de datos")
        return len(rows)
    
    if not rows:
        return 0
    
    # Truncar tabla e insertar
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE glims_rs_results_raw"))
        LOGGER.info("Tabla truncada")
    
    cols = rows[0].keys()
    sql = f"""
        INSERT INTO glims_rs_results_raw ({", ".join(cols)})
        VALUES ({", ".join(f":{c}" for c in cols)})
    """
    with engine.begin() as conn:
        conn.execute(text(sql), rows)
    
    return len(rows)


def main() -> None:
    load_env()
    parser = argparse.ArgumentParser(description="Sync RS tab to glims_rs_results_raw")
    parser.add_argument(
        "--spreadsheet-id",
        default=os.environ.get("GSHEETS_SPREADSHEET_ID"),
        help="Google Sheets ID",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Solo procesar datos sin escribir a la DB",
    )
    args = parser.parse_args()

    if not args.spreadsheet_id:
        raise RuntimeError("Must provide --spreadsheet-id or GSHEETS_SPREADSHEET_ID env")

    LOGGER.info("Conectando a Google Sheets...")
    sheet = connect_sheet(args.spreadsheet_id)
    
    LOGGER.info("Descargando tab RS...")
    df = fetch_df(sheet, TAB_RS)
    LOGGER.info("Filas en el sheet: %d", len(df))
    LOGGER.info("Columnas: %s", list(df.columns)[:10])
    
    if not args.dry_run:
        LOGGER.info("Conectando a PostgreSQL...")
        engine = build_engine()
    else:
        engine = None
    
    count = sync_rs_raw(engine, df, dry_run=args.dry_run)
    LOGGER.info("Sincronización completada. Filas insertadas: %d", count)


if __name__ == "__main__":
    main()
