
import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

def fix_sample():
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
    
    with engine.begin() as conn:
        sid = 'S25-00946'
        print(f"Fixing Sample: {sid} (Resetting MB to Batched)")
        
        # Reset MB
        result = conn.execute(text("UPDATE glims_mb_results SET status = 'Batched' WHERE sample_id = :sid AND status = 'Completed'"), {"sid": sid})
        print(f"Rows updated: {result.rowcount}")

if __name__ == "__main__":
    fix_sample()
