
import os
import json
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

def analyze_sample():
    load_dotenv(override=True)
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL not found, constructing...")
        user = os.getenv("POSTGRES_USER", "postgres")
        password = os.getenv("POSTGRES_PASSWORD", "password")
        host = os.getenv("POSTGRES_HOST", "localhost")
        port = os.getenv("POSTGRES_PORT", "5432")
        db = os.getenv("POSTGRES_DB", "mcrlabs_dashboard")
        db_url = f"postgresql://{user}:{password}@{host}:{port}/{db}"
    
    print(f"Connecting to DB...")
    engine = create_engine(db_url)
    
    with engine.connect() as conn:
        sid = 'S25-00946'
        print(f"Analyzing Sample: {sid}")
        
        # 1. Check Samples table
        row = conn.execute(text("SELECT sample_id, requested_testing FROM glims_samples WHERE sample_id = :sid"), {"sid": sid}).first()
        if row:
            print(f"Found in glims_samples. Requested: {row.requested_testing}")
        else:
            print(f"NOT FOUND in glims_samples")

        # 2. Check MB Results
        print("\n--- glims_mb_results ---")
        row = conn.execute(text("SELECT sample_id, status, analytes, tempo_prep_date FROM glims_mb_results WHERE sample_id = :sid"), {"sid": sid}).first()
        if row:
            print(f"Status: {row.status}")
            print(f"Analytes: {row.analytes}")
            if row.analytes:
                # Check if it looks empty
                 try:
                     # It's likely a dict or None since we select raw
                     # wait, sqlalchemy might return dict for jsonb column
                     data = row.analytes
                     print(f"Analytes Type: {type(data)}")
                     has_real_val = False
                     if isinstance(data, dict):
                         for k,v in data.items():
                             if v and str(v).strip().lower() not in ("nan", "none", "", "null"):
                                 has_real_val = True
                                 print(f"  Found Value: {k}={v}")
                     if not has_real_val:
                         print("  -> Analytes JSON exists but appears EMPTY of real values")
                 except Exception as e:
                     print(f"Error parsing analytes: {e}")
        else:
            print("MB Result NOT FOUND")

if __name__ == "__main__":
    analyze_sample()
