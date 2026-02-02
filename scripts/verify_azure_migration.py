import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

def verify():
    host = os.getenv("POSTGRES_HOST")
    port = os.getenv("POSTGRES_PORT")
    db = os.getenv("POSTGRES_DB")
    user = os.getenv("POSTGRES_USER")
    pw = os.getenv("POSTGRES_PASSWORD")
    
    engine = create_engine(f"postgresql+psycopg2://{user}:{pw}@{host}:{port}/{db}")
    
    with engine.connect() as conn:
        print("\n=== VERIFICACIÓN EN AZURE ===")
        # Cantidad de samples hasta 2025
        count = conn.execute(text("SELECT COUNT(*) FROM glims_samples WHERE date_received <= '2025-12-31'")).scalar()
        print(f"Samples (<= 2025-12-31): {count}")
        
        # Verificar un par de tests para ver si el campo analytes está poblado
        cn_count = conn.execute(text("SELECT COUNT(*) FROM glims_cn_results WHERE sample_id NOT LIKE 'S26-%'")).scalar()
        print(f"Resultados CN (Not S26): {cn_count}")

if __name__ == "__main__":
    verify()
