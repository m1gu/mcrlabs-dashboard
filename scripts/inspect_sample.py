import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

def inspect_sample(sample_id):
    host = os.getenv("POSTGRES_HOST")
    port = os.getenv("POSTGRES_PORT")
    db = os.getenv("POSTGRES_DB")
    user = os.getenv("POSTGRES_USER")
    pw = os.getenv("POSTGRES_PASSWORD")
    
    engine = create_engine(f"postgresql+psycopg2://{user}:{pw}@{host}:{port}/{db}")
    
    with engine.connect() as conn:
        print(f"\n=== INSPECTING SAMPLE {sample_id} ===")
        q = text(f"SELECT sample_id, status, date_received, report_date FROM glims_samples WHERE sample_id = '{sample_id}'")
        row = conn.execute(q).fetchone()
        if row:
            print(dict(row._mapping))
        else:
            print("Not found.")

if __name__ == "__main__":
    inspect_sample("S20-10")
