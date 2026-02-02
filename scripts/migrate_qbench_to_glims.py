"""
Migrate Qbench legacy data to GLIMS tables.

This script migrates customers to glims_dispensaries and samples to glims_samples,
applying business rules for conflicts and data normalization.
"""

import os
import json
import logging
import argparse
from datetime import datetime
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# --- Setup Logging ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
LOGGER = logging.getLogger(__name__)

# --- Load Environment ---
load_dotenv()

def get_engine():
    """Build SQLAlchemy engine from LOCAL_POSTGRES variables."""
    host = os.getenv("LOCAL_POSTGRES_HOST")
    port = os.getenv("LOCAL_POSTGRES_PORT")
    db = os.getenv("LOCAL_POSTGRES_DB")
    user = os.getenv("LOCAL_POSTGRES_USER")
    password = os.getenv("LOCAL_POSTGRES_PASSWORD")
    
    if not all([host, port, db, user, password]):
        raise ValueError("Missing required LOCAL_POSTGRES_* environment variables")
        
    url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"
    return create_engine(url)

class MigrationReporter:
    def __init__(self, dry_run=True):
        self.stats = {
            "started_at": datetime.now().isoformat(),
            "finished_at": None,
            "dry_run": dry_run,
            "customers": {"total": 0, "migrated": 0, "matched_existing": 0, "errors": 0},
            "samples": {"total": 0, "migrated": 0, "skipped_conflict": 0, "skipped_no_id": 0, "errors": 0}
        }
    
    def save(self, path="migration_report.json"):
        self.stats["finished_at"] = datetime.now().isoformat()
        with open(path, "w") as f:
            json.dump(self.stats, f, indent=2)

def migrate(dry_run=True, batch_size=500):
    engine = get_engine()
    reporter = MigrationReporter(dry_run)
    customer_map = {} # qbench_id -> glims_id
    
    LOGGER.info(f"Starting migration (dry_run={dry_run})...")
    
    with engine.connect() as conn:
        # 1. MIGRAR CUSTOMERS -> glims_dispensaries
        LOGGER.info("Step 1: Migrating customers...")
        q_customers = conn.execute(text("SELECT id, name FROM customers")).all()
        reporter.stats["customers"]["total"] = len(q_customers)
        
        for q_cust in q_customers:
            cust_id, cust_name = q_cust
            # Search by lower name
            existing = conn.execute(
                text("SELECT id FROM glims_dispensaries WHERE LOWER(name) = LOWER(:name)"),
                {"name": cust_name}
            ).scalar()
            
            if existing:
                customer_map[cust_id] = existing
                reporter.stats["customers"]["matched_existing"] += 1
            else:
                if not dry_run:
                    new_id = conn.execute(
                        text("INSERT INTO glims_dispensaries (name) VALUES (:name) RETURNING id"),
                        {"name": cust_name}
                    ).scalar()
                    conn.commit()
                    customer_map[cust_id] = new_id
                    reporter.stats["customers"]["migrated"] += 1
                else:
                    # Simulation: we don't have a real ID, but we count it
                    reporter.stats["customers"]["migrated"] += 1
        
        # 2. MIGRAR SAMPLES -> glims_samples
        LOGGER.info("Step 2: Migrating samples...")
        
        # Pre-load existing GLIMS IDs to avoid redundant queries
        existing_glims_ids = set(conn.execute(text("SELECT sample_id FROM glims_samples")).scalars().all())
        
        # Fetch Qbench samples with order/customer info
        q_samples_query = text("""
            SELECT 
                s.id, s.sample_name, s.custom_formatted_id, s.metrc_id, 
                s.matrix_type, s.date_created, s.completed_date, s.state,
                s.sample_weight, o.customer_account_id, c.name as customer_name
            FROM samples s
            JOIN orders o ON o.id = s.order_id
            JOIN customers c ON c.id = o.customer_account_id
        """)
        
        q_samples = conn.execute(q_samples_query).all()
        reporter.stats["samples"]["total"] = len(q_samples)
        
        batch = []
        for s in q_samples:
            # Rule R3: Determine sample_id
            original_id = s.custom_formatted_id.strip() if (s.custom_formatted_id and s.custom_formatted_id.strip()) else None
            glims_sample_id = original_id or f"QB-{s.id}"
            
            if not original_id:
                reporter.stats["samples"]["skipped_no_id"] += 1
            
            # Rule R1: Skip if already exists in GLIMS
            if glims_sample_id in existing_glims_ids:
                reporter.stats["samples"]["skipped_conflict"] += 1
                continue
            
            # Map dispensary_id
            disp_id = customer_map.get(s.customer_account_id)
            
            # Prepare row
            row = {
                "sample_id": glims_sample_id,
                "date_received": s.date_created.date() if s.date_created else None,
                "report_date": s.completed_date.date() if s.completed_date else None,
                "client_name": s.customer_name,
                "dispensary_id": disp_id,
                "sample_name": s.sample_name,
                "matrix": s.matrix_type,
                "status": s.state or "Unknown",
                "adult_use_medical": "Unknown", # Rule R4
                "metrc_id": s.metrc_id,
                "gross_weight_g": float(s.sample_weight) if s.sample_weight else None
            }
            batch.append(row)
            
            if len(batch) >= batch_size:
                if not dry_run:
                    _insert_batch(conn, batch)
                reporter.stats["samples"]["migrated"] += len(batch)
                batch = []
                LOGGER.info(f"Processed {reporter.stats['samples']['migrated']} samples...")
        
        # Last batch
        if batch:
            if not dry_run:
                _insert_batch(conn, batch)
            reporter.stats["samples"]["migrated"] += len(batch)
            LOGGER.info(f"Processed {reporter.stats['samples']['migrated']} samples.")

    reporter.save()
    LOGGER.info("Migration finished.")
    print(json.dumps(reporter.stats, indent=2))

def _insert_batch(conn, batch):
    sql = text("""
        INSERT INTO glims_samples (
            sample_id, date_received, report_date, client_name, dispensary_id,
            sample_name, matrix, status, adult_use_medical, metrc_id, gross_weight_g
        ) VALUES (
            :sample_id, :date_received, :report_date, :client_name, :dispensary_id,
            :sample_name, :matrix, :status, :adult_use_medical, :metrc_id, :gross_weight_g
        ) ON CONFLICT (sample_id) DO NOTHING
    """)
    conn.execute(sql, batch)
    conn.commit()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", default=False)
    parser.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args()
    
    try:
        migrate(dry_run=args.dry_run, batch_size=args.batch_size)
    except Exception as e:
        LOGGER.exception(f"Migration failed: {e}")
        exit(1)
