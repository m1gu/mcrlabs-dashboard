import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

def check_dates():
    h = os.getenv('LOCAL_POSTGRES_HOST')
    p = os.getenv('LOCAL_POSTGRES_PORT')
    d = os.getenv('LOCAL_POSTGRES_DB')
    u = os.getenv('LOCAL_POSTGRES_USER')
    pw = os.getenv('LOCAL_POSTGRES_PASSWORD')
    
    engine = create_engine(f"postgresql+psycopg2://{u}:{pw}@{h}:{p}/{d}")
    
    with engine.connect() as conn:
        print("\n--- Qbench Sample IDs (S22, S23, S24) ---")
        q_qbench = text("""
            SELECT MIN(date_received), MAX(date_received), COUNT(*) 
            FROM glims_samples 
            WHERE sample_id LIKE 'S22-%' OR sample_id LIKE 'S23-%' OR sample_id LIKE 'S24-%'
        """)
        res = conn.execute(q_qbench).fetchone()
        print(f"Range: {res[0]} to {res[1]}")
        print(f"Count: {res[2]}")
        
        print("\n--- S25 Sample IDs ---")
        q_s25 = text("""
            SELECT MIN(date_received), MAX(date_received), COUNT(*) 
            FROM glims_samples 
            WHERE sample_id LIKE 'S25-%'
        """)
        res = conn.execute(q_s25).fetchone()
        print(f"Range: {res[0]} to {res[1]}")
        print(f"Count: {res[2]}")

        print("\n--- Recent Samples (by ID prefix) ---")
        q_prefixes = text("""
            SELECT LEFT(sample_id, 3) as prefix, MIN(date_received), MAX(date_received), COUNT(*)
            FROM glims_samples
            GROUP BY prefix
            ORDER BY MIN(date_received) ASC
        """)
        res = conn.execute(q_prefixes).fetchall()
        for r in res:
            print(f"Prefix {r[0]}: {r[1]} to {r[2]} (Count: {r[3]})")

if __name__ == "__main__":
    check_dates()
