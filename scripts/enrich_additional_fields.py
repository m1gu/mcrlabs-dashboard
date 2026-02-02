"""
Enriquecer campos adicionales de glims_samples desde qbench-backup.csv.

Este script busca campos NULL o vacíos en glims_samples que pertenezcan a Qbench
y los completa con información del backup CSV.

Campos a enriquecer:
- Matrix -> matrix
- Report Date -> report_date
- Order Date -> date_received

Usage:
    python scripts/enrich_additional_fields.py --dry-run
    python scripts/enrich_additional_fields.py
"""

import os
import json
import logging
import argparse
from datetime import datetime
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# --- Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
LOGGER = logging.getLogger(__name__)
load_dotenv()

FIELD_MAP = {
    "Matrix": "matrix",
    "Report Date": "report_date",
    "Order Date": "date_received"
}

def get_engine():
    """Build SQLAlchemy engine from LOCAL_POSTGRES variables."""
    host = os.getenv("LOCAL_POSTGRES_HOST")
    port = os.getenv("LOCAL_POSTGRES_PORT")
    db = os.getenv("LOCAL_POSTGRES_DB")
    user = os.getenv("LOCAL_POSTGRES_USER")
    password = os.getenv("LOCAL_POSTGRES_PASSWORD")
    return create_engine(f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}")

def to_date_str(val):
    """Convierte fecha del CSV (MM/DD/YYYY) a formato ISO (YYYY-MM-DD)."""
    if pd.isna(val) or not str(val).strip():
        return None
    try:
        # El CSV parece tener formato tipo 04/12/2022
        return pd.to_datetime(val).date().isoformat()
    except:
        return None

class EnrichedReporter:
    def __init__(self, dry_run=True):
        self.stats = {
            "started_at": datetime.now().isoformat(),
            "finished_at": None,
            "dry_run": dry_run,
            "fields_processed": {f: 0 for f in FIELD_MAP.values()},
            "total_updates_requested": 0
        }
    
    def save(self, path="scripts/additional_enrichment_report.json"):
        self.stats["finished_at"] = datetime.now().isoformat()
        with open(path, "w") as f:
            json.dump(self.stats, f, indent=2)

def enrich(dry_run=True):
    engine = get_engine()
    reporter = EnrichedReporter(dry_run)
    
    LOGGER.info(f"Starting additional field enrichment (dry_run={dry_run})...")
    
    # 1. Cargar CSV
    LOGGER.info("Step 1: Loading CSV...")
    df = pd.read_csv('qbench-backup.csv', low_memory=False)
    
    # 2. Por cada campo mapeado, buscar huecos y llenar
    with engine.connect() as conn:
        for csv_col, db_col in FIELD_MAP.items():
            LOGGER.info(f"Processing field: {db_col} (from CSV: {csv_col})...")
            
            # Obtener samples donde el campo sea NULL o vacío
            if "date" in db_col:
                query = text(f"SELECT sample_id FROM glims_samples WHERE {db_col} IS NULL")
            else:
                query = text(f"SELECT sample_id FROM glims_samples WHERE {db_col} IS NULL OR {db_col} = ''")
            null_ids = [row[0] for row in conn.execute(query)]
            
            if not null_ids:
                LOGGER.info(f"No NULL values found for {db_col}. Skipping.")
                continue
                
            null_ids_set = set(null_ids)
            updates = []
            
            # Buscar en el CSV
            # Filtramos el CSV para tener solo los IDs que necesitamos
            relevant_df = df[df['Full ID'].isin(null_ids_set) & df[csv_col].notna()]
            
            for _, row in relevant_df.iterrows():
                sid = str(row['Full ID']).strip()
                val = row[csv_col]
                
                # Procesamiento especial para fechas
                if "date" in db_col:
                    val = to_date_str(val)
                
                if val:
                    updates.append({"sample_id": sid, "value": val})
            
            if updates:
                LOGGER.info(f"Found {len(updates)} values to update for {db_col}")
                if not dry_run:
                    with engine.begin() as trans:
                        sql = text(f"UPDATE glims_samples SET {db_col} = :value WHERE sample_id = :sample_id")
                        # Ejecutar en pequeñas transacciones si es necesario, o batch
                        trans.execute(sql, updates)
                
                reporter.stats["fields_processed"][db_col] = len(updates)
                reporter.stats["total_updates_requested"] += len(updates)
            else:
                LOGGER.info(f"No enrichable data found for {db_col}")

    reporter.save()
    LOGGER.info("Enrichment completed.")
    print(json.dumps(reporter.stats, indent=2))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", default=False)
    args = parser.parse_args()
    
    try:
        enrich(dry_run=args.dry_run)
    except Exception as e:
        LOGGER.exception(f"Fatal error: {e}")
        exit(1)
