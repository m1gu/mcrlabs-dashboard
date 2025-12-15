
import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

def verify_hm():
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
    
    with engine.connect() as conn:
        print(f"Checking HM results for S25-01012...")
        # Check values
        sql = """
            SELECT sample_id, status, as_val, cd_val, hg_val, pb_val 
            FROM glims_hm_results 
            WHERE sample_id = 'S25-01012'
        """
        row = conn.execute(text(sql)).first()
        if row:
            print(f"Sample: {row.sample_id}")
            print(f"Status: {row.status}")
            print(f"Values -> As: {row.as_val}, Cd: {row.cd_val}, Hg: {row.hg_val}, Pb: {row.pb_val}")
            
            # Validation
            if row.status == 'Completed':
                print("SUCCESS: HM status is Completed.")
            else:
                print(f"WARNING: Status is {row.status}")
                
            # Check if text was saved
            # Expecting ND or BQL or similar text
            # Per user screenshot: As=ND, Cd=ND, Hg=ND, Pb=BQL
            expected_vals = {'as_val': 'ND', 'cd_val': 'ND', 'hg_val': 'ND', 'pb_val': 'BQL'}
            
            match = True
            for col, val in expected_vals.items():
                actual = getattr(row, col)
                if actual != val:
                    print(f"MISMATCH {col}: Expected {val}, got {actual}")
                    match = False
            
            if match:
                print("SUCCESS: All text values match expected (ND/BQL).")
            
        else:
            print("FAILURE: HM Result NOT FOUND")

if __name__ == "__main__":
    verify_hm()
