"""
Analyze Qbench and GLIMS data to estimate migration impact.

This script connects to the local PostgreSQL database using credentials from the .env file
and generates a migration_analysis.json report.
"""

import os
import json
import logging
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

def analyze():
    """Main analysis routine."""
    engine = get_engine()
    analysis = {
        "analysis_date": datetime.now().isoformat(),
        "qbench_stats": {},
        "glims_stats": {},
        "migration_estimate": {},
        "conflicts": {}
    }
    
    LOGGER.info("Starting database analysis...")
    
    with engine.connect() as conn:
        # 1. Qbench Stats
        LOGGER.info("Analyzing Qbench tables...")
        analysis["qbench_stats"]["customers"] = conn.execute(text("SELECT COUNT(*) FROM customers")).scalar()
        analysis["qbench_stats"]["orders"] = conn.execute(text("SELECT COUNT(*) FROM orders")).scalar()
        
        q_samples = conn.execute(text("""
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE custom_formatted_id IS NOT NULL AND custom_formatted_id != '') as with_custom_id,
                COUNT(*) FILTER (WHERE custom_formatted_id IS NULL OR custom_formatted_id = '') as without_custom_id,
                MIN(date_created) as min_date,
                MAX(date_created) as max_date
            FROM samples
        """)).mappings().first()
        
        analysis["qbench_stats"]["samples"] = {
            "total": q_samples["total"],
            "with_custom_id": q_samples["with_custom_id"],
            "without_custom_id": q_samples["without_custom_id"],
            "date_range": [
                q_samples["min_date"].isoformat() if q_samples["min_date"] else None,
                q_samples["max_date"].isoformat() if q_samples["max_date"] else None
            ]
        }
        
        # 2. GLIMS Stats
        LOGGER.info("Analyzing GLIMS tables...")
        analysis["glims_stats"]["dispensaries"] = conn.execute(text("SELECT COUNT(*) FROM glims_dispensaries")).scalar()
        
        g_samples = conn.execute(text("""
            SELECT 
                COUNT(*) as total,
                MIN(date_received) as min_date,
                MAX(date_received) as max_date
            FROM glims_samples
        """)).mappings().first()
        
        analysis["glims_stats"]["samples"] = {
            "total": g_samples["total"],
            "date_range": [
                g_samples["min_date"].isoformat() if g_samples["min_date"] else None,
                g_samples["max_date"].isoformat() if g_samples["max_date"] else None
            ]
        }
        
        # 3. Conflict Detection
        LOGGER.info("Detecting ID conflicts...")
        # A conflict is when a Qbench sample's ID (custom or generated) already exists in glims_samples
        conflicts_query = conn.execute(text("""
            WITH q_ids AS (
                SELECT COALESCE(custom_formatted_id, 'QB-' || id) as q_id
                FROM samples
            )
            SELECT q_id 
            FROM q_ids 
            WHERE q_id IN (SELECT sample_id FROM glims_samples)
        """)).scalars().all()
        
        analysis["conflicts"] = {
            "count": len(conflicts_query),
            "sample_ids": conflicts_query[:100]  # First 100 as examples
        }
        
        # 4. Migration Estimate
        LOGGER.info("Calculating estimates...")
        # Customers that already exist in GLIMS (match by lower name)
        existing_customers = conn.execute(text("""
            SELECT COUNT(*) 
            FROM customers c
            WHERE EXISTS (
                SELECT 1 FROM glims_dispensaries gd 
                WHERE LOWER(gd.name) = LOWER(c.name)
            )
        """)).scalar()
        
        analysis["migration_estimate"] = {
            "customers_to_migrate": analysis["qbench_stats"]["customers"] - existing_customers,
            "customers_matched_existing": existing_customers,
            "samples_to_migrate": analysis["qbench_stats"]["samples"]["total"] - len(conflicts_query),
            "samples_conflicting_skip": len(conflicts_query),
            "samples_using_QB_prefix": analysis["qbench_stats"]["samples"]["without_custom_id"]
        }
        
    # --- Write Results ---
    output_path = "migration_analysis.json"
    with open(output_path, "w") as f:
        json.dump(analysis, f, indent=2)
    
    LOGGER.info(f"Analysis complete. Report saved to {output_path}")
    print(json.dumps(analysis, indent=2))

if __name__ == "__main__":
    try:
        analyze()
    except Exception as e:
        LOGGER.exception(f"Fatal error during analysis: {e}")
        exit(1)
