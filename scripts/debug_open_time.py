import os
import json
from sqlalchemy import create_engine, text
from datetime import datetime
from dotenv import load_dotenv

def main():
    load_dotenv()
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db = os.environ["POSTGRES_DB"]
    user = os.environ["POSTGRES_USER"]
    password = os.environ["POSTGRES_PASSWORD"]
    url = f"postgresql://{user}:{password}@{host}:{port}/{db}"
    engine = create_engine(url)

    sample_ids = ['S25-01035', 'S25-01033', 'S25-01034', 'S25-01036', 'S25-01037']
    now_utc = datetime.utcnow()

    sql = """
        SELECT 
            sample_id, 
            date_received, 
            date_received::timestamp as casted_received,
            :now as python_now,
            CURRENT_TIMESTAMP as db_now,
            EXTRACT(EPOCH FROM (:now - date_received::timestamp))/3600.0 AS open_hours
        FROM glims_samples 
        WHERE sample_id = ANY(:ids)
    """
    
    with engine.connect() as conn:
        res = conn.execute(text(sql), {"ids": sample_ids, "now": now_utc})
        for row in res:
            print(f"Sample: {row.sample_id}")
            print(f"  Received: {row.date_received} (Type: {type(row.date_received)})")
            print(f"  Casted:   {row.casted_received}")
            print(f"  PyNow:    {row.python_now}")
            print(f"  DbNow:    {row.db_now}")
            print(f"  OpenHrs:  {row.open_hours}")
            print("-" * 20)

if __name__ == "__main__":
    main()
