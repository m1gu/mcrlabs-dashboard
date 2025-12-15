
import os
import sys
import pandas as pd
from sqlalchemy import create_engine, text

# Add src to path
src_path = os.path.join(os.getcwd(), "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

try:
    from glims.client import fetch_df, get_sheet
    from glims.sync import load_env
    from glims.models import normalize_sample_id, extract_start_date, _has_required_fields
    from glims.constants import TAB_HO
except ImportError as e:
    print(f"Error importing modules: {e}")
    sys.exit(1)

def debug_ho():
    load_env()
    sheet = get_sheet()
    print(f"Fetching {TAB_HO}...")
    df = fetch_df(sheet, TAB_HO)
    
    print(f"\n--- Columns found in {TAB_HO} ({len(df.columns)}) ---")
    print(df.columns.tolist())
    
    if df.empty:
        print("DataFrame is empty!")
        return

    print(f"\n--- Checking first 5 rows ---")
    
    mapping = {
        "prep_date": "HO Analysis Prep Date",
        "start_date": "HO analysis Start Date",
        "lab_analyst": "Lab Analyst",
        "instrument": "Instrument",
        "total_thc_1": "Total THC 1 (mg/g)",
        "total_cbd_1": "Total CBD 1 (mg/g)",
        "total_thc_2": "Total THC 2 (mg/g)",
        "total_cbd_2": "Total CBD 2 (mg/g)",
        "total_thc_3": "Total THC 3 (mg/g)",
        "total_cbd_3": "Total CBD 3 (mg/g)",
        "total_thc_rsd": "Total THC (% RSD)",
        "total_cbd_rsd": "Total CBD (% RSD)",
        "data_analyst": "Data Analyst",
        "notes": "Notes",
        "batch_id": "Batch ID",
    }
    
    required_src_cols = [
        "Sample ID",
        "HO Analysis Prep Date",
        "HO analysis Start Date",
        "Lab Analyst",
        "Batch ID",
    ]
    
    # Check Required Cols existence
    missing_cols = [c for c in required_src_cols if c not in df.columns]
    if missing_cols:
        print(f"CRITICAL: The following required columns are MISSING from the dataframe headers: {missing_cols}")
    else:
        print("All required columns present in headers.")

    for i, row in df.head(5).iterrows():
        print(f"\nRow {i}:")
        raw_sid = str(row.get("Sample ID", "")).strip()
        print(f"  Sample ID (Raw): '{raw_sid}'")
        
        clean_sid = normalize_sample_id(raw_sid)
        print(f"  Sample ID (Norm): '{clean_sid}'")
        
        if not clean_sid:
            print("  -> SKIP: No clean sample ID")
            continue

        # Check required fields
        has_req = _has_required_fields(row, required_src_cols)
        print(f"  Has Required Fields: {has_req}")
        if not has_req:
            # Print which ones are missing/empty
            for col in required_src_cols:
                val = row.get(col)
                # Check for empty string or NaN
                is_empty = val is None or (isinstance(val, str) and not val.strip()) or pd.isna(val)
                if is_empty:
                    print(f"    Missing value for: '{col}' (Value: {val!r})")

        # Check start date
        start_dt = extract_start_date(row, mapping)
        print(f"  Start Date: {start_dt}")

if __name__ == "__main__":
    debug_ho()
