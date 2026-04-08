import pandas as pd
import re

GITHUB_USER = "krocks9903"
GITHUB_REPO = "EagleGIS"
BRANCH_NAME = "script"
BASE_URL = f"https://github.com/{GITHUB_USER}/{GITHUB_REPO}/blob/{BRANCH_NAME}/pdfs/"

def professional_grooming(text):
    if not isinstance(text, str) or text == "Meeting Cancelled":
        return text
    text = re.sub(r'(\b\w)\s(?=\w\b)', r'\1', text)
    stitch_map = {
        r'Appr\s+oved': 'Approved', r'Approve\s+d': 'Approved',
        r'Adopt\s+ed': 'Adopted', r'Cons\s+ent': 'Consent',
        r'V\s+ote': 'Vote', r'minut\s+es': 'minutes',
        r't\s+erminat\s+ion': 'termination', r'pr\s+ojects': 'projects'
    }
    for pattern, replacement in stitch_map.items():
        text = re.sub(pattern, replacement, text, flags=re.I)
    text = re.sub(r'Vote\s*:\s*\(.*?\)\s*Aye\s*:', '', text, flags=re.I)
    text = re.sub(r'Vote\s*:\s*Aye\s*:', '', text, flags=re.I)
    return re.sub(r'\s+', ' ', text).strip()

def main():
    try:
        df = pd.read_csv('estero_map_data.csv')
        df['Action Taken'] = df['Action Taken'].apply(professional_grooming)
        df['Document_Link'] = df['Filename'].apply(lambda x: f"{BASE_URL}{str(x).replace(' ', '%20')}")
        df.to_csv('estero_map_data_polished.csv', index=False)
        print("Success: Dataset sanitized.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
