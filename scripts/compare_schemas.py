import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

def compare_schemas(table):
    def get_info(e):
        with e.connect() as conn:
            q = text(f"SELECT column_name, data_type FROM information_schema.columns WHERE table_name = '{table}' ORDER BY column_name")
            return {r[0]: r[1] for r in conn.execute(q)}

    local_e = create_engine(f"postgresql+psycopg2://{os.getenv('LOCAL_POSTGRES_USER')}:{os.getenv('LOCAL_POSTGRES_PASSWORD')}@{os.getenv('LOCAL_POSTGRES_HOST')}:{os.getenv('LOCAL_POSTGRES_PORT')}/{os.getenv('LOCAL_POSTGRES_DB')}")
    azure_e = create_engine(f"postgresql+psycopg2://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}@{os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}")

    try:
        local_cols = get_info(local_e)
        azure_cols = get_info(azure_e)
        
        print(f"--- Columnas en Local ({table}) ---")
        for c, t in local_cols.items():
            at = azure_cols.get(c, "MISSING")
            if t != at:
                print(f"DIFF!! {c}: Local={t}, Azure={at}")
            else:
                # print(f"  {c}: {t}")
                pass
        
        # Check if Azure has extra columns
        for c in azure_cols:
            if c not in local_cols:
                print(f"EXTRA in Azure: {c} ({azure_cols[c]})")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    compare_samples = "glims_samples"
    compare_schemas(compare_samples)
