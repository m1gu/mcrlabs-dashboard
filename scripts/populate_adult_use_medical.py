"""
Populate glims_samples.adult_use_medical from qbench-backup.csv.

Lee el archivo CSV con datos de Qbench y actualiza el campo adult_use_medical
de los samples que actualmente tienen valor 'Unknown'.

Usage:
    python scripts/populate_adult_use_medical.py --dry-run  # Solo simula
    python scripts/populate_adult_use_medical.py            # Ejecuta real
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

# Mapeo de Type (CSV) -> adult_use_medical (DB)
# Corregido según instrucción del usuario: AU Client R&D -> AU R&D
TYPE_MAP = {
    "Adult Use": "Adult Use",
    "Medical MJ": "Medical",
    "AU Client R&D": "AU R&D"
}

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

class EnrichmentReporter:
    def __init__(self, dry_run=True):
        self.stats = {
            "started_at": datetime.now().isoformat(),
            "finished_at": None,
            "dry_run": dry_run,
            "csv_rows_total": 0,
            "csv_rows_mapped": 0,
            "samples_found_unknown_db": 0,
            "samples_updated": 0,
            "samples_not_found_in_csv": 0,
            "type_distribution_updated": {}
        }
    
    def save(self, path="scripts/adult_use_enrichment_report.json"):
        self.stats["finished_at"] = datetime.now().isoformat()
        with open(path, "w") as f:
            json.dump(self.stats, f, indent=2)

def populate(dry_run=True, batch_size=500):
    engine = get_engine()
    reporter = EnrichmentReporter(dry_run)
    
    LOGGER.info(f"Starting adult_use_medical population (dry_run={dry_run})...")
    
    # 1. Cargar CSV
    LOGGER.info("Step 1: Loading CSV...")
    df = pd.read_csv('qbench-backup.csv', low_memory=False)
    reporter.stats["csv_rows_total"] = len(df)
    
    # Filtrar solo filas con Full ID y Type válidos
    df_mapped = df[df['Full ID'].notna() & df['Type'].notna()].copy()
    reporter.stats["csv_rows_mapped"] = len(df_mapped)
    
    # 2. Preparar mapeo Full ID -> mapped_type
    LOGGER.info("Step 2: Preparing mapping...")
    csv_map = {}
    for _, row in df_mapped.iterrows():
        full_id = str(row['Full ID']).strip()
        csv_type = str(row['Type']).strip()
        mapped_type = TYPE_MAP.get(csv_type, csv_type)
        csv_map[full_id] = mapped_type
    
    # 3. Obtener samples con adult_use_medical = 'Unknown' de la DB
    with engine.connect() as conn:
        LOGGER.info("Step 3: Fetching samples with 'Unknown' adult_use_medical from DB...")
        result = conn.execute(text("SELECT sample_id FROM glims_samples WHERE adult_use_medical = 'Unknown'"))
        db_unknown_ids = [row[0] for row in result]
        reporter.stats["samples_found_unknown_db"] = len(db_unknown_ids)
        
        # 4. Cruzar datos
        updates = []
        updated_counts = {}
        for sid in db_unknown_ids:
            if sid in csv_map:
                target_val = csv_map[sid]
                updates.append({"sample_id": sid, "new_value": target_val})
                updated_counts[target_val] = updated_counts.get(target_val, 0) + 1
            else:
                reporter.stats["samples_not_found_in_csv"] += 1
        
        reporter.stats["type_distribution_updated"] = updated_counts
        
        # 5. Ejecutar actualizaciones
        if not updates:
            LOGGER.info("No updates found to apply.")
        else:
            LOGGER.info(f"Step 4: Executing {len(updates)} updates...")
            if not dry_run:
                # Usar una transacción para el batch
                with engine.begin() as transaction_conn:
                    sql = text("UPDATE glims_samples SET adult_use_medical = :new_value WHERE sample_id = :sample_id")
                    for i in range(0, len(updates), batch_size):
                        batch = updates[i:i+batch_size]
                        transaction_conn.execute(sql, batch)
                        reporter.stats["samples_updated"] += len(batch)
                        LOGGER.info(f"Progress: {reporter.stats['samples_updated']}/{len(updates)} updated...")
            else:
                reporter.stats["samples_updated"] = len(updates)
                LOGGER.info(f"[DRY-RUN] Would update {len(updates)} samples.")

    reporter.save()
    LOGGER.info("Process completed successfully.")
    print(json.dumps(reporter.stats, indent=2))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", default=False)
    parser.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args()
    
    try:
        populate(dry_run=args.dry_run, batch_size=args.batch_size)
    except Exception as e:
        LOGGER.exception(f"Fatal error: {e}")
        exit(1)
