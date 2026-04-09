import pandas as pd
import re

# --- CONFIGURATION ---
GITHUB_USER = "krocks9903"
GITHUB_REPO = "EagleGIS"
BRANCH_NAME = "script"
# The 'blob' URL ensures users view the PDF in the GitHub UI
BASE_URL = f"https://github.com/{GITHUB_USER}/{GITHUB_REPO}/blob/{BRANCH_NAME}/pdfs/"

def professional_grooming(text):
    """
    Sanitizes action text for professional presentation.
    """
    if not isinstance(text, str) or text == "Meeting Cancelled":
        return text
    
    # Stitch fragmented words
    text = re.sub(r'(\b\w)\s(?=\w\b)', r'\1', text)
    
    # Repair specific PDF artifacts
    stitch_map = {
        r'Appr\s+oved': 'Approved', r'Approve\s+d': 'Approved',
        r'Adopt\s+ed': 'Adopted', r'Cons\s+ent': 'Consent',
        r'V\s+ote': 'Vote', r'minut\s+es': 'minutes',
        r't\s+erminat\s+ion': 'termination', r'pr\s+ojects': 'projects'
    }
    for pattern, replacement in stitch_map.items():
        text = re.sub(pattern, replacement, text, flags=re.I)

    # Remove roll-call noise
    text = re.sub(r'Vote\s*:\s*\(.*?\)\s*Aye\s*:', '', text, flags=re.I)
    text = re.sub(r'Vote\s*:\s*Aye\s*:', '', text, flags=re.I)
    
    return re.sub(r'\s+', ' ', text).strip()

def main():
    print("[EagleGIS] Starting prioritized data refinement...")
    try:
        # Load the raw source
        df = pd.read_csv('estero_map_data.csv')
        
        # ACTION 1: Immediately replace placeholder links with GitHub links
        print("[Step 1] Overwriting placeholder links with GitHub blob URLs...")
        df['Document_Link'] = df['Filename'].apply(
            lambda x: f"{BASE_URL}{str(x).replace(' ', '%20')}"
        )
        
        # ACTION 2: Groom the 'Action Taken' summaries
        print("[Step 2] Cleaning meeting minutes text artifacts...")
        df['Action Taken'] = df['Action Taken'].apply(professional_grooming)
        
        # Save the polished output
        df.to_csv('estero_map_data_polished.csv', index=False)
        print("[Success] Dataset is now professional and linked to the 'script' branch.")
        
    except Exception as e:
        print(f"[Error] Pipeline failure: {e}")

if __name__ == "__main__":
    main()
# trigger
# trigger
