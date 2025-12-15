
import re

def normalize_sample_id(raw: str) -> str:
    if not raw:
        return ""
    sid = raw.strip()
    # Current implementation
    sid = re.sub(r"-(HO\d+(?:-\d+)?)$", "", sid, flags=re.IGNORECASE)
    sid = re.sub(r"-N$", "", sid, flags=re.IGNORECASE)
    return sid

def proposed_normalize(raw: str) -> str:
    if not raw:
        return ""
    sid = raw.strip()
    
    # 1. Remove HO variants
    sid = re.sub(r"-(HO\d+(?:-\d+)?)$", "", sid, flags=re.IGNORECASE)
    # 2. Remove -N
    sid = re.sub(r"-N$", "", sid, flags=re.IGNORECASE)
    
    # 3. PROPOSED: Remove -1, -2, etc. (re-runs/aliquots)
    # DANGER: S25-00955 matches -\d+$
    # Strategy: Only remove if resulting ID still matches S\d+-\d+ or if original had 2 dashes?
    
    # Try: Remove -\d+$ IF the string has at least 2 dashes?
    # Ex: S25-00955-1 (2 dashes) -> remove -1 -> S25-00955 (1 dash) OK
    # Ex: S25-00955 (1 dash) -> remove -00955 -> S25 (0 dashes) - Maybe we accept this rule?
    
    if filter_match := re.search(r"(-\d+)$", sid):
        # Check if we have > 1 dash
        if sid.count('-') >= 2:
            sid = re.sub(r"-\d+$", "", sid)
            
    return sid

cases = [
    "S25-00955",
    "S25-00955-1",
    "S25-00955-HO1",
    "S25-00955-HO2-1",
    "S25-00955-N",
    "S25-00955-12", # Maybe?
    "S25-00955-1-1", # Two layers?
]

print(f"{'Input':<20} | {'Current':<20} | {'Proposed':<20}")
print("-" * 65)
for c in cases:
    curr = normalize_sample_id(c)
    prop = proposed_normalize(c)
    print(f"{c:<20} | {curr:<20} | {prop:<20}")
