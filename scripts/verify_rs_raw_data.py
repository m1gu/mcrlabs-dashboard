import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import pandas as pd

def verify():
    load_dotenv()
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db = os.environ["POSTGRES_DB"]
    user = os.environ["POSTGRES_USER"]
    password = os.environ["POSTGRES_PASSWORD"]
    url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"
    engine = create_engine(url)

    sql = """
    SELECT sample_id, sample_id_clean, client, start_date, acetone, butane 
    FROM glims_rs_results_raw 
    ORDER BY start_date DESC NULLS LAST
    LIMIT 10;
    """
    
    with engine.connect() as conn:
        df = pd.read_sql(text(sql), conn)
        print("--- RESULTADOS SINCRONIZADOS (TOP 10) ---")
        print(df.to_string(index=False))
        
        count = conn.execute(text("SELECT COUNT(*) FROM glims_rs_results_raw")).scalar()
        print(f"\nTotal de filas en la tabla: {count}")

if __name__ == "__main__":
    verify()
