"""
Migración de resultados de tests de Qbench a tablas glims_*_results.
Utiliza qbench-backup.csv como fuente de datos.
"""

import os
import json
import logging
import argparse
from datetime import datetime
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# --- Setup Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
LOGGER = logging.getLogger(__name__)

load_dotenv()

# --- Configuration & Mappings ---

# Cannabinoids
CN_COLS = [
    "CBDVA %", "CBDV %", "CBDA %", "CBGA %", "CBG %", "CBD %", "THCV %", "THCVA %",
    "CBCV %", "CBN %", "D9 THC %", "D8 THC %", "CBL %", "THCA %", "CBC %", "CBCA %",
    "CBLA %", "CBT %", "Total THC %", "Total CBD %", "Total CN %"
]

# Heavy Metals
HM_COLS = ["Arsenic ug/kg", "Cadmium ug/kg", "Mercury ug/kg", "Lead ug/kg"]

# Microbiology
MB_COLS = [
    "Yeast Mold CFU/g", "Aerobic Count CFU/g", "Enterobacteriaceae CFU/g",
    "Coliform Bacteria CFU/g", "Salmonella", "E.Coli"
]

# Residual Solvents
RS_COLS = [
    "Acetone", "Acetonitrile", "Ethanol", "Pentane", "Ethyl Acetate", "Ethyl Ether",
    "Heptane", "Hexane", "Isopropyl Alcohol", "Methanol", "Toluene", "Total Xylenes",
    "Butane", "Propane", "1,2-Dichloroethane", "Chloroform", "Benzene",
    "Methylene Chloride", "Trichloroethylene", "Ethylene Oxide"
]

# Terpenes are dynamic (identified by % and not in CN_COLS)
def get_tp_cols(all_cols):
    tp = [c for c in all_cols if '%' in c and c not in CN_COLS and "Total" not in c and "RSD" not in c]
    return tp

def get_engine():
    """Build SQLAlchemy engine from LOCAL_POSTGRES variables."""
    host = os.getenv("LOCAL_POSTGRES_HOST")
    port = os.getenv("LOCAL_POSTGRES_PORT")
    db = os.getenv("LOCAL_POSTGRES_DB")
    user = os.getenv("LOCAL_POSTGRES_USER")
    password = os.getenv("LOCAL_POSTGRES_PASSWORD")
    
    if not all([host, port, db, user, password]):
        raise ValueError("Missing required LOCAL_POSTGRES_* environment variables")
        
    return create_engine(f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}")

class MigrationReporter:
    def __init__(self, dry_run=True):
        self.stats = {
            "started_at": datetime.now().isoformat(),
            "finished_at": None,
            "dry_run": dry_run,
            "total_rows_csv": 0,
            "inserted": {
                "glims_cn_results": 0,
                "glims_hm_results": 0,
                "glims_tp_results": 0,
                "glims_mb_results": 0,
                "glims_rs_results": 0
            }
        }
    
    def save(self, path="scripts/qbench_results_migration_report.json"):
        self.stats["finished_at"] = datetime.now().isoformat()
        with open(path, "w") as f:
            json.dump(self.stats, f, indent=2)

def migrate(dry_run=True, batch_size=500):
    engine = get_engine()
    reporter = MigrationReporter(dry_run)
    
    LOGGER.info(f"Starting Qbench results migration (dry_run={dry_run})...")
    
    # 1. Loading CSV
    LOGGER.info("Step 1: Loading CSV...")
    df = pd.read_csv('qbench-backup.csv', low_memory=False)
    reporter.stats["total_rows_csv"] = len(df)
    cols = list(df.columns)
    tp_cols = get_tp_cols(cols)
    LOGGER.info(f"Identified {len(tp_cols)} terpene columns.")
    
    # 2. Get valid sample IDs from DB to avoid ForeignKeyViolation
    LOGGER.info("Step 2: Fetching valid sample_ids from glims_samples...")
    with engine.connect() as conn:
        result = conn.execute(text("SELECT sample_id FROM glims_samples"))
        valid_sample_ids = {row[0] for row in result}
    LOGGER.info(f"Found {len(valid_sample_ids)} valid sample_ids in DB.")
    
    # 3. Preparation of mappings for iteration
    categories = [
        ("glims_cn_results", CN_COLS),
        ("glims_hm_results", HM_COLS),
        ("glims_tp_results", tp_cols),
        ("glims_mb_results", MB_COLS),
        ("glims_rs_results", RS_COLS)
    ]
    
    # 4. Process by table
    for table_name, category_cols in categories:
        LOGGER.info(f"Processing table {table_name}...")
        
        # Filter rows that have at least one analyte for this category AND exist in DB
        mask = df[category_cols].notna().any(axis=1)
        target_df = df[mask & df['Full ID'].notna()].copy()
        
        # Filter by valid IDs
        total_before_filter = len(target_df)
        target_df = target_df[target_df['Full ID'].isin(valid_sample_ids)]
        if total_before_filter > len(target_df):
            LOGGER.warning(f"Filtered out {total_before_filter - len(target_df)} records for {table_name} because their sample_id is not in glims_samples.")
        
        if target_df.empty:
            LOGGER.info(f"No records for {table_name} after filtering. Skipping.")
            continue
            
        rows_to_insert = []
        for _, row in target_df.iterrows():
            sample_id = str(row['Full ID']).strip()
            
            # Build analytes JSON
            analytes = {}
            for col in category_cols:
                val = row[col]
                if pd.notna(val) and str(val).strip() != "":
                    analytes[col] = val
                    
            if not analytes:
                continue
                
            insert_row = {
                "sample_id": sample_id,
                "sample_id_raw": sample_id,
                "analytes": json.dumps(analytes),
                "status": "Completed", 
                "updated_at": datetime.now()
            }
            rows_to_insert.append(insert_row)
            
        LOGGER.info(f"Found {len(rows_to_insert)} records to insert into {table_name}")
        
        if not dry_run and rows_to_insert:
            # Batch insertion with ON CONFLICT
            sql = text(f"""
                INSERT INTO {table_name} (sample_id, sample_id_raw, analytes, status, updated_at)
                VALUES (:sample_id, :sample_id_raw, :analytes, :status, :updated_at)
                ON CONFLICT (sample_id) DO NOTHING
            """)
            
            with engine.begin() as conn:
                for i in range(0, len(rows_to_insert), batch_size):
                    batch = rows_to_insert[i : i + batch_size]
                    conn.execute(sql, batch)
                    reporter.stats["inserted"][table_name] += len(batch)
            LOGGER.info(f"Finished inserting into {table_name}.")
        else:
            reporter.stats["inserted"][table_name] = len(rows_to_insert)

    reporter.save()
    LOGGER.info("Migration process finished.")
    print(json.dumps(reporter.stats, indent=2))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", default=False)
    parser.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args()
    
    try:
        migrate(dry_run=args.dry_run, batch_size=args.batch_size)
    except Exception as e:
        LOGGER.exception(f"Fatal error during migration: {e}")
        exit(1)
