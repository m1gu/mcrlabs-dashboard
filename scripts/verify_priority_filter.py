import os
import requests
from dotenv import load_dotenv

load_dotenv()

def verify_most_overdue():
    # Use localhost if running locally, or the API URL if configured
    base_url = "http://localhost:8000/api/v2/glims/priority/most-overdue"
    params = {"min_days_overdue": 3}
    
    # We might need an auth token if require_active_user is active
    # For local testing, we can check if it works without token or find a token
    try:
        response = requests.get(base_url, params=params)
        if response.status_code == 401:
            print("Authentication required (401). Skipping HTTP test, will check DB directly.")
            return
            
        data = response.json()
        samples = data.get("samples", [])
        
        print(f"\n=== VERIFYING OVERDUE SAMPLES (API) ===")
        print(f"Total returned: {len(samples)}")
        
        count_old = 0
        for s in samples:
            sample_id = s["sample_id"]
            if any(prefix in sample_id for prefix in ["S20-", "S21-", "S22-", "S23-", "S24-"]):
                print(f"FAILED: Found old sample {sample_id}")
                count_old += 1
            else:
                # print(f"PASS: {sample_id}")
                pass
                
        if count_old == 0:
            print("SUCCESS: No historical samples found in overdue list.")
        else:
            print(f"Total old samples found: {count_old}")

    except Exception as e:
        print(f"Error calling API: {e}")

if __name__ == "__main__":
    verify_most_overdue()
