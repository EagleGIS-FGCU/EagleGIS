"""
EagleGIS PDF processing pipeline.

Single source of truth for:
  - Extracting text from Village of Estero meeting-minute PDFs
  - Cleaning that text (PDF artifacts, mid-word breaks, broken capitals)
  - Parsing meeting metadata (dates, start/end times, status)
  - Parsing the structured "Action:" blocks that the frontend displays

Used by ``fixminutes.py``, ``sanitizeData.py``, and ``refine_final_csv.py``.

Primary extractor is ``pdfplumber`` (much better word-boundary handling than
PyPDF2); falls back to PyPDF2 when pdfplumber is unavailable so the script
still runs in stripped-down environments.
"""
from __future__ import annotations

import os
import re
from datetime import datetime
from typing import List, Optional, Tuple

# --- Backends -----------------------------------------------------------------

try:
    import pdfplumber  # type: ignore
    _HAS_PDFPLUMBER = True
except Exception:  # pragma: no cover
    _HAS_PDFPLUMBER = False

try:
    import PyPDF2  # type: ignore
    _HAS_PYPDF2 = True
except Exception:  # pragma: no cover
    _HAS_PYPDF2 = False


# --- Extraction ---------------------------------------------------------------

def extract_pages(pdf_path: str) -> List[str]:
    """Return per-page text. Prefers pdfplumber for cleaner word boundaries."""
    if _HAS_PDFPLUMBER:
        try:
            with pdfplumber.open(pdf_path) as pdf:
                return [(p.extract_text() or "") for p in pdf.pages]
        except Exception:
            pass
    if _HAS_PYPDF2:
        with open(pdf_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            return [(p.extract_text() or "") for p in reader.pages]
    raise RuntimeError("Neither pdfplumber nor PyPDF2 is available")


_MONTHS = ("January|February|March|April|May|June|July|August|September|"
           "October|November|December")


# --- Cleaning -----------------------------------------------------------------

# Continuations attached to a stray leading capital letter, e.g. "C ouncil".
# Only join when the second token starts with a known continuation so we never
# turn legitimate phrases like "A car" into "Acar".
_CAP_CONT = {
    "A": ["ction", "dopt", "dopted", "doption", "pprov", "pproved", "pproves",
          "pproval", "pproving", "gainst", "menda", "mendment", "uthoriz",
          "uthorized", "uthorize", "genda", "ttention", "ttest",
          "ttachment", "ttorney", "pril", "ugust", "pplied", "pplication",
          "pplicant", "ttempt", "ssessment", "ccept", "ccepted", "ye", "ye:",
          "ddendum", "wards", "warded", "warding", "ssign", "ssigned"],
    "V": ["ote", "oted", "oting", "illage", "ice", "alidat", "olunteer",
          "otes"],
    "M": ["otion", "ayor", "arch", "ay", "ember", "embers",
          "eeting", "eetings", "inute", "inutes", "anag", "anager",
          "aterials", "onth", "onths", "anhattan"],
    "P": ["assed", "asses", "assing", "lanning", "lan", "lans", "olicy",
          "roject", "rojects", "ublic", "aragraph", "arkway", "ier",
          "urchas", "urchase", "urchased", "rovide", "rovided",
          "rovides", "rovision", "ointed", "oint", "osition", "olice",
          "rivate", "roperty", "ackage"],
    "S": ["taff", "econd", "econded", "ervice", "ervices", "ystem",
          "tate", "treet", "chool", "ub", "eptember", "eries", "tudy",
          "tudent", "tudents", "ession", "tep", "top", "tarted", "tart",
          "unny", "even", "ig", "ite", "ites", "andy", "ix"],
    "C": ["ouncil", "ouncilmember", "onsent", "ommittee", "ommunity",
          "ity", "orks", "omprehen", "ompetition", "hange", "hapter",
          "hair", "hairperson", "hild", "orkscrew", "oast", "oastal",
          "orridor", "ode", "ouncilmembers", "ouncilman", "ouncilwoman",
          "ontract", "ompletion", "onstruction"],
    "B": ["oard", "roadway", "icycle", "ridge", "oth", "illable",
          "oat", "each", "ert", "ill", "ills"],
    "F": ["inal", "irst", "inanc", "inance", "lorida", "unding",
          "ebruary", "oundation", "ay", "ayhee"],
    "R": ["oll", "esolu", "esolution", "oad", "ailroad", "ail",
          "oads", "ange", "eceived", "eceive", "eceives", "ecord",
          "ecords", "eview", "eady", "ibble", "iver"],
    "T": ["he", "ime", "imes", "oday", "rust", "iger", "ree", "ake",
          "etra", "ammy"],
    "D": ["ecember", "irector", "eputy", "istrict", "istricts",
          "ate", "ates", "eveloper", "evelopment", "enied", "eny",
          "enial", "epot", "uran"],
    "I": ["nformation", "mprovement", "mprovements", "nclude",
          "ncluded", "nstall", "nstalled", "nstallation", "ntersection"],
    "O": ["rdinance", "rdinances", "rgan", "rganized", "pen", "wner",
          "utside", "ctober"],
    "N": ["ovember", "ay:", "ay", "one", "ovember"],
    "L": ["ee", "ot", "icens", "icense", "and", "ane", "opez"],
    "U": ["nan", "nanim", "nanimous", "pdate", "pdated", "tility"],
    "E": ["ster", "stero", "asement", "ngineer", "ngineering",
          "lect", "lection", "lections", "schenfelder"],
    "W": ["illia", "illiams", "ater", "ay", "eek", "orks", "ith",
          "ard", "iley"],
    "G": ["rowth", "arage", "ibbs", "reenville", "uaranteed"],
    "H": ["unt", "igh", "ome", "ighSpans"],
    "J": ["anuary", "uly", "une", "oint", "ohn", "ohns", "ohnson"],
    "K": ["evin"],
}

# Specific known-broken chunks (case-insensitive). Use these for fragments
# pdfplumber still leaves split. Add patterns here as they're spotted.
_EXPLICIT_FIXES: List[Tuple[str, str]] = [
    # Word-final consonant + suffix splits
    (r"\bApprove\s+d\b", "Approved"),
    (r"\bApprov\s+ed\b", "Approved"),
    (r"\bApprove\s+s\b", "Approves"),
    (r"\bAdopt\s+ed\b", "Adopted"),
    (r"\bAccept\s+ed\b", "Accepted"),
    (r"\bAccept\s+ing\b", "Accepting"),
    (r"\bPass\s+ed\b", "Passed"),
    (r"\bElect\s+ed\b", "Elected"),
    (r"\bAuthoriz\s+ed\b", "Authorized"),
    (r"\bAppoint\s+ed\b", "Appointed"),
    (r"\bDirect\s+ed\b", "Directed"),
    (r"\bRequest\s+ed\b", "Requested"),
    (r"\bAward\s+ed\b", "Awarded"),
    (r"\bDeni\s+ed\b", "Denied"),
    (r"\bConsent\s+ed\b", "Consented"),
    (r"\bContinu\s+ed\b", "Continued"),
    (r"\bAmend\s+ed\b", "Amended"),
    (r"\bSecond\s+ed\b", "Seconded"),

    # Mid-word splits seen in real data
    (r"\bbetwe\s+en\b", "between"),
    (r"\bAmendme\s+nt\b", "Amendment"),
    (r"\bAmen\s+dment\b", "Amendment"),
    (r"\bManageme\s+nt\b", "Management"),
    (r"\bapplica\s+nt\b", "applicant"),
    (r"\bapplican\s+t\b", "applicant"),
    (r"\bdeleg\s+ation\b", "delegation"),
    (r"\btermin\s+ation\b", "termination"),
    (r"\bcompris\s+e\b", "comprise"),
    (r"\bpurchas\s+e\b", "purchase"),
    (r"\bappropriat\s+e\b", "appropriate"),
    (r"\bins\s+tallation\b", "installation"),
    (r"\btha\s+t\b", "that"),
    (r"\bdesig\s+n\b", "design"),
    (r"\bdesi\s+gn\b", "design"),
    (r"\bminut\s+es\b", "minutes"),
    (r"\bResolu\s+tion\b", "Resolution"),
    (r"\bResol\s+ution\b", "Resolution"),
    (r"\bResolut\s+ion\b", "Resolution"),
    (r"\bOrdina\s+nce\b", "Ordinance"),
    (r"\bOrdinan\s+ce\b", "Ordinance"),
    (r"\bImprove\s+ments\b", "Improvements"),
    (r"\bImprovement\s+s\b", "Improvements"),
    (r"\bse\s+cond\b", "second"),
    (r"\bseco\s+nd\b", "second"),
    (r"\bC\s+are\b", "Care"),
    (r"\bPa\s+rkway\b", "Parkway"),
    (r"\bRivercre\s+ek\b", "Rivercreek"),
    (r"\bAve\s+nue\b", "Avenue"),
    (r"\bInte\s+rlocal\b", "Interlocal"),
    (r"\bInterloc\s+al\b", "Interlocal"),
    (r"\bAgenc\s+y\b", "Agency"),
    (r"\bScho\s+ol\b", "School"),
    (r"\bImpro\s+vement\b", "Improvement"),

    # Punctuation glued to words by extraction
    (r"\bAction\s+:", "Action:"),
    (r"\bMotion\s+:", "Motion:"),
    (r"\bVote\s+:", "Vote:"),
    (r"\bAye\s+:", "Aye:"),
    (r"\bNay\s+:", "Nay:"),
    (r"\bAbstentions\s+:", "Abstentions:"),
]


def _join_single_letter_chains(text: str) -> str:
    """Collapse 'A p p r o v e d' style chains into 'Approved'."""
    prev = None
    while prev != text:
        prev = text
        text = re.sub(r"(\b[A-Za-z])\s(?=[A-Za-z]\b)", r"\1", text)
    return text


def _join_capital_continuations(text: str) -> str:
    """Repair stray leading capitals: 'C ouncil' -> 'Council'."""
    for letter, conts in _CAP_CONT.items():
        # Longer continuations first so 'pprov' wins over 'pp' if added later.
        sorted_conts = sorted(set(conts), key=len, reverse=True)
        alt = "|".join(re.escape(c) for c in sorted_conts)
        pattern = rf"\b{letter}\s+(?={alt}\b)"
        text = re.sub(pattern, letter, text)
    return text


def clean_text(text: str) -> str:
    """Clean raw PDF-extracted text.

    Order matters:
      1. Strip the broken Unicode replacement char that some fonts emit
      2. Normalise whitespace so newlines mid-word stop fooling the joiners
      3. Join single-letter chains
      4. Re-attach stray leading capitals to their continuation
      5. Apply explicit fix-up patterns
      6. Fix times '9 : 30' and dashes '2024 - 06'
      7. Final whitespace collapse
    """
    if not text:
        return ""
    # Dash glyphs and the Unicode replacement char (the PDF font emits this for
    # curly quotes/apostrophes; turning it into a plain apostrophe preserves
    # words like "Village's" instead of mangling them to "Villages").
    text = text.replace("\u2013", "-").replace("\u2014", "-")
    text = text.replace("\u2018", "'").replace("\u2019", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = text.replace("\ufffd", "'")
    # Drop the boilerplate page-footer line that bleeds into action capture
    text = re.sub(
        rf"Village Council Minutes\s*[-�]?\s*({_MONTHS})\s+\d{{1,2}},\s+\d{{4}}"
        r"\s*Page\s+\d+\s+of\s+\d+",
        " ",
        text,
        flags=re.IGNORECASE,
    )
    # And the long disclaimer paragraph that appears on most first pages
    text = re.sub(
        r"Final Action Agenda/Minutes are supplemented by audio.*?"
        r"corresponding meeting date\.?",
        " ",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    text = re.sub(r"\s+", " ", text).strip()
    text = _join_single_letter_chains(text)
    text = _join_capital_continuations(text)
    for pat, rep in _EXPLICIT_FIXES:
        text = re.sub(pat, rep, text, flags=re.I)
    text = re.sub(r"(\d)\s*:\s*(\d)", r"\1:\2", text)
    text = re.sub(r"(\d)\s*-\s*(\d)", r"\1-\2", text)
    return re.sub(r"\s+", " ", text).strip()


# --- Action extraction --------------------------------------------------------

# Words that legitimately appear at the start of a *new* section in a transcript
# of a council meeting. We use them as terminators when capturing an Action:
# block. They must be matched at a word boundary AND followed by something that
# looks like a section marker (colon, line-leading position, etc.) so we don't
# truncate mid-sentence at e.g. "Staff" inside an action description.
_ACTION_TERMINATORS = (
    r"Vote\s*:|"
    r"Motion\s*:|"
    r"Motion\s+by\s*:|"
    r"Seconded\s+by\s*:|"
    r"Aye\s*:|"
    r"Nay\s*:|"
    r"Abstentions\s*:|"
    r"Adjourn(?:ed|ment)\b|"
    r"$"
)


def extract_actions(clean_full_text: str, max_items: int = 12,
                    max_total_chars: int = 1500) -> List[str]:
    """Pull every distinct ``Action:`` block out of a cleaned minutes string.

    Each block runs from "Action:" up to the next section terminator
    (Vote:, Motion:, Aye:, Adjournment, end-of-text). Blocks are
    de-duplicated, trimmed, and capped so the frontend cell stays readable.
    """
    if not clean_full_text:
        return []
    pattern = re.compile(
        rf"\bAction\s*:\s*(.*?)(?=\s+(?:{_ACTION_TERMINATORS}))",
        re.IGNORECASE | re.DOTALL,
    )
    seen, out, total = set(), [], 0
    for m in pattern.finditer(clean_full_text):
        a = re.sub(r"\s+", " ", m.group(1)).strip(" .,:;-")
        if len(a) < 8:
            continue
        # Drop residual roll-call noise that occasionally bleeds in
        a = re.sub(r"\(Roll\s+Call\)\s*", "", a, flags=re.I).strip()
        key = a.lower()[:120]
        if key in seen:
            continue
        seen.add(key)
        out.append(a)
        total += len(a)
        if len(out) >= max_items or total >= max_total_chars:
            break
    return out


def join_actions(actions: List[str], cap: int = 1500) -> str:
    """Render a list of action strings as the frontend's pipe-separated form."""
    joined = " | ".join(actions)
    return joined[:cap].rstrip(" |")


# --- Metadata helpers ---------------------------------------------------------

def _date_from_filename(fn: str) -> Optional[datetime]:
    base = os.path.splitext(os.path.basename(fn))[0]
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", base)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    m = re.search(r"\b(\d{2})(\d{2})(\d{2,4})\b", base)
    if m:
        mo, d, y = m.groups()
        if len(y) == 2:
            y = "20" + y
        try:
            return datetime(int(y), int(mo), int(d))
        except ValueError:
            pass
    return None


def extract_meeting_date(filename: str, clean_full_text: str) -> Optional[datetime]:
    """Best-effort meeting date.

    Strategy, in order:
      1. Find a "Month Day, Year" *immediately followed by a clock time* —
         that's how the meeting header always renders ("October 15, 2025
         9:30 a.m."). This avoids picking up the boilerplate sentence
         "...meetings from June 8, 2016, forward..." that appears on every
         first page.
      2. Fall back to the filename's MMDDYYYY-style stamp.
      3. Final fallback: any Month Day, Year in the body.
    """
    anchored = re.search(
        rf"\b({_MONTHS})\s+(\d{{1,2}}),\s+(\d{{4}})\s+\d{{1,2}}[:\.]\d{{2}}",
        clean_full_text, re.IGNORECASE,
    )
    if anchored:
        try:
            return datetime.strptime(
                f"{anchored.group(1).title()} {anchored.group(2)}, {anchored.group(3)}",
                "%B %d, %Y",
            )
        except ValueError:
            pass

    fname_dt = _date_from_filename(filename)
    if fname_dt:
        return fname_dt

    m = re.search(rf"\b({_MONTHS})\s+(\d{{1,2}}),\s+(\d{{4}})\b",
                  clean_full_text, re.IGNORECASE)
    if m:
        try:
            return datetime.strptime(
                f"{m.group(1).title()} {m.group(2)}, {m.group(3)}",
                "%B %d, %Y",
            )
        except ValueError:
            pass
    return None


def extract_start_time(clean_full_text: str) -> Optional[str]:
    m = re.search(
        r"\b(\d{1,2}[:\.]\d{2})\s*([ap])\.?m\.?\b",
        clean_full_text, re.IGNORECASE,
    )
    if not m:
        return None
    hhmm = m.group(1).replace(".", ":")
    return f"{hhmm} {m.group(2).lower()}m"


def extract_end_time(clean_full_text: str) -> Optional[str]:
    """Look for adjournment time near 'Adjournment' tokens."""
    patterns = [
        r"Adjourn(?:ed|ment)?\s+at\s+(\d{1,2}[:\.]\d{2})\s*([ap])\.?m\.?",
        r"ADJOURN(?:ED|MENT)\s+at\s+(\d{1,2}[:\.]\d{2})\s*([ap])\.?m\.?",
        r"Adjourn(?:ed|ment)?\s*[:\-]\s*(\d{1,2}[:\.]\d{2})\s*([ap])\.?m\.?",
    ]
    for p in patterns:
        m = re.search(p, clean_full_text, re.IGNORECASE)
        if m:
            return f"{m.group(1).replace('.', ':')} {m.group(2).lower()}m"
    return None


def detect_status(clean_full_text: str, filename: str) -> str:
    haystack = (clean_full_text + " " + filename).lower()
    if "cancelled" in haystack or "cancellation" in haystack:
        return "Cancelled"
    return "Accepted"


# Canonical meeting-type labels. Match the categories supplied by the team.
MEETING_TYPES = {
    "REGULAR_COUNCIL":   "Regular Council Meeting",
    "COUNCIL_WORKSHOP":  "Council Workshop",
    "SPECIAL_CALLED":    "Special Called Meeting",
    "JOINT":             "Joint Meeting",
    "PUBLIC_HEARING":    "Public Hearing",
    "QUASI_JUDICIAL":    "Quasi-judicial Hearing",
    "STRATEGIC":         "Goal-setting / Strategic Planning Session",
    "PZDB_INFO":         "PZDB Public Information Meeting",
    "PZDB_HEARING":      "PZDB Public Hearing",
    "PZDB_WORKSHOP":     "PZDB Workshop",
    "PZDB_REGULAR":      "PZDB Meeting",
}


_PZDB_PAT = re.compile(
    r"pz(?:db|b)\b|planning[,\s]+zoning(?:[,\s]+(?:and|&)[,\s]+design"
    r"\s+board)?|design\s+board",
    re.IGNORECASE,
)


def _classify_label(label: str) -> Optional[str]:
    """Map a single short label string (filename hint or title line) to a
    canonical meeting type, or ``None`` if it doesn't match any."""
    if not label:
        return None
    low = label.lower()

    is_pzdb = bool(_PZDB_PAT.search(low))
    if is_pzdb:
        if "public information" in low:
            return MEETING_TYPES["PZDB_INFO"]
        if "public hearing" in low:
            return MEETING_TYPES["PZDB_HEARING"]
        if "workshop" in low:
            return MEETING_TYPES["PZDB_WORKSHOP"]
        return MEETING_TYPES["PZDB_REGULAR"]

    if re.search(r"goal[\s-]*setting|strategic\s+planning", low):
        return MEETING_TYPES["STRATEGIC"]
    if "quasi" in low and ("judicial" in low or "hearing" in low):
        return MEETING_TYPES["QUASI_JUDICIAL"]
    if re.search(r"\bjoint\s+(?:meeting|workshop|session)\b", low):
        return MEETING_TYPES["JOINT"]
    if re.search(r"\bspecial\b.*\b(?:meeting|hearing|emergency)\b"
                 r"|\borganizational\b|\bbudget\s+hearing\b"
                 r"|\bemergency\s+meeting\b", low):
        return MEETING_TYPES["SPECIAL_CALLED"]
    if "workshop" in low:
        return MEETING_TYPES["COUNCIL_WORKSHOP"]
    if re.search(r"public\s+hearing|zoning\s+hearing|dri\s+development", low):
        return MEETING_TYPES["PUBLIC_HEARING"]
    if re.search(r"regular\s+meeting|council\s+meeting", low):
        return MEETING_TYPES["REGULAR_COUNCIL"]
    return None


_TITLE_TRIGGERS = (
    # Strong, uppercase/title-cased headings used in the documents
    r"VILLAGE\s+COUNCIL[^\n]*",
    r"Village\s+Council[^\n]*",
    r"PLANNING[,\s]+ZONING[^\n]*",
    r"Planning[,\s]+Zoning[^\n]*",
    r"PZDB[^\n]*",
    r"PZB[^\n]*",
)


def _candidate_title_lines(raw_text: str) -> List[str]:
    """Pull lines that look like the document's *type* heading.

    These appear early in the body, on their own line, and follow words like
    "FINAL ACTION AGENDA/MINUTES". They do **not** appear inside a numbered
    agenda item (e.g. "5. PUBLIC HEARING: (A) ..."), so we only consider
    early lines and skip ones that start with a digit + dot.
    """
    out: List[str] = []
    if not raw_text:
        return out
    head = raw_text[:2500]
    for line in head.splitlines():
        s = line.strip()
        if not s or len(s) > 120:
            continue
        if re.match(r"^\d+[.)]\s", s):  # numbered agenda item
            continue
        if re.search(r"|".join(_TITLE_TRIGGERS), s):
            out.append(s)
    return out


def extract_meeting_type(filename: str, clean_full_text: str,
                         raw_text: Optional[str] = None) -> str:
    """Classify the meeting from filename hint + document title line.

    Order of precedence:
      1. Filename keywords (clerks type these explicitly: "Workshop",
         "Special Meeting", "Joint Workshop", "Zoning Hearing", ...).
      2. The first matching title line near the top of the body
         ("Village Council Special Meeting", "Village Council Workshop",
         "Planning, Zoning & Design Board Public Hearing", ...).
      3. Fallback: Regular Council Meeting.

    We deliberately do **not** scan the entire body, since regular meetings
    routinely contain agenda items labelled "PUBLIC HEARING:" or
    "Quasi-judicial" that would otherwise hijack the classification.
    """
    fn = filename or ""
    fn_label = re.sub(r"\.pdf$", "", fn, flags=re.I)
    fn_label = re.sub(r"\bcancel(?:led)?\b", "", fn_label, flags=re.I)
    fn_label = re.sub(r"\bapproved\b|\bminutes?\b", "", fn_label, flags=re.I)
    fn_label = re.sub(r"[\d_/-]+", " ", fn_label).strip()
    fn_hit = _classify_label(fn_label)
    if fn_hit:
        return fn_hit

    source = raw_text if raw_text else clean_full_text
    for line in _candidate_title_lines(source or ""):
        title_hit = _classify_label(line)
        if title_hit:
            return title_hit

    return MEETING_TYPES["REGULAR_COUNCIL"]


def extract_staff_code(raw_full_text: str, clean_full_text: str) -> Optional[str]:
    """Pull the 'td/CS' style author code from the trailer."""
    m = re.search(r"\(([A-Za-z]{2}/[A-Za-z]{2})\)", raw_full_text)
    if m:
        return m.group(1).upper()
    m = re.search(r"\(([A-Za-z]{2}/[A-Za-z]{2})\)", clean_full_text)
    if m:
        return m.group(1).upper()
    if "Sarkozy" in clean_full_text:
        return "SS"
    if "Gibbs" in clean_full_text:
        return "MG"
    return None


# --- High-level convenience ---------------------------------------------------

def process_pdf(pdf_path: str) -> dict:
    """Full extract+clean+parse pipeline. Returns structured fields."""
    pages = extract_pages(pdf_path)
    raw = "\n".join(pages)
    clean = clean_text(raw)
    fn = os.path.basename(pdf_path)
    status = detect_status(clean, fn)
    if status == "Cancelled":
        actions = ["Meeting Cancelled"]
        end_time = "N/A"
    else:
        actions = extract_actions(clean)
        end_time = extract_end_time(clean)
    return {
        "filename": fn,
        "raw_text": raw,
        "clean_text": clean,
        "meeting_date": extract_meeting_date(fn, clean),
        "meeting_type": extract_meeting_type(fn, clean, raw),
        "start_time": extract_start_time(clean) or "9:30 am",
        "end_time": end_time,
        "status": status,
        "staff_code": extract_staff_code(raw, clean),
        "actions": actions,
        "action_text": join_actions(actions),
    }
