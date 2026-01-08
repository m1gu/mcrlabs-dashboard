import os
import sys
from datetime import date
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Add src to path
sys.path.append(os.path.join(os.getcwd(), "src"))

def check():
    load_dotenv()
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db = os.environ.get("POSTGRES_DB")
    user = os.environ.get("POSTGRES_USER")
    password = os.environ.get("POSTGRES_PASSWORD")

    if not all([db, user, password]):
        print("Missing DB env vars")
        return

    url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"
    engine = create_engine(url)
    
    try:
        with engine.connect() as conn:
            res = conn.execute(text("SELECT * FROM glims_samples LIMIT 1"))
            print("Columns in glims_samples:")
            print(res.keys())
            
            # Test the query logic
            start = date(2026, 1, 2)
            end = date(2026, 1, 8)
            sample_type = "Adult Use"
            params = {"start": start, "end": end, "sample_type": sample_type}
            
            samples_sql = f"""
                SELECT date_received AS d, adult_use_medical, COUNT(*) AS c
                FROM glims_samples s
                WHERE date_received BETWEEN :start AND :end AND adult_use_medical = :sample_type
                GROUP BY date_received, adult_use_medical
            """
            print("\nTesting query...")
            res = conn.execute(text(samples_sql), params)
            print("Query executed successfully")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check()
