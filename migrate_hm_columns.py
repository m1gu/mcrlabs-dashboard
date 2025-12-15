
import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

def migrate_db():
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
    
    engine = create_engine(db_url)
    
    commands = [
        "ALTER TABLE glims_hm_results ALTER COLUMN as_val TYPE TEXT",
        "ALTER TABLE glims_hm_results ALTER COLUMN cd_val TYPE TEXT",
        "ALTER TABLE glims_hm_results ALTER COLUMN hg_val TYPE TEXT",
        "ALTER TABLE glims_hm_results ALTER COLUMN pb_val TYPE TEXT",
    ]
    
    with engine.begin() as conn:
        for cmd in commands:
            print(f"Executing: {cmd}")
            conn.execute(text(cmd))
    
    print("Migration completed successfully.")

if __name__ == "__main__":
    migrate_db()
