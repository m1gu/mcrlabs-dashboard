import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

def show_schema(table):
    host = os.getenv("LOCAL_POSTGRES_HOST")
    port = os.getenv("LOCAL_POSTGRES_PORT")
    db = os.getenv("LOCAL_POSTGRES_DB")
    user = os.getenv("LOCAL_POSTGRES_USER")
    pw = os.getenv("LOCAL_POSTGRES_PASSWORD")
    
    engine = create_engine(f"postgresql+psycopg2://{user}:{pw}@{host}:{port}/{db}")
    
    with engine.connect() as conn:
        print(f"\n=== {table.upper()} ===")
        q = text(f"SELECT column_name, data_type FROM information_schema.columns WHERE table_name = '{table}' ORDER BY ordinal_position")
        for r in conn.execute(q):
            print(f"  {r[0]}: {r[1]}")
            
        # Check PK
        q_pk = text("""
            SELECT a.attname
            FROM   pg_index i
            JOIN   pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
            WHERE  i.indrelid = :table::regclass
            AND    i.indisprimary
        """)
        pk = conn.execute(q_pk, {"table": table}).fetchall()
        print(f"PK: {[p[0] for p in pk]}")

if __name__ == "__main__":
    show_schema("glims_dispensaries")
