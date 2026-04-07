import os, re, csv, PyPDF2
from datetime import datetime

# --- CONFIGURATION ---
HEADERS = ['Filename', 'Meeting Date', 'ArcGIS_Date', 'Meeting Type', 'Location', 'Start Time', 'End Time', 'Action Taken', 'Staff Code', 'Status']

ESTERO_ROADS = [
    'Corkscrew Road', 'Three Oaks Parkway', 'US 41', 'Williams Road', 
    'Estero Parkway', 'Ben Hill Griffin Parkway', 'Via Coconut Point', 
    'Coconut Road', 'Broadway Avenue', 'River Ranch Road', 'Sandy Lane',
    'Cypress Bend', 'Estero River', 'Bamboo Island', 'River Oaks Preserve'
]

def total_grooming(text):
    """The Ultimate Word Stitcher: Fixes spaces in the middle of words."""
    if not text: return ""
    
    # 1. Fix 'A p p r o v e d' -> 'Approved' (Single letters separated by spaces)
    text = re.sub(r'(\b\w)\s(?=\w\b)', r'\1', text)
    
    # 2. Stitch common broken words seen in your files
    stitch_map = {
        r'\bminut\s+es\b': 'minutes',
        r'\bAdopt\s+ed\b': 'Adopted',
        r'\ba\s+ward\b': 'award',
        r'\bper\s+form\b': 'perform',
        r'\bApprove\s+d\b': 'Approved',
        r'\bAccept\s+ed\b': 'Accepted',
        r'\bt\s+he\b': 'the',
        r'\bEster\s+o\b': 'Estero',
        r'\bC\s+ouncil\b': 'Council',
        r'\bpropos\s+ed\b': 'proposed',
        r'\bapplican\s+t\b': 'applicant'
    }
    for pattern, replacement in stitch_map.items():
        text = re.sub(pattern, replacement, text, flags=re.I)
    
    # 3. Fix spaces inside times like '9 : 3 0' -> '9:30'
    text = re.sub(r'(\d)\s*:\s*(\d)', r'\1:\2', text)
    
    # 4. Collapse all remaining multiple spaces into one
    return re.sub(r'\s+', ' ', text).strip()

def extract_project_location(action_text):
    if not action_text or "No action found" in action_text:
        return "9401 Corkscrew Palms Circle, Estero, FL 33928"
    for road in ESTERO_ROADS:
        match = re.search(fr'(\d+)\s+{re.escape(road)}', action_text, re.I)
        if match: return f"{match.group(1)} {road}, Estero, FL"
    for i, road_a in enumerate(ESTERO_ROADS):
        for road_b in ESTERO_ROADS[i+1:]:
            if road_a.lower() in action_text.lower() and road_b.lower() in action_text.lower():
                return f"{road_a} and {road_b}, Estero, FL"
    for road in ESTERO_ROADS:
        if road.lower() in action_text.lower(): return f"{road}, Estero, FL"
    return "9401 Corkscrew Palms Circle, Estero, FL 33928"

def process_pdf(file_path):
    fn = os.path.basename(file_path)
    data = {'Filename': fn, 'Meeting Type': 'Village Council', 'Start Time': '9:30 am', 'Staff Code': 'N/A', 'Status': 'Accepted'}
    try:
        with open(file_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            pages = [page.extract_text() or "" for page in reader.pages]
            full_text = total_grooming(" ".join(pages))
            
            # Date and ArcGIS Date
            d_match = re.search(r'(?:The\s+)?([A-Z][a-z]+)\s+(\d{1,2}),\s+(\d{4})', full_text, re.I)
            if d_match:
                data['Meeting Date'] = f"{d_match.group(1)} {d_match.group(2)}, {d_match.group(3)}"
                data['ArcGIS_Date'] = datetime.strptime(data['Meeting Date'], '%B %d, %Y').strftime('%Y-%m-%d')
            
            # Cancellations vs Regular
            if "cancelled" in full_text.lower():
                data.update({'Status': 'Cancelled', 'End Time': 'N/A', 'Action Taken': 'Meeting Cancelled'})
            else:
                end_match = re.search(r'(?:Adjourned|Adjournment|Time Adjourned)(?:\s+at)?[:\s]+(\d{1,2}[:\.]\d{2}\s*[ap]m)', full_text, re.I)
                data['End Time'] = end_match.group(1).lower() if end_match else "Unknown"
                segments = re.findall(r'Action:\s*(.*?)(?=\s*(?:Motion|Vote:|Staff|Council|Public|Adjourned:|$))', full_text, re.I)
                data['Action Taken'] = total_grooming(" | ".join([s.strip() for s in segments if len(s.strip()) > 10]))[:700]
                
                # SENSITIVE Staff Code Sniffer
                staff = re.search(r'\(?([a-z]{2}/[a-z]{2})\)?', " ".join(pages), re.I)
                if staff: data['Staff Code'] = staff.group(1).upper()
                elif "Sarkozy" in full_text: data['Staff Code'] = "SS"
                elif "Gibbs" in full_text: data['Staff Code'] = "MG"

            data['Location'] = extract_project_location(data.get('Action Taken', ''))
    except: pass
    return data

def main():
    pdfs = [f for f in os.listdir('.') if f.lower().endswith('.pdf')]
    results = [process_pdf(f) for f in pdfs]
    with open('estero_map_data.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=HEADERS, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(results)
    print("Purr-fect! Words stitched, locations found, and staff codes sniffed!")

if __name__ == "__main__": main()