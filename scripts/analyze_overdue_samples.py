import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

def analyze_samples():
    host = os.getenv("POSTGRES_HOST")
    port = os.getenv("POSTGRES_PORT")
    db = os.getenv("POSTGRES_DB")
    user = os.getenv("POSTGRES_USER")
    pw = os.getenv("POSTGRES_PASSWORD")
    
    engine = create_engine(f"postgresql+psycopg2://{user}:{pw}@{host}:{port}/{db}")
    
    with engine.connect() as conn:
        print("\n=== SAMPLE PREFIXES AND STATUS ===")
        q = text("""
            SELECT status, LEFT(sample_id, 3) as prefix, COUNT(*) 
            FROM glims_samples 
            GROUP BY status, prefix 
            ORDER BY count DESC 
            LIMIT 30
        """)
        results = conn.execute(q).fetchall()
        for r in results:
            print(f"Status: {r[0]}, Prefix: {r[1]}, Count: {r[2]}")

if __name__ == "__main__":
    analyze_samples()
