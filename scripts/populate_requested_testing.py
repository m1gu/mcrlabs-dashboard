"""
Populate glims_samples.requested_testing from Qbench tests table.

This script aggregates label_abbr from the legacy tests table and updates the
requested_testing field in the unified glims_samples table.
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

class PopulationReporter:
    def __init__(self, dry_run=True):
        self.stats = {
            "started_at": datetime.now().isoformat(),
            "finished_at": None,
            "dry_run": dry_run,
            "samples_found": 0,
            "samples_updated": 0,
            "samples_skipped": 0,
            "errors": 0
        }
    
    def save(self, path="requested_testing_report.json"):
        self.stats["finished_at"] = datetime.now().isoformat()
        with open(path, "w") as f:
            json.dump(self.stats, f, indent=2)

def populate(dry_run=True, batch_size=500):
    engine = get_engine()
    reporter = PopulationReporter(dry_run)
    
    LOGGER.info(f"Starting requested_testing population (dry_run={dry_run})...")
    
    with engine.connect() as conn:
        # Query to aggregate label_abbr for each sample
        # We only care about samples that were migrated (adult_use_medical = 'Unknown')
        # and where requested_testing is currently empty or NULL
        LOGGER.info("Step 1: Fetching aggregated tests data from Qbench...")
        agg_query = text("""
            SELECT 
                s.custom_formatted_id AS sample_id,
                STRING_AGG(DISTINCT t.label_abbr, ', ' ORDER BY t.label_abbr) AS tests_list
            FROM samples s
            JOIN tests t ON t.sample_id = s.id
            JOIN glims_samples gs ON gs.sample_id = s.custom_formatted_id
            WHERE s.custom_formatted_id IS NOT NULL
              AND gs.adult_use_medical = 'Unknown'
              AND (gs.requested_testing IS NULL OR gs.requested_testing = '')
            GROUP BY s.custom_formatted_id
        """)
        
        results = conn.execute(agg_query).all()
        reporter.stats["samples_found"] = len(results)
        LOGGER.info(f"Found {len(results)} samples to update.")
        
        batch = []
        for row in results:
            batch.append({
                "sample_id": row.sample_id,
                "tests_list": row.tests_list
            })
            
            if len(batch) >= batch_size:
                if not dry_run:
                    _update_batch(conn, batch)
                reporter.stats["samples_updated"] += len(batch)
                batch = []
                LOGGER.info(f"Updated {reporter.stats['samples_updated']} samples...")

        # Last batch
        if batch:
            if not dry_run:
                _update_batch(conn, batch)
            reporter.stats["samples_updated"] += len(batch)
            LOGGER.info(f"Updated {reporter.stats['samples_updated']} samples.")

    reporter.save()
    LOGGER.info("Population finished.")
    print(json.dumps(reporter.stats, indent=2))

def _update_batch(conn, batch):
    sql = text("""
        UPDATE glims_samples 
        SET requested_testing = :tests_list
        WHERE sample_id = :sample_id
    """)
    conn.execute(sql, batch)
    conn.commit()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", default=False)
    parser.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args()
    
    try:
        populate(dry_run=args.dry_run, batch_size=args.batch_size)
    except Exception as e:
        LOGGER.exception(f"Population failed: {e}")
        exit(1)
