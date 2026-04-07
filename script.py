import os
import re
import csv
import PyPDF2
from datetime import datetime

# --- CONFIGURATION ---
# These match your meeting_log headers exactly
HEADERS = ['Filename', 'Meeting Date', 'Meeting Type', 'Location', 'Start Time', 'End Time', 'Action Taken', 'Staff Code', 'Status']

def ultra_clean(text):
    """Grooms the text to remove 'stuttering' (A p p r o v e d) and extra fluff."""
    if not text: return ""
    # 1. Fix single letters separated by spaces (e.g., 'V i l l a g e')
    text = re.sub(r'(\b\w)\s(?=\w\b)', r'\1', text) 
    # 2. Fix spaces inside times (e.g., '9 : 3 0')
    text = re.sub(r'(\d)\s*:\s*(\d)', r'\1:\2', text)
    # 3. CRITICAL: Collapse multiple spaces/tabs/newlines into ONE single space
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def extract_date(fn, text):
    """Sniffs out the date from text or filename."""
    # Try text first (The [Month] [Day], [Year]...)
    match = re.search(r'(?:The\s+)?([A-Z][a-z]+)\s+(\d{1,2}),\s+(\d{4})', text, re.I)
    if match:
        return f"{match.group(1)} {match.group(2)}, {match.group(3)}"
    # Fallback to filename (YYYY-MM-DD or MMDDYY)
    m1 = re.search(r'(\d{4})-(\d{2})-(\d{2})', fn)
    if m1:
        try: return datetime.strptime(m1.group(0), '%Y-%m-%d').strftime('%B %d, %Y')
        except: pass
    m2 = re.search(r'(\d{2})(\d{2})(\d{2,4})', fn)
    if m2:
        m, d, y = m2.groups()
        if len(y) == 2: y = '20' + y
        try: return datetime(int(y), int(m), int(d)).strftime('%B %d, %Y')
        except: pass
    return "Unknown"

def sniff_end_time(text):
    """A better hunter for adjournment times (catches 'at', 'pm', etc.)"""
    patterns = [
        # Matches: "Adjourned at 10:30 am" or "Adjournment: 11:00 p.m."
        r'(?:Adjourned|Adjournment|Time Adjourned|Ended)(?:\s+at)?[:\s]+(\d{1,2}[:\.]\d{2}\s*[ap]\.?m\.?)',
        # Matches: "10:30 am Adjourned"
        r'(\d{1,2}[:\.]\d{2}\s*[ap]\.?m\.?)\s+(?:Adjourned|Adjournment)',
        # Matches: "Meeting adjourned at 11:30 am"
        r'Meeting\s+adjourned\s+at\s+(\d{1,2}[:\.]\d{2}\s*[ap]\.?m\.?)'
    ]
    for p in patterns:
        match = re.search(p, text, re.I)
        if match:
            # Clean up: remove dots from 'a.m.' and return lowercase
            return re.sub(r'\s+', ' ', match.group(1).replace('.', '').lower().strip())
    return "Unknown"

def process_pdf(file_path):
    fn = os.path.basename(file_path)
    data = {
        'Filename': fn, 'Meeting Date': 'Unknown', 'Meeting Type': 'Village Council',
        'Location': 'Village of Estero Council Chambers', 'Start Time': '9:30 am',
        'End Time': 'Unknown', 'Action Taken': 'No action found', 'Staff Code': 'N/A', 'Status': 'Accepted'
    }
    
    try:
        with open(file_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            pages = [page.extract_text() or "" for page in reader.pages]
            full_text = "".join(pages)
            last_page = pages[-1] if pages else ""
            
            clean_full = ultra_clean(full_text)
            clean_last = ultra_clean(last_page)

            # 1. Detect Cancellations
            if "cancelled" in clean_full.lower() or "cancel" in fn.lower():
                data['Status'] = 'Cancelled'
                data['Action Taken'] = 'Meeting Cancelled'
                data['End Time'] = 'N/A'
                data['Meeting Date'] = extract_date(fn, clean_full)
                return data

            # 2. Regular Meeting Extraction
            data['Meeting Date'] = extract_date(fn, clean_full)
            
            # Start Time
            start = re.search(r'(?:Started|Order)(?:\s+at)?[:\s]+(\d{1,2}[:\.]\d{2}\s*[ap]\.?m\.?)', clean_full, re.I)
            if start: data['Start Time'] = start.group(1).replace('.', '').lower()

            # End Time - Search the last page first! 
            data['End Time'] = sniff_end_time(clean_last)
            if data['End Time'] == "Unknown":
                data['End Time'] = sniff_end_time(clean_full)

            # Actions Taken
            segments = re.findall(r'Action:\s*(.*?)(?=\s*(?:Motion|Vote:|Staff|Council|Public|Adjourned:|$))', clean_full, re.I)
            acts = [s.strip() for s in segments if len(s.strip()) > 10 and 'agenda' not in s.lower()]
            if acts: data['Action Taken'] = " | ".join(acts[:6])
            
            # Staff Code
            staff = re.search(r'\((\w{2}/\w{2})\)', full_text)
            if staff: data['Staff Code'] = staff.group(1)

    except Exception as e:
        print(f"Meow! Problem with {fn}: {e}")
    return data

def main():
    pdfs = [f for f in os.listdir('.') if f.lower().endswith('.pdf')]
    if not pdfs:
        print("I don't see any PDFs! Put me in the same folder as your papers.")
        return

    print(f"Meow! Sniffing {len(pdfs)} files...")
    results = [process_pdf(f) for f in pdfs]
    
    with open('meeting_log_final.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows(results)
    print("Purr-fect! 'meeting_log_final.csv' is ready for you.")

if __name__ == "__main__":
    main()