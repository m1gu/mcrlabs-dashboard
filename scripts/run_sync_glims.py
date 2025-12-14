"""
Synchronise GLIMS data from Google Sheets into PostgreSQL.

Usage:
    python scripts/run_sync_glims.py [--lookback-days 30] [--spreadsheet-id <ID>]

Requires:
    - Env vars for DB (POSTGRES_HOST/PORT/DB/USER/PASSWORD or existing .env).
    - GSHEETS_SERVICE_ACCOUNT_FILE pointing to the service account JSON.
    - GSHEETS_SPREADSHEET_ID (optional here if passed via CLI).
"""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping, Sequence

import gspread
import logging
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError


TAB_OVERVIEW = "overview"
TAB_DISPENSARIES = "Dispensaries"
TAB_RERUNS = "Reruns"
TAB_RUNLISTS = "Run Lists"
TAB_CN = "CN"
TAB_MB = "MB"
TAB_HM = "HM"
TAB_WA = "WA"
TAB_FFM = "FFM"
TAB_RS = "RS"
TAB_TP = "TP"
TAB_PS = "PS"
TAB_MY = "MY"
TAB_MC = "MC"
TAB_PN = "PN"
TAB_LW = "LW"

DATE_COLS_OVERVIEW = ["DateReceived", "DateCollected", "ReportDate"]

NUMERIC_FIELDS = {
    "sample_weight_mg",
    "sample_weight_g",
    "serving_weight_mg",
    "servings_per_package",
    "dilution",
    "ym_numerical",
    "net_weight_g",
    "gross_weight_g",
    "number_units_received",
    "lot_size",
    # Heavy metals numeric fields
    "as_val",
    "cd_val",
    "hg_val",
    "pb_val",
    "as_lod",
    "cd_lod",
    "hg_lod",
    "pb_lod",
    "as_loq",
    "cd_loq",
    "hg_loq",
    "pb_loq",
    # Other numeric measurements
    "wa",
    "moisture_content_percent",
}

DATE_ONLY_FIELDS = {
    "prep_date",
    "start_date",
    "ac_cc_eb_read_date",
    "ym_read_date",
    "sal_read_date",
    "stec_read_date",
    "qc_tempo_date",
    "earliest_ac_ym_date",
    "latest_ac_ym_date",
    "latest_stec_sal",
    "analysis_date",
    "qc_date",
    "run_date",
}

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(message)s",
)
LOGGER = logging.getLogger(__name__)
SYNC_SOURCE = "gsheets"


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


def start_sync_run(engine: Engine) -> int:
    sql = """
        INSERT INTO glims_sync_runs (started_at, status, source)
        VALUES (now(), 'running', :source)
        RETURNING id
    """
    with engine.begin() as conn:
        run_id = conn.execute(text(sql), {"source": SYNC_SOURCE}).scalar_one()
    return int(run_id)


def finish_sync_run(engine: Engine, run_id: int, status: str, message: str | None = None) -> None:
    sql = """
        UPDATE glims_sync_runs
        SET finished_at = now(), status = :status, message = :message
        WHERE id = :run_id
    """
    with engine.begin() as conn:
        conn.execute(text(sql), {"status": status, "message": message, "run_id": run_id})


def fetch_df(sh: gspread.Spreadsheet, tab: str) -> pd.DataFrame:
    """Return a DataFrame from the given tab, making headers unique if needed."""

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


def to_ts(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, str) and value.strip().lower() in {"n/a", "na", "nan"}:
        return None
    try:
        parsed = pd.to_datetime(value, errors="coerce", utc=True)
    except Exception:
        return None
    if pd.isna(parsed):
        return None
    return parsed.to_pydatetime()


def to_date(value: Any) -> datetime | None:
    dt = to_ts(value)
    return dt


def to_date_only(value: Any) -> datetime.date | None:
    """Return a date (no timezone) matching the sheet value."""

    ts = to_ts(value)
    if ts is None:
        return None
    return ts.date()


def to_bool(value: Any) -> bool | None:
    if value in (None, "", "NaN"):
        return None
    if isinstance(value, (int, float)):
        return bool(int(value))
    if isinstance(value, str):
        val = value.strip().lower()
        if val in ("1", "true", "yes", "y"):
            return True
        if val in ("0", "false", "no", "n"):
            return False
    return None


def to_num(value: Any) -> float | None:
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


def normalize_disp_name(name: str) -> str:
    """Normalize dispensary names for matching (lower, trim, squeeze spaces, strip punctuation)."""

    if not name:
        return ""
    # lower, trim
    val = name.strip().lower()
    # squeeze multiple spaces
    val = re.sub(r"\s+", " ", val)
    # strip trailing punctuation/spaces
    val = val.strip(" ,.;")
    return val


def normalize_sample_id(raw: str) -> str:
    """Strip only special HO / -N suffixes to match glims_samples.sample_id."""

    if not raw:
        return ""
    sid = raw.strip()
    # Remove HO suffix variants (e.g. -HO1, -HO2-1) and -N
    sid = re.sub(r"-(HO\d+(?:-\d+)?)$", "", sid, flags=re.IGNORECASE)
    sid = re.sub(r"-N$", "", sid, flags=re.IGNORECASE)
    return sid or raw.strip()


def extract_start_date(row: Mapping[str, Any], mapping: dict[str, str]) -> datetime.date | None:
    """Return the start date used to decide if a row is eligible."""

    # Preferred keys in order
    candidates = [
        mapping.get("start_date"),
        mapping.get("analysis_date"),
        mapping.get("tempo_prep_date"),
        mapping.get("run_date"),
    ]
    for key in candidates:
        if not key:
            continue
        val = row.get(key)
        dt = to_date_only(val)
        if dt:
            return dt
    return None


def upsert_dispensaries(engine: Engine, df: pd.DataFrame) -> None:
    if df.empty or "Dispensary" not in df.columns:
        return
    cols = {
        "name": "Dispensary",
        "license_number": "License Number",
        "address": "Address",
        "abbrev": "Abbrev.",
        "hex_code": "Hex Code",
        "adult_use_medical": "Adult Use / Medical",
        "special_reporting_instructions": "Special Reporting Instructions",
        "parent_company": "Parent Company",
        "email": "Email",
        "phone_number": "Phone Number",
        "billing_contact_name": "Billing Contact Name",
        "billing_email": "Billing Email",
    }
    rows: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        name = str(row.get("Dispensary") or "").strip()
        if not name:
            continue
        payload = {"name": name}
        for dst, src in cols.items():
            if dst == "name":
                continue
            payload[dst] = row.get(src)
        rows.append(payload)
    if not rows:
        return
    sql = """
        INSERT INTO glims_dispensaries ({cols})
        VALUES ({vals})
        ON CONFLICT (lower(name)) DO UPDATE SET
            license_number = EXCLUDED.license_number,
            address = EXCLUDED.address,
            abbrev = EXCLUDED.abbrev,
            hex_code = EXCLUDED.hex_code,
            adult_use_medical = EXCLUDED.adult_use_medical,
            special_reporting_instructions = EXCLUDED.special_reporting_instructions,
            parent_company = EXCLUDED.parent_company,
            email = EXCLUDED.email,
            phone_number = EXCLUDED.phone_number,
            billing_contact_name = EXCLUDED.billing_contact_name,
            billing_email = EXCLUDED.billing_email,
            updated_at = now()
    """.format(
        cols=", ".join(rows[0].keys()),
        vals=", ".join(f":{c}" for c in rows[0].keys()),
    )
    with engine.begin() as conn:
        conn.execute(text(sql), rows)


def load_dispensary_map(engine: Engine) -> dict[str, int]:
    """Return mapping of normalized name -> id."""

    sql = "SELECT id, name FROM glims_dispensaries"
    with engine.begin() as conn:
        rows = conn.execute(text(sql)).all()
    return {normalize_disp_name(row.name): row.id for row in rows if row.name}


def upsert_overview(engine: Engine, df: pd.DataFrame, lookback_days: int | None, dispensary_map: dict[str, int]) -> set[str]:
    if df.empty or "SampleID" not in df.columns:
        return set()
    required_groups = [
        ["SampleID"],
        ["DateReceived"],
        ["Client"],
        ["SampleName"],
        ["Matrix"],
        ["RequestedTesting"],
        ["Status"],
        ["Adult Use / Medical", "Adult Use/Medical"],
        ["Gross Weight (g)"],
        ["Sample Double Checked (Initials)"],
    ]
    df["DateReceived_ts"] = df["DateReceived"].apply(to_ts)
    if lookback_days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        df = df[df["DateReceived_ts"].notna()]
        df = df[df["DateReceived_ts"] >= cutoff]
    sample_ids: set[str] = set()
    rows: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        sample_id = str(row.get("SampleID") or "").strip()
        if not sample_id:
            continue
        if not all(any(not _is_blank(row.get(col)) for col in group) for group in required_groups):
            continue
        sample_ids.add(sample_id)
        payload = {
            "sample_id": sample_id,
            "date_received": to_date_only(row.get("DateReceived")),
            "date_collected": to_date_only(row.get("DateCollected")),
            "client_name": row.get("Client"),
            "dispensary_name": row.get("Dispensary"),
            "sample_name": row.get("SampleName"),
            "matrix": row.get("Matrix"),
            "sub_matrix": row.get("Sub-Matrix"),
            "requested_testing": row.get("RequestedTesting"),
            "lot_number": row.get("Lot #"),
            "serving_size_g": to_num(row.get("Serving Size (g)")),
            "servings_per_package": to_num(row.get("Servings Per Package")),
            "case_narrative_codes": row.get("Case Narrative and Qualifier Codes"),
            "initials": row.get("Initials"),
            "report_date": to_date_only(row.get("ReportDate")),
            "notes": row.get("Notes"),
            "billing_notes": row.get("Billing Notes"),
            "cannabinoid_flag": row.get("Cannabinoid(CN)"),
            "terpene_flag": row.get("Terpene(TP)"),
            "pesticides_flag": row.get("Pesticides(PS)"),
            "heavy_metals_flag": row.get("HeavyMetals(HM)"),
            "mb_start": row.get("MB_Start"),
            "mb_end": row.get("MB_End"),
            "ecoli_salmonella": row.get("Ecoli/Salmonella"),
            "aspergillus": row.get("Aspergillus"),
            "mycotoxin_flag": row.get("Mycotoxin(MY)"),
            "residual_solvents_flag": row.get("ResidualSolvents(RS)"),
            "moisture_content_flag": row.get("MoistureContent(MC)"),
            "water_activity_flag": row.get("WaterActivity(WA)"),
            "vitamin_e_flag": row.get("VitaminE(VEA)"),
            "ffm_flag": row.get("FilthForeignMaterial(FFM)"),
            "homogeneity_flag": row.get("HomogeneityTesting(HO)"),
            "leafworks_flag": row.get("Leafworks (LW)"),
            "compliance_randd": row.get("Compliance/R&D"),
            "tests_completed": to_bool(row.get("TestsCompleted?(1=yes,0=no)")),
            "metrc_id": row.get("METRC ID"),
            "client_source_batch": row.get("Client Source Batch"),
            "storage_code": row.get("StorageCode"),
            "sciops_cn_mb": row.get("SciOps:CN/MB"),
            "net_weight_g": to_num(row.get("Net Weight (g)")),
            "revnum": row.get("RevNum"),
            "runlist_priority": row.get("Runlist Priority, 1 = expedited , 2 = normal , 3= hold"),
            "number_units_received": to_num(row.get("Number of Units Received")),
            "lot_size": to_num(row.get("Lot Size")),
            "unit_size": row.get("Unit Size"),
            "sample_collection_site": row.get("Sample Collection Site"),
            "sample_collection_date": to_date_only(row.get("Sample Collection Date")),
            "sample_collection_time": row.get("Sample Collection Time"),
            "sampling_by_mcr": row.get("Sampling by MCR (Y/N)"),
            "sample_double_checked": row.get("Sample Double Checked (Initials)"),
            "cc_sample_id": row.get("CC Sample ID"),
            "status": row.get("Status"),
            "adult_use_medical": row.get("Adult Use / Medical"),
            "gross_weight_g": to_num(row.get("Gross Weight (g)")),
        }
        client_val = str(row.get("Client") or "").strip().lower()
        disp_name = client_val  # usamos el nombre del cliente para mapear dispensary_id
        norm_name = normalize_disp_name(disp_name) if disp_name else ""
        payload["dispensary_id"] = dispensary_map.get(norm_name) if norm_name else None
        rows.append(payload)
    if not rows:
        return set()
    cols = rows[0].keys()
    sql = f"""
        INSERT INTO glims_samples ({", ".join(cols)})
        VALUES ({", ".join(f":{c}" for c in cols)})
        ON CONFLICT (sample_id) DO UPDATE SET
            {", ".join(f"{c}=EXCLUDED.{c}" for c in cols if c != "sample_id")},
            updated_at = now()
    """
    with engine.begin() as conn:
        conn.execute(text(sql), rows)
    return sample_ids


def upsert_reruns(engine: Engine, df: pd.DataFrame, sample_ids: set[str]) -> None:
    if df.empty or "Sample ID" not in df.columns:
        return
    # Allow reruns only for samples that exist either in this sync batch (sample_ids) or already in DB
    candidate_ids: set[str] = set()
    rows: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        sid = str(row.get("Sample ID") or "").strip()
        if not sid:
            continue
        candidate_ids.add(sid)
        rows.append(
            {
                "date": to_date(row.get("Date")),
                "assay": row.get("Assay"),
                "sample_id": sid,
                "rerun_code": row.get("Rerun/Reprep Code"),
                "resolution": row.get("Resolution"),
                "notes": row.get("Notes"),
            }
        )
    if not rows:
        return

    allowed_ids = set(sample_ids)
    missing = list(candidate_ids - allowed_ids)
    if missing:
        with engine.begin() as conn:
            existing = conn.execute(
                text("SELECT sample_id FROM glims_samples WHERE sample_id = ANY(:ids)"),
                {"ids": missing},
            ).scalars()
            allowed_ids.update(existing)

    filtered_rows = [r for r in rows if r["sample_id"] in allowed_ids]
    if not filtered_rows:
        return

    sql = """
        INSERT INTO glims_reruns (date, assay, sample_id, rerun_code, resolution, notes)
        VALUES (:date, :assay, :sample_id, :rerun_code, :resolution, :notes)
    """
    with engine.begin() as conn:
        conn.execute(text(sql), filtered_rows)


def upsert_runlists(engine: Engine, df: pd.DataFrame) -> None:
    if df.empty:
        return
    rows = []
    for idx, row in df.iterrows():
        payload = {k: v for k, v in row.items() if v not in (None, "", float("nan"))}
        rows.append({"row_number": idx + 1, "data": json.dumps(payload)})
    sql = """
        INSERT INTO glims_runlists_raw (row_number, data)
        VALUES (:row_number, :data)
    """
    with engine.begin() as conn:
        conn.execute(text(sql), rows)


def split_fields(row: Mapping[str, Any], known: Iterable[str], id_field: str) -> tuple[dict[str, Any], dict[str, Any]]:
    known_set = set(known) | {id_field}
    main = {k: row.get(k) for k in known if k in row}
    analytes: dict[str, Any] = {}
    for k, v in row.items():
        if k in known_set:
            continue
        if v in (None, "", float("nan")):
            continue
        analytes[k] = v
    return main, analytes


def _has_required_fields(row: Mapping[str, Any], cols: Sequence[str]) -> bool:
    for col in cols:
        val = row.get(col)
        if _is_blank(val):
            return False
    return True


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    try:
        import math
        return isinstance(value, float) and math.isnan(value)
    except Exception:
        return False


def upsert_generic_assay(
    engine: Engine,
    df: pd.DataFrame,
    sample_ids: set[str],
    table: str,
    mapping: dict[str, str],
    analyte_cols: Iterable[str] | None = None,
    required_src_cols: Sequence[str] | None = None,
) -> None:
    if df.empty or "Sample ID" not in df.columns:
        return
    rows = []
    known_src = list(mapping.values())
    candidate_ids: set[str] = set()
    for _, row in df.iterrows():
        raw_sid = str(row.get("Sample ID") or "").strip()
        clean_sid = normalize_sample_id(raw_sid)
        if not clean_sid:
            continue
        if required_src_cols and not _has_required_fields(row, required_src_cols):
            continue
        # require start date
        start_dt = extract_start_date(row, mapping)
        if start_dt is None:
            continue
        if sample_ids and clean_sid not in sample_ids:
            continue

        main, analytes = split_fields(row, known_src, "Sample ID")
        payload = {"sample_id": clean_sid, "sample_id_raw": raw_sid or None}
        for dst, src in mapping.items():
            val = main.get(src)
            if dst in NUMERIC_FIELDS:
                payload[dst] = to_num(val)
            elif dst in DATE_ONLY_FIELDS or dst.endswith("_date") or dst.endswith("_start") or dst.endswith("_prep"):
                payload[dst] = to_date_only(val)
            elif "date" in dst:
                payload[dst] = to_ts(val)
            else:
                payload[dst] = val
        if analyte_cols is not None:
            analytes = {k: v for k, v in analytes.items() if k in analyte_cols}
        payload["analytes"] = json.dumps(analytes) if analytes else None
        payload["status"] = "Completed" if payload.get("analytes") else "Batched"
        rows.append(payload)
        candidate_ids.add(clean_sid)
    if not rows:
        return

    allowed_ids = set(sample_ids)
    missing = list(candidate_ids - allowed_ids)
    if missing:
        with engine.begin() as conn:
            existing = conn.execute(
                text("SELECT sample_id FROM glims_samples WHERE sample_id = ANY(:ids)"),
                {"ids": missing},
            ).scalars()
            allowed_ids.update(existing)
    # If no allowed_ids, skip inserting to avoid FK errors
    rows = [r for r in rows if r["sample_id"] in allowed_ids]
    if not rows:
        return

    cols = rows[0].keys()
    update_parts = []
    for c in cols:
        if c == "sample_id":
            continue
        if c == "status":
            update_parts.append(
                f"status = CASE "
                f"WHEN {table}.status = 'Completed' THEN {table}.status "
                f"WHEN EXCLUDED.status = 'Completed' THEN 'Completed' "
                f"ELSE EXCLUDED.status END"
            )
        else:
            update_parts.append(f"{c}=EXCLUDED.{c}")

    sql = f"""
        INSERT INTO {table} ({", ".join(cols)})
        VALUES ({", ".join(f":{c}" for c in cols)})
        ON CONFLICT (sample_id) DO UPDATE SET
            {", ".join(update_parts)},
            updated_at = now()
    """
    with engine.begin() as conn:
        conn.execute(text(sql), rows)


def main() -> None:
    load_env()
    parser = argparse.ArgumentParser()
    parser.add_argument("--spreadsheet-id", default=os.environ.get("GSHEETS_SPREADSHEET_ID"), help="Google Sheets ID")
    parser.add_argument("--lookback-days", type=int, default=int(os.environ.get("GLIMS_SYNC_LOOKBACK_DAYS", "30")))
    parser.add_argument(
        "--ignore-lookback",
        action="store_true",
        help="Process all records without date_received cutoff (overrides lookback-days).",
    )
    args = parser.parse_args()

    if not args.spreadsheet_id:
        raise RuntimeError("Must provide --spreadsheet-id or GSHEETS_SPREADSHEET_ID env")

    effective_lookback = None if args.ignore_lookback else args.lookback_days
    LOGGER.info("Starting GLIMS sync (lookback_days=%s)", effective_lookback)
    sheet = connect_sheet(args.spreadsheet_id)
    engine = build_engine()
    results: list[dict[str, str | int]] = []

    run_id: int | None = None
    try:
        run_id = start_sync_run(engine)
    except SQLAlchemyError as exc:  # noqa: BLE001
        LOGGER.warning("Could not register sync run: %s", exc)

    def record(tab: str, status: str, rows: int = 0, error: str | None = None) -> None:
        entry: dict[str, str | int] = {"tab": tab, "status": status, "rows": rows}
        if error:
            entry["error"] = error
        results.append(entry)

    df_disp = fetch_df(sheet, TAB_DISPENSARIES)
    try:
        upsert_dispensaries(engine, df_disp)
        record(TAB_DISPENSARIES, "ok", len(df_disp))
    except Exception as exc:  # noqa: BLE001
        record(TAB_DISPENSARIES, "error", len(df_disp), str(exc))
        if run_id:
            finish_sync_run(engine, run_id, "failed", f"{TAB_DISPENSARIES}: {exc}")
        raise
    dispensary_map = load_dispensary_map(engine)

    df_overview = fetch_df(sheet, TAB_OVERVIEW)
    try:
        sample_ids = upsert_overview(engine, df_overview, effective_lookback, dispensary_map)
        record(TAB_OVERVIEW, "ok", len(sample_ids))
    except Exception as exc:  # noqa: BLE001
        record(TAB_OVERVIEW, "error", len(df_overview), str(exc))
        if run_id:
            finish_sync_run(engine, run_id, "failed", f"{TAB_OVERVIEW}: {exc}")
        raise

    df_reruns = fetch_df(sheet, TAB_RERUNS)
    try:
        upsert_reruns(engine, df_reruns, sample_ids)
        record(TAB_RERUNS, "ok", len(df_reruns))
    except Exception as exc:  # noqa: BLE001
        record(TAB_RERUNS, "error", len(df_reruns), str(exc))
        raise

    df_runlists = fetch_df(sheet, TAB_RUNLISTS)
    try:
        upsert_runlists(engine, df_runlists)
        record(TAB_RUNLISTS, "ok", len(df_runlists))
    except Exception as exc:  # noqa: BLE001
        record(TAB_RUNLISTS, "error", len(df_runlists), str(exc))
        raise

    def run_assay(
        tab: str,
        table: str,
        mapping: dict[str, str],
        analyte_cols: Iterable[str] | None = None,
        required_src_cols: Sequence[str] | None = None,
    ) -> None:
        df = fetch_df(sheet, tab)
        try:
            upsert_generic_assay(engine, df, sample_ids, table, mapping, analyte_cols, required_src_cols)
            record(tab, "ok", len(df))
        except Exception as exc:  # noqa: BLE001
            record(tab, "error", len(df), str(exc))
            raise

    # Assays
    run_assay(
        TAB_CN,
        "glims_cn_results",
        mapping={
            "prep_date": "CN Analysis Prep Date",
            "start_date": "CN Analysis Start Date",
            "analyst": "Analyst",
            "dilution": "Dilution",
            "sample_weight_mg": "Sample Weight (mg)",
            "instrument": "Instrument",
            "matrix": "Matrix",
            "auth_code": "Authorization",
            "serving_weight_mg": "serving weight (mg; edibles only)",
            "servings_per_package": "servings per package (edibles only)",
            "notes": "Notes",
            "batch_id": "Batch ID",
        },
        required_src_cols=[
            "Sample ID",
            "CN Analysis Prep Date",
            "CN Analysis Start Date",
            "Analyst",
            "Batch ID",
        ],
    )

    run_assay(
        TAB_MB,
        "glims_mb_results",
        mapping={
            "adult_use_medical": "Adult Use/Medical",
            "sample_weight_mg": "Sample Weight (mg)",
            "ac": "AC",
            "ym": "YM",
            "eb": "EB",
            "cc": "CC",
            "sal": "Sal",
            "stec": "STEC",
            "tempo_prep_date": "Tempo Prep Date",
            "tempo_prep_time": "Tempo Prep Time",
            "lab_analyst_mb": "Lab Analyst - MB",
            "lab_analyst_stec_sal": "Lab Analyst - STEC/Sal",
            "ac_cc_eb_read_date": "AC/CC/EB Read Date",
            "ac_cc_eb_read_time": "AC/CC/EB Read Time",
            "ym_read_date": "YM Read Date",
            "ym_read_time": "YM Read Time",
            "sal_read_date": "Sal Read Date",
            "stec_read_date": "STEC Read Date",
            "qc_tempo_date": "QC Tempo date",
            "qc_tempo_analyst": "QC Tempo Analyst",
            "client": "Client",
            "data_analyst_ac_cc_eb": "Data Analyst-AC/CC/EB",
            "data_analyst_ym": "Data Analyst-YM",
            "data_analyst_pathogens": "Data Analyst-Pathogens",
            "rerun_category": "Rerun Category",
            "note_category": "Note (Category)",
            "rerun_effect": "Rerun effect",
            "note_effect": "Note (Effect)",
            "sample_id_repeated": "Sample ID - Repeated",
            "ac_no_parenthesis": "AC No Parenthesis",
            "ym_no_parenthesis": "YM No Parenthesis",
            "sal_no_parenthesis": "Sal No Parenthesis",
            "stec_no_parenthesis": "STEC No Parenthesis",
            "earliest_ac_ym_date": "Earliest AC/YM Date",
            "latest_ac_ym_date": "Latest AC/YM Date",
            "latest_stec_sal": "Latest STEC/Salmonella",
            "ym_numerical": "YM Numerical",
            "batch_id": "Batch ID",
        },
        required_src_cols=[
            "Sample ID",
            "Sample Weight (mg)",
            "Tempo Prep Date",
            "Tempo Prep Time",
            "Lab Analyst - MB",
            "Batch ID",
        ],
    )

    run_assay(
        TAB_HM,
        "glims_hm_results",
        mapping={
            "prep_date": "HM Analysis Prep Date",
            "start_date": "HM Analysis Start Date",
            "lab_analyst": "Lab Analyst",
            "dilution": "Dilution",
            "sample_weight_mg": "Sample Weight (mg)",
            "instrument": "Instrument",
            "as_val": "As",
            "cd_val": "Cd",
            "hg_val": "Hg",
            "pb_val": "Pb",
            "as_lod": "As LOD",
            "cd_lod": "Cd LOD",
            "hg_lod": "Hg LOD",
            "pb_lod": "Pb LOD",
            "as_loq": "As LOQ",
            "cd_loq": "Cd LOQ",
            "hg_loq": "Hg LOQ",
            "pb_loq": "Pb LOQ",
            "client": "Client",
            "analyst": "Analyst",
            "rerun_category": "Rerun Category",
            "note": "Note",
            "batch_id": "Batch ID",
        },
        required_src_cols=[
            "Sample ID",
            "HM Analysis Prep Date",
            "HM Analysis Start Date",
            "Lab Analyst",
            "Batch ID",
        ],
    )

    run_assay(
        TAB_WA,
        "glims_wa_results",
        mapping={
            "matrix": "Matrix",
            "sub_matrix": "Sub-Matrix",
            "instrument": "Instrument",
            "lab_analyst": "Lab Analyst",
            "prep_date": "WA Analysis Prep Date",
            "start_date": "WA Analysis Start Date",
            "sample_weight_g": "Sample Weight (g)",
            "wa": "WA",
            "notes": "Notes",
            "batch_id": "Batch ID",
            "duplicate_rpd_log": "WA Batch Duplicate RPD Check Log",
        },
        required_src_cols=[
            "Sample ID",
            "WA Analysis Prep Date",
            "WA Analysis Start Date",
            "Lab Analyst",
            "Batch ID",
        ],
    )

    run_assay(
        TAB_FFM,
        "glims_ffm_results",
        mapping={
            "analysis_date": "Analysis Date",
            "analysis_time": "Analysis Time",
            "lab_analyst": "Lab Analyst",
            "pass_fail": "Pass / Fail",
            "fail_pictures_notes": "Filth and Foreign Materials FAIL Pictures and Notes",
            "batch_id": "Batch ID",
        },
        required_src_cols=[
            "Sample ID",
            "Analysis Date",
            "Analysis Time",
            "Lab Analyst",
            "Batch ID",
        ],
    )

    run_assay(
        TAB_RS,
        "glims_rs_results",
        mapping={
            "prep_date": "RS Analysis Prep Date",
            "start_date": "RS Analysis Start Date",
            "lab_analyst": "Lab Analyst",
            "instrument": "Instrument",
            "sample_weight_mg": "Sample Weight (mg)",
            "dilution": "Dilution",
            "qc_date": "QC Date",
            "qc_analyst": "QC Analyst",
            "client": "Client",
            "data_analyst": "Data Analyst",
            "rerun_category": "Rerun Category",
            "note": "Note",
            "batch_id": "Batch ID",
        },
        required_src_cols=[
            "Sample ID",
            "RS Analysis Prep Date",
            "RS Analysis Start Date",
            "Lab Analyst",
            "Batch ID",
        ],
    )

    run_assay(
        TAB_TP,
        "glims_tp_results",
        mapping={
            "prep_date": "TP Analysis Prep Date",
            "start_date": "TP Analysis Start Date",
            "dilution": "Dilution",
            "sample_weight_mg": "Sample Weight (mg)",
            "lab_analyst": "Lab Analyst",
            "instrument": "Instrument",
            "client": "Client",
            "data_analyst": "Data Analyst",
            "rerun_category": "Rerun Category",
            "note": "Note",
            "batch_id": "Batch ID",
        },
        required_src_cols=[
            "Sample ID",
            "TP Analysis Prep Date",
            "TP Analysis Start Date",
            "Lab Analyst",
            "Batch ID",
        ],
    )

    run_assay(
        TAB_PS,
        "glims_ps_results",
        mapping={
            "prep_date": "PS Analysis Prep Date",
            "start_date": "PS Analysis Start Date",
            "lab_analyst": "Lab Analyst",
            "sample_weight_mg": "Sample Weight (mg)",
            "instrument": "Instrument",
            "data_analyst": "Data Analyst",
            "rerun_category": "Rerun Category",
            "note": "Note",
            "batch_id": "Batch ID",
        },
        required_src_cols=[
            "Sample ID",
            "PS Analysis Prep Date",
            "PS Analysis Start Date",
            "Lab Analyst",
            "Batch ID",
        ],
    )

    run_assay(
        TAB_MY,
        "glims_my_results",
        mapping={
            "prep_date": "MY Analysis Prep Date",
            "start_date": "MY Analysis Start Date",
            "lab_analyst": "Lab Analyst",
            "sample_weight_mg": "Sample Weight (mg)",
            "instrument": "Instrument",
            "client": "Client",
            "data_analyst": "Data Analyst",
            "rerun_category": "Rerun Category",
            "note": "Note",
            "batch_id": "Batch ID",
        },
        required_src_cols=[
            "Sample ID",
            "MY Analysis Prep Date",
            "MY Analysis Start Date",
            "Lab Analyst",
            "Batch ID",
        ],
    )

    run_assay(
        TAB_MC,
        "glims_mc_results",
        mapping={
            "instrument": "Instrument",
            "analyst": "Analyst",
            "prep_date": "MC Analysis Prep Date",
            "start_date": "MC Analysis Start Date",
            "sample_weight_g": "Sample Weight (g)",
            "moisture_content_percent": "Moisture Content Percent",
            "leco_start_time": "LECO Start Time",
            "leco_end_time": "LECO End Time",
            "notes": "Notes",
            "batch_id": "Batch ID",
        },
        required_src_cols=[
            "Sample ID",
            "MC Analysis Prep Date",
            "MC Analysis Start Date",
            "Analyst",
            "Batch ID",
        ],
    )

    run_assay(
        TAB_PN,
        "glims_pn_results",
        mapping={
            "prep_date": "PN Analysis Prep Date",
            "start_date": "PN Analysis Start Date",
            "lab_analyst": "Lab Analyst",
            "dilution": "Dilution",
            "sample_weight_mg": "Sample Weight (mg)",
            "instrument": "Instrument",
            "client": "Client",
            "analyst": "Analyst",
            "rerun_category": "Rerun Category",
            "note": "Note",
            "batch_id": "Batch ID",
        },
        required_src_cols=[
            "Sample ID",
            "PN Analysis Prep Date",
            "PN Analysis Start Date",
            "Lab Analyst",
            "Batch ID",
        ],
    )

    run_assay(
        TAB_LW,
        "glims_lw_results",
        mapping={
            "run_date": "Run Date",
            "run_time": "Run Time",
            "eqf": "EQF",
            "lab_analyst": "Lab Analyst",
            "test_requested": "Test Requested",
            "result": "Result",
            "note": "Note",
            "batch_id": "Batch ID",
        },
        required_src_cols=[
            "Sample ID",
            "Run Date",
            "Run Time",
            "Lab Analyst",
            "Test Requested",
            "Batch ID",
        ],
    )

    LOGGER.info("Completed GLIMS sync. Samples processed: %s", len(sample_ids))
    LOGGER.info("Summary per tab:")
    for entry in results:
        if entry.get("status") == "ok":
            LOGGER.info(" - %-15s status=%s rows=%s", entry["tab"], entry["status"], entry.get("rows", 0))
        else:
            LOGGER.error(
                " - %-15s status=%s rows=%s error=%s",
                entry["tab"],
                entry["status"],
                entry.get("rows", 0),
                entry.get("error"),
            )
    if "run_id" in locals() and run_id:
        try:
            finish_sync_run(engine, run_id, "success")
        except SQLAlchemyError as exc:  # noqa: BLE001
            LOGGER.warning("Could not mark sync run success: %s", exc)


if __name__ == "__main__":
    main()
