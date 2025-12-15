
import sys
import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Ensure src is in path
sys.path.append(os.path.join(os.getcwd(), "src"))

from glims.sync import load_env

def verify():
    load_env()
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        # construct from components if needed, similar to sync.py
        user = os.getenv("POSTGRES_USER", "postgres")
        password = os.getenv("POSTGRES_PASSWORD", "password")
        host = os.getenv("POSTGRES_HOST", "localhost")
        port = os.getenv("POSTGRES_PORT", "5432")
        db = os.getenv("POSTGRES_DB", "mcrlabs_dashboard")
        db_url = f"postgresql://{user}:{password}@{host}:{port}/{db}"

    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    session = Session()

    print("Checking for sample S25-00878 in priority list logic...")

    # We want to see if HO is included in the 'tests' list for this sample.
    # The logic in glims_priority.py queries ASSAY_START_MAP.
    # Let's perform a direct query similar to what the API does.

    from downloader_qbench_data.api.routers.glims_priority import ASSAY_START_MAP

    print(f"ASSAY_START_MAP keys: {list(ASSAY_START_MAP.keys())}")
    if "HO" not in ASSAY_START_MAP:
        print("FAIL: HO is not in ASSAY_START_MAP!")
        return

    # Check tests for S25-00878 specifically
    sample_id = "S25-00878"
    
    # 1. Check if sample exists in glims_ho_results
    ho_rows = session.execute(text("SELECT * FROM glims_ho_results WHERE sample_id = :sid"), {"sid": sample_id}).fetchall()
    print(f"\nRows in glims_ho_results for {sample_id}: {len(ho_rows)}")
    for row in ho_rows:
        print(f"  HO Row: {row._mapping}")

    # 2. Simulate the union query for this sample
    union_parts = []
    for label, (table, start_col) in ASSAY_START_MAP.items():
        union_parts.append(
            f"SELECT '{label}' AS label, sample_id, {start_col}::date AS start_date, analytes, status FROM {table} WHERE sample_id = :sid"
        )
    
    full_sql = " UNION ALL ".join(union_parts)
    print("\nExecuting Union Query for tests...")
    tests = session.execute(text(full_sql), {"sid": sample_id}).fetchall()
    
    print(f"Tests found for {sample_id}:")
    ho_found = False
    for t in tests:
        print(f" - Label: {t.label}, Status: {t.status}, Analytes present: {bool(t.analytes)}")
        if t.label == "HO":
            ho_found = True

    if ho_found:
        print("\nSUCCESS: HO test is present for the sample.")
    else:
        print("\nFAILURE: HO test is NOT present for the sample.")

if __name__ == "__main__":
    verify()
