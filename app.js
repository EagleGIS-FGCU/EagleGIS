/* ==========================================================================
   app.js — ALL the behavior for the EagleGIS site (index.html)
   ==========================================================================

   New to the project? Here's the map:

   - index.html  = the page structure (what's on the page, incl. the map)
   - styles.css  = how it looks (colors, sizes)
   - app.js      = this file: how it behaves (loading data, search, filters)

   This file is organized top-to-bottom as:
     1. SETTINGS YOU MIGHT WANT TO CHANGE  (just below — safe to edit)
     2. Meetings tab   (loads the CSV, search, filters, detail panel)
     3. Community News tab   (live articles from EsteroToday.com)
     4. Minutes PDF resolver  (finds official PDFs on estero-fl.gov)
     5. Reports & Governing Docs panel  (Engage Estero documents)
     6. Upcoming Meetings tab  (live calendar from estero-fl.gov)
     7. Startup  (the last few lines kick everything off)

   If you only need to change a label, a color, or where data comes from,
   you should not need to read past section 1.
   ========================================================================== */

/* ──────────────────────────────────────────────────────────────────────────
   1. SETTINGS YOU MIGHT WANT TO CHANGE
   ────────────────────────────────────────────────────────────────────────── */

// Public data deliverables (rebuilt by `python -m app.pipeline.run`).
// The site loads site_manifest.json first, then JSON (or year-shards when large).
const MANIFEST_URL = 'app/data/gold/site_manifest.json';
const CSV_URL = 'app/data/gold/meetings_public.csv';
const DATA_CACHE_TTL_MS = 24 * 60 * 60 * 1000;

let siteManifest = null;

// Every meeting type and how its "chip" looks in the sidebar:
//   color = text color, bg = background, bd = border (hex color codes)
//   short = the label shown on the chip
//   icon  = a Font Awesome icon name (browse https://fontawesome.com/icons)
// To support a NEW meeting type, add a line here — otherwise it shows
// with the generic FALLBACK_TYPE look below.
const TYPES = {
    "Regular Council Meeting":                    {color:"#0052a5",bg:"#eff6ff",bd:"#93c5fd",short:"Regular Council",icon:"fa-gavel"},
    "Council Workshop":                           {color:"#c2410c",bg:"#fff7ed",bd:"#fdba74",short:"Workshop",icon:"fa-screwdriver-wrench"},
    "Special Called Meeting":                     {color:"#b91c1c",bg:"#fef2f2",bd:"#fca5a5",short:"Special Called",icon:"fa-bullhorn"},
    "Joint Meeting":                              {color:"#15803d",bg:"#f0fdf4",bd:"#86efac",short:"Joint",icon:"fa-handshake"},
    "Public Hearing":                             {color:"#6d28d9",bg:"#f5f3ff",bd:"#c4b5fd",short:"Public Hearing",icon:"fa-scale-balanced"},
    "Quasi-judicial Hearing":                     {color:"#4338ca",bg:"#eef2ff",bd:"#a5b4fc",short:"Quasi-judicial",icon:"fa-scale-balanced"},
    "Goal-setting / Strategic Planning Session":  {color:"#0f766e",bg:"#f0fdfa",bd:"#5eead4",short:"Strategic",icon:"fa-bullseye"},
    "PZDB Meeting":                               {color:"#374151",bg:"#f9fafb",bd:"#d1d5db",short:"PZDB",icon:"fa-building-columns"},
    "PZDB Public Information Meeting":            {color:"#0369a1",bg:"#f0f9ff",bd:"#7dd3fc",short:"PZDB Info",icon:"fa-circle-info"},
    "PZDB Public Hearing":                        {color:"#7e22ce",bg:"#faf5ff",bd:"#d8b4fe",short:"PZDB Hearing",icon:"fa-scale-balanced"},
    "PZDB Workshop":                              {color:"#854d0e",bg:"#fefce8",bd:"#fde68a",short:"PZDB Wkshp",icon:"fa-screwdriver-wrench"},
};
const FALLBACK_TYPE = {color:"#0052a5",bg:"#eff6ff",bd:"#93c5fd",short:"Other",icon:"fa-file"};
const t = type => TYPES[type] || FALLBACK_TYPE;

/** Run work after first paint when the browser is idle (with a timeout fallback). */
function scheduleIdle(fn, timeoutMs = 2000) {
    if ('requestIdleCallback' in window) requestIdleCallback(fn, { timeout: timeoutMs });
    else setTimeout(fn, 100);
}

/** Defer the heavy ArcGIS embed until after the meeting list has painted. */
function loadDeferredMap() {
    const iframe = document.getElementById('map-iframe');
    if (!iframe || iframe.dataset.loaded || !iframe.dataset.src) return;
    iframe.src = iframe.dataset.src;
    iframe.dataset.loaded = '1';
}

const MEETINGS_PAGE_SIZE = 50;
let meetingsDisplayLimit = MEETINGS_PAGE_SIZE;
let _meetingsScrollObserver = null;

function versionedUrl(path, sha256) {
    const v = sha256 ? String(sha256).slice(0, 12) : String(Date.now());
    return `${path}?v=${v}`;
}

function readDataCache(key) {
    try {
        const raw = localStorage.getItem(key);
        if (!raw) return null;
        const { ts, data } = JSON.parse(raw);
        if (Date.now() - ts > DATA_CACHE_TTL_MS) return null;
        return data;
    } catch (e) { return null; }
}

function writeDataCache(key, data) {
    try {
        localStorage.setItem(key, JSON.stringify({ ts: Date.now(), data }));
    } catch (e) { /* quota exceeded */ }
}

async function fetchJson(url) {
    const res = await fetch(url);
    if (!res.ok) throw new Error('HTTP ' + res.status);
    return res.json();
}

function compareMeetingRows(a, b) {
    const byDate = (b.MeetingDate || '').localeCompare(a.MeetingDate || '');
    if (byDate !== 0) return byDate;
    return (a.ProjectName || '').localeCompare(b.ProjectName || '');
}

async function loadSiteManifest() {
    siteManifest = await fetchJson(MANIFEST_URL);
    return siteManifest;
}

async function loadMeetingsRecords(manifest) {
    const meta = manifest.meetings || {};
    const sha = meta.sha256 || '';
    const cacheKey = `eaglegis:meetings:v1:${sha}`;
    const cached = readDataCache(cacheKey);
    if (cached) return cached;

    let rows = null;
    if (meta.shards && meta.shards.length) {
        const parts = await Promise.all(
            meta.shards.map(s => fetchJson(versionedUrl(s.path, sha)))
        );
        rows = parts.flat().sort(compareMeetingRows);
    } else if (meta.json) {
        rows = await fetchJson(versionedUrl(meta.json, sha));
    }

    if (rows) {
        writeDataCache(cacheKey, rows);
        return rows;
    }

    return new Promise((resolve, reject) => {
        if (typeof Papa === 'undefined') {
            reject(new Error('PapaParse unavailable'));
            return;
        }
        Papa.parse(versionedUrl(meta.csv || CSV_URL, sha), {
            download: true, header: true, skipEmptyLines: true,
            complete: ({ data }) => resolve(data),
            error: reject,
        });
    });
}

function onMeetingsLoaded(data) {
    allData = data;
    populateYears();
    buildTypeFilters();
    run();
    setupSearch();
    setupFilters();
    setupControls();
    setupBackTop();
    setupRecordListDelegation();
    setupMeetingsInfiniteScroll();
    scheduleIdle(() => buildMeetingSearchIndex());
    scheduleIdle(() => loadMinutesIndex(), 3000);
    scheduleIdle(loadDeferredMap, 1500);
}

/* ──────────────────────────────────────────────────────────────────────────
   2. MEETINGS TAB — load the CSV, then search / filter / sort / render
   ────────────────────────────────────────────────────────────────────────── */

// Full-text index (MiniSearch) — built once per CSV load. Row identity is the
// array index in allData (stable for this session). Indexed fields mirror
// the gold CSV: ProjectName, MeetingType, MeetingDate, MeetingYear,
// Status, ActionTaken, StartTime, StaffCode, Title, MinutesURL, DocDate,
// LocationName, Latitude, Longitude.
let meetingSearch = null;

let allData=[], active=new Set(['all']), sortMode='newest', yearFilter='all', current=[];

const fmtDate = d => {
    if (!d) return '—';
    const dt = new Date(d+'T00:00:00');
    return isNaN(dt) ? d : dt.toLocaleDateString('en-US',{year:'numeric',month:'long',day:'numeric'});
};
const sCls = s => {
    if (!s) return '';
    const l=s.toLowerCase();
    return l==='accepted'?'s-accepted':l==='pending'?'s-pending':l==='cancelled'?'s-cancelled':'';
};
const noAct = t => !t||['No action found','Meeting Cancelled','No action extracted - verify PDF'].includes(t);

function highlight(text, termRaw) {
    if (!termRaw || !text) return text;
    const parts = String(termRaw).toLowerCase().trim().split(/\s+/).filter(Boolean);
    if (!parts.length) return text;
    const escaped = parts.map(p => p.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
    const re = new RegExp('(' + escaped.join('|') + ')', 'gi');
    return String(text).replace(re, '<span class="hl">$1</span>');
}

function showSkeleton() {
    document.getElementById('data-list').innerHTML = Array(5).fill('').map(()=>`
        <div class="skeleton-card">
            <div style="display:flex;justify-content:space-between;margin-bottom:8px;">
                <div class="skel-line" style="height:20px;width:30%;border-radius:5px;"></div>
                <div class="skel-line" style="height:14px;width:20%;border-radius:4px;"></div>
            </div>
            <div class="skel-line" style="height:12px;width:95%;"></div>
            <div class="skel-line" style="height:12px;width:75%;margin-bottom:10px;"></div>
            <div style="display:flex;justify-content:space-between;">
                <div class="skel-line" style="height:12px;width:40%;"></div>
                <div class="skel-line" style="height:24px;width:25%;border-radius:5px;"></div>
            </div>
        </div>`).join('');
}

async function init() {
    showSkeleton();
    try {
        const manifest = await loadSiteManifest();
        const data = await loadMeetingsRecords(manifest);
        onMeetingsLoaded(data);
    } catch (err) {
        console.warn('Manifest/JSON load failed; falling back to CSV:', err);
        if (typeof Papa === 'undefined') {
            document.getElementById('data-list').innerHTML =
                `<div class="empty"><i class="fa-solid fa-triangle-exclamation" style="color:#ef4444;"></i><p style="color:#ef4444;">Could not load data.<br>Meeting records failed to load.</p></div>`;
            return;
        }
        Papa.parse(CSV_URL, {
            download: true, header: true, skipEmptyLines: true,
            complete: ({ data }) => onMeetingsLoaded(data),
            error: () => {
                document.getElementById('data-list').innerHTML =
                    `<div class="empty"><i class="fa-solid fa-triangle-exclamation" style="color:#ef4444;"></i><p style="color:#ef4444;">Could not load data.<br>The meetings file (app/data/gold/meetings_public.csv) failed to load.</p></div>`;
            },
        });
    }
}

/**
 * Builds an in-browser full-text index over all CSV columns used by the UI.
 * Row IDs are numeric indices into allData (session-stable).
 */
function buildMeetingSearchIndex() {
    meetingSearch = null;
    if (typeof MiniSearch === 'undefined' || !allData.length) return;
    try {
        const ms = new MiniSearch({
            idField: 'id',
            fields: [
                'projectName',
                'meetingType',
                'meetingDate',
                'meetingYear',
                'status',
                'actionTaken',
                'startTime',
                'staffCode',
                'title',
                'minutesUrl',
                'docDate',
                'locationName',
                'coordinates',
            ],
        });
        const docs = allData.map((row, i) => ({
            id: String(i),
            projectName: row.ProjectName || '',
            meetingType: row.MeetingType || '',
            meetingDate: row.MeetingDate || '',
            meetingYear: row.MeetingYear || '',
            status: row.Status || '',
            actionTaken: row.ActionTaken || '',
            startTime: row.StartTime || '',
            staffCode: row.StaffCode || '',
            title: row.Title || '',
            minutesUrl: row.MinutesURL || '',
            docDate: row.DocDate || '',
            locationName: row.LocationName || '',
            coordinates: [row.Latitude, row.Longitude].filter(Boolean).join(' '),
        }));
        ms.addAll(docs);
        meetingSearch = ms;
    } catch (e) {
        console.warn('Meeting search index failed:', e);
        meetingSearch = null;
    }
}

function populateYears() {
    const years = [...new Set(allData.map(r=>r.MeetingYear).filter(Boolean))].sort((a,b)=>b-a);
    const sel = document.getElementById('year-filter');
    years.forEach(y => {
        const opt = document.createElement('option');
        opt.value = y; opt.textContent = y;
        sel.appendChild(opt);
    });
}

// Build a filter chip for every meeting type that actually appears in the
// loaded data. Types are sorted by frequency (most-common first) so the
// sidebar isn't dominated by rare categories.
function buildTypeFilters() {
    const counts = new Map();
    allData.forEach(r => {
        const k = (r.MeetingType || '').trim() || 'Other';
        counts.set(k, (counts.get(k) || 0) + 1);
    });
    const ordered = [...counts.entries()].sort((a,b) => b[1]-a[1]);
    const row = document.getElementById('filter-row');

    // The "All" button keeps the sticky behaviour of the original UI.
    const allBtn = row.querySelector('[data-type="all"]');
    if (allBtn) {
        const existing = allBtn.querySelector('.chip-count');
        const html = `<span class="chip-count">${allData.length}</span>`;
        if (existing) existing.outerHTML = html; else allBtn.insertAdjacentHTML('beforeend', html);
    }

    ordered.forEach(([type, n]) => {
        const meta = t(type);
        const btn = document.createElement('button');
        btn.className = 'filter-btn';
        btn.dataset.type = type;
        btn.style.cssText = `background:${meta.bg};color:${meta.color};border-color:${meta.bd};`;
        btn.innerHTML = `<i class="fa-solid ${meta.icon}"></i> ${meta.short}<span class="chip-count">${n}</span>`;
        row.appendChild(btn);
    });
}

function compareRowsBySortMode(a, b) {
    if (sortMode === 'newest') return new Date(b.MeetingDate) - new Date(a.MeetingDate);
    if (sortMode === 'oldest') return new Date(a.MeetingDate) - new Date(b.MeetingDate);
    const typeCmp = (a.MeetingType || '').localeCompare(b.MeetingType || '');
    if (typeCmp !== 0) return typeCmp;
    return new Date(b.MeetingDate) - new Date(a.MeetingDate);
}

function run() {
    // The sidebar list is shared across three tabs. Re-route the input event
    // to whichever renderer owns the active view; only the Meetings view's
    // logic lives in this function.
    if (typeof currentView !== 'undefined') {
        if (currentView === 'news') {
            if (typeof renderNews === 'function') renderNews();
            return;
        }
        if (currentView === 'upcoming') {
            if (typeof renderUpcoming === 'function') renderUpcoming();
            return;
        }
    }
    const qRaw = document.getElementById('main-search').value.trim();
    const q = qRaw.toLowerCase();
    const useIndex = !!q && meetingSearch;

    const scores = new Map();
    let idSet = null;
    if (useIndex) {
        const hits = meetingSearch.search(qRaw, {
            prefix: true,
            fuzzy: 0.2,
            combineWith: 'AND',
            boost: {
                title: 1.7,
                actionTaken: 1.45,
                projectName: 1.25,
                meetingType: 1.15,
                locationName: 1.1,
                minutesUrl: 1.05,
            },
        });
        idSet = new Set(hits.map(h => parseInt(h.id, 10)));
        hits.forEach(h => scores.set(parseInt(h.id, 10), h.score));
    }

    let rows = allData.map((r, idx) => ({ r, idx })).filter(({ r, idx }) => {
        const matchesType = active.has('all') || active.has((r.MeetingType || '').trim() || 'Other');
        const matchesYear = yearFilter === 'all' || r.MeetingYear === yearFilter;
        let matchesText = true;
        if (q) {
            if (useIndex && idSet) {
                matchesText = idSet.has(idx);
            } else {
                matchesText =
                    (r.ActionTaken || '').toLowerCase().includes(q) ||
                    (r.MeetingDate || '').toLowerCase().includes(q) ||
                    (r.MeetingType || '').toLowerCase().includes(q) ||
                    (r.ProjectName || '').toLowerCase().includes(q) ||
                    (r.LocationName || '').toLowerCase().includes(q) ||
                    (r.StaffCode || '').toLowerCase().includes(q) ||
                    (r.Title || '').toLowerCase().includes(q) ||
                    (r.Status || '').toLowerCase().includes(q) ||
                    (r.MinutesURL || '').toLowerCase().includes(q) ||
                    (r.DocDate || '').toLowerCase().includes(q);
            }
        }
        return matchesType && matchesYear && matchesText;
    });

    if (useIndex && scores.size) {
        rows.sort((a, b) => {
            const sb = scores.get(b.idx) ?? 0;
            const sa = scores.get(a.idx) ?? 0;
            if (sb !== sa) return sb - sa;
            return compareRowsBySortMode(a.r, b.r);
        });
    } else {
        rows.sort((a, b) => compareRowsBySortMode(a.r, b.r));
    }

    current = rows.map(x => x.r);
    meetingsDisplayLimit = MEETINGS_PAGE_SIZE;
    stats(current);
    render(current);
}

function stats(d) {
    document.getElementById('s-count').textContent = d.length;
    document.getElementById('s-years').textContent = new Set(d.map(r=>r.MeetingYear).filter(Boolean)).size||'—';
    document.getElementById('s-types').textContent = new Set(d.map(r=>r.MeetingType).filter(Boolean)).size||'—';
    // Count both CSV-supplied URLs and rows where the manifest can fill in a
    // canonical estero-fl.gov copy. This reflects the actual PDF coverage
    // the UI is offering, not just what the CSV ships with.
    const pdfCount = d.filter(r => r.MinutesURL || resolveMinutesPdf(r.MeetingType, r.MeetingDate)).length;
    document.getElementById('s-pdfs').textContent  = pdfCount;
    const badge = document.getElementById('tab-count-meetings');
    if (badge) badge.textContent = d.length;
}

function renderCard(row, i) {
    const {color,bg,bd,short,icon}=t(row.MeetingType);
    const rawAction = noAct(row.ActionTaken) ? null : row.ActionTaken;
    const qForHl = document.getElementById('main-search').value.trim();
    const displayAction = rawAction
        ? highlight(rawAction.length>130?rawAction.slice(0,130)+'...':rawAction, qForHl)
        : `<span style="font-style:italic;color:#9ca3af;">View PDF for full meeting details.</span>`;
    // Prefer the CSV-supplied URL when present; otherwise fall back to the
    // canonical Village PDF resolved from the minutes index.
    const pdfUrl = row.MinutesURL || resolveMinutesPdf(row.MeetingType, row.MeetingDate);
    const fromManifest = !row.MinutesURL && pdfUrl;
    return `
    <div class="record-card" data-idx="${i}">
        <div class="card-top">
            <span class="project-pill" style="background:${bg};color:${color};border-color:${bd};" title="${row.MeetingType||''}">
                <i class="fa-solid ${icon}"></i>${short}
            </span>
            <span class="card-date">${highlight(row.MeetingDate||'—', qForHl)}</span>
        </div>
        <div class="card-action">${displayAction}</div>
        <div class="card-footer">
            <span class="card-loc"><i class="fa-solid fa-location-dot" style="color:${color};font-size:10px;"></i>${highlight(row.LocationName||'—', qForHl)}</span>
            <div class="card-btns">
                <button class="btn-sm btn-outline detail-btn" data-idx="${i}">
                    <i class="fa-solid fa-circle-info"></i>Details
                </button>
                ${pdfUrl
                    ?`<a class="btn-sm btn-solid" href="${pdfUrl}" target="_blank" rel="noopener" style="background:${color};" title="${fromManifest ? 'Canonical estero-fl.gov copy' : 'Mirror copy'}">
                        <i class="fa-solid fa-file-pdf"></i>PDF${fromManifest ? '<sup style="font-size:7px;opacity:0.85;margin-left:2px;">VOE</sup>' : ''}
                      </a>`
                    :''}
            </div>
        </div>
    </div>`;
}

function render(data) {
    const list = document.getElementById('data-list');
    if (!data.length) {
        list.innerHTML=`<div class="empty"><i class="fa-solid fa-magnifying-glass"></i><p>No matching records found.<br>Try adjusting your filters.</p></div>`;
        return;
    }

    const visible = data.slice(0, meetingsDisplayLimit);
    const hasMore = data.length > meetingsDisplayLimit;

    // When sorted "By Meeting Type", emit a sticky header before each new
    // type group so the grouping is visually obvious.
    if (sortMode === 'type') {
        let html = '';
        let lastType = null;
        const groupCounts = data.reduce((acc, r) => {
            const k = r.MeetingType || 'Other';
            acc[k] = (acc[k] || 0) + 1;
            return acc;
        }, {});
        visible.forEach((row, i) => {
            const type = row.MeetingType || 'Other';
            if (type !== lastType) {
                const meta = t(type);
                html += `
                <div class="group-header" style="color:${meta.color};">
                    <i class="fa-solid ${meta.icon}"></i>${type}
                    <span class="gh-count">${groupCounts[type]}</span>
                </div>`;
                lastType = type;
            }
            html += renderCard(row, i);
        });
        list.innerHTML = html + (hasMore ? meetingsScrollSentinelHtml() : '');
    } else {
        list.innerHTML = visible.map(renderCard).join('') + (hasMore ? meetingsScrollSentinelHtml() : '');
    }

    observeMeetingsSentinel();
}

function meetingsScrollSentinelHtml() {
    return `<div class="meetings-scroll-sentinel" aria-hidden="true"></div>`;
}

function setupMeetingsInfiniteScroll() {
    const list = document.getElementById('data-list');
    if (!list || _meetingsScrollObserver) return;
    _meetingsScrollObserver = new IntersectionObserver(entries => {
        if (!entries.some(e => e.isIntersecting)) return;
        if (currentView !== 'meetings' || meetingsDisplayLimit >= current.length) return;
        meetingsDisplayLimit += MEETINGS_PAGE_SIZE;
        render(current);
    }, { root: list, rootMargin: '160px' });
}

function observeMeetingsSentinel() {
    if (!_meetingsScrollObserver) return;
    const list = document.getElementById('data-list');
    _meetingsScrollObserver.disconnect();
    const sentinel = list.querySelector('.meetings-scroll-sentinel');
    if (sentinel) _meetingsScrollObserver.observe(sentinel);
}

/** One delegated listener for all meeting cards (avoids N listeners per render). */
function setupRecordListDelegation() {
    document.getElementById('data-list').addEventListener('click', e => {
        if (currentView !== 'meetings') return;
        const detailBtn = e.target.closest('.detail-btn');
        if (detailBtn) {
            e.stopPropagation();
            openDetail(parseInt(detailBtn.dataset.idx, 10));
            return;
        }
        if (e.target.closest('a')) return;
        const card = e.target.closest('.record-card');
        if (card) openDetail(parseInt(card.dataset.idx, 10));
    });
}

function openDetail(idx) {
    const row = current[idx];
    if (!row) return;
    document.querySelectorAll('.record-card').forEach(c=>c.classList.remove('active'));
    const card = document.querySelector(`.record-card[data-idx="${idx}"]`);
    if (card) { card.classList.add('active'); card.scrollIntoView({behavior:'smooth',block:'nearest'}); }

    const {color,bg,bd,icon} = t(row.MeetingType);

    const qForHl = document.getElementById('main-search').value.trim();
    const actions = noAct(row.ActionTaken)
        ? `<div class="action-empty"><i class="fa-solid fa-circle-info" style="margin-right:5px;"></i>No action text available — view the PDF for full meeting details.</div>`
        : row.ActionTaken.split(' | ').filter(Boolean).map(a=>`<div class="action-item">${highlight(a.trim(), qForHl)}</div>`).join('');

    document.getElementById('detail-content').innerHTML=`
        <div class="detail-banner" style="background:${bg};border-color:${bd};">
            <div class="detail-banner-name" style="color:${color};">
                <i class="fa-solid ${icon}"></i>${row.MeetingType||'Meeting'}
            </div>
            ${row.ProjectName
                ? `<div style="margin-top:6px;font-size:13px;font-weight:600;color:${color};display:flex;align-items:center;gap:6px;">
                       <i class="fa-solid fa-diagram-project" style="font-size:11px;opacity:0.8;"></i>${row.ProjectName}
                   </div>`
                : ''}
            <div class="detail-banner-meta" style="color:${color};margin-top:4px;">${fmtDate(row.MeetingDate)}</div>
        </div>

        <div class="detail-grid">
            <div class="detail-cell full">
                <div class="dcl"><i class="fa-solid fa-diagram-project"></i>Project</div>
                <div class="dcv" style="font-weight:600;font-size:13px;">${row.ProjectName||'—'}</div>
            </div>
            <div class="detail-cell">
                <div class="dcl"><i class="fa-solid fa-circle-check"></i>Status</div>
                <span class="status-chip ${sCls(row.Status)}">${row.Status||'—'}</span>
            </div>
            <div class="detail-cell">
                <div class="dcl"><i class="fa-solid fa-user"></i>Staff Code</div>
                <div class="dcv" style="font-family:'IBM Plex Mono',monospace;font-size:12px;">${row.StaffCode||'—'}</div>
            </div>
            <div class="detail-cell full">
                <div class="dcl"><i class="fa-solid fa-location-dot"></i>Location <span style="color:#9ca3af;font-weight:500;">(ArcGIS)</span></div>
                <div class="dcv" style="font-weight:500;font-size:12px;">${row.LocationName||'—'}</div>
                ${(row.Latitude && row.Longitude)
                    ? `<div style="font-family:'IBM Plex Mono',monospace;font-size:10px;color:#9ca3af;margin-top:3px;">${row.Latitude}, ${row.Longitude}</div>`
                    : ''}
            </div>
            <div class="detail-cell">
                <div class="dcl"><i class="fa-regular fa-calendar"></i>Meeting Year</div>
                <div class="dcv">${row.MeetingYear||'—'}</div>
            </div>
            <div class="detail-cell">
                <div class="dcl"><i class="fa-solid fa-file-lines"></i>Doc Date</div>
                <div class="dcv" style="font-family:'IBM Plex Mono',monospace;font-size:11px;">${row.DocDate||'—'}</div>
            </div>
        </div>

        <div class="action-section">
            <div class="action-header"><i class="fa-solid fa-list-check"></i>Action Taken</div>
            <div class="action-box">${actions}</div>
        </div>

        ${(() => {
            const pdf = row.MinutesURL || resolveMinutesPdf(row.MeetingType, row.MeetingDate);
            const fromManifest = !row.MinutesURL && pdf;
            if (!pdf) {
                return `<div class="no-pdf"><i class="fa-solid fa-ban" style="margin-right:6px;color:#9ca3af;"></i>No PDF available for this record</div>`;
            }
            const label = fromManifest
                ? 'View Approved Minutes (estero-fl.gov)'
                : 'View Full Meeting Minutes PDF';
            return `<a class="pdf-btn" href="${pdf}" target="_blank" rel="noopener" style="background:${color};">
                        <i class="fa-solid fa-file-pdf"></i>${label}
                    </a>`;
        })()}`;

    document.getElementById('detail-panel').classList.add('open');
    document.getElementById('map-spot').style.marginLeft='380px';
}

document.getElementById('close-detail').addEventListener('click',()=>{
    document.getElementById('detail-panel').classList.remove('open');
    document.getElementById('map-spot').style.marginLeft='0';
    document.querySelectorAll('.record-card').forEach(c=>c.classList.remove('active'));
    document.querySelectorAll('.news-card').forEach(c=>c.classList.remove('active'));
    if (typeof newsActiveId !== 'undefined') newsActiveId = null;
});

function setupSearch() {
    // 150ms debounce avoids re-rendering on every keystroke. The lists stay
    // responsive but expensive search/highlight passes only fire once the
    // user pauses typing.
    let timer = null;
    document.getElementById('main-search').addEventListener('input', () => {
        clearTimeout(timer);
        timer = setTimeout(() => run(), 150);
    });
}

function setupFilters() {
    // Use event delegation: type chips are added dynamically after the CSV
    // loads, so static querySelectorAll wouldn't see them.
    document.getElementById('filter-row').addEventListener('click', ev => {
        const btn = ev.target.closest('.filter-btn');
        if (!btn) return;
        const type = btn.dataset.type;
        if (type === 'all') {
            active = new Set(['all']);
            document.querySelectorAll('.filter-btn').forEach(b=>b.classList.remove('inactive'));
        } else {
            active.delete('all');
            document.querySelector('[data-type="all"]').classList.add('inactive');
            if (active.has(type)) { active.delete(type); btn.classList.add('inactive'); }
            else { active.add(type); btn.classList.remove('inactive'); }
            if (active.size === 0) {
                active = new Set(['all']);
                document.querySelectorAll('.filter-btn').forEach(b=>b.classList.remove('inactive'));
            }
        }
        run();
    });
}

function setupControls() {
    document.getElementById('year-filter').addEventListener('change', e=>{
        yearFilter = e.target.value; run();
    });
    document.getElementById('sort-select').addEventListener('change', e=>{
        sortMode = e.target.value; run();
    });
}

function setupBackTop() {
    const list = document.getElementById('data-list');
    const btn = document.getElementById('back-top');
    list.addEventListener('scroll', ()=>{
        btn.classList.toggle('visible', list.scrollTop > 200);
    });
    btn.addEventListener('click', ()=>{
        list.scrollTo({top:0, behavior:'smooth'});
    });
}

// ─────────────────────────────────────────────────────────────────────────
// 3. COMMUNITY NEWS TAB (EsteroToday.com — Engage Estero)
//
// EsteroToday.com is a WordPress site and exposes its content via the
// public REST API at /wp-json/wp/v2/posts. We request `_embed=1` to inline
// featured-media and term (category) data so we don't need follow-up calls.
// CORS is open on this endpoint, so we can call it directly from the
// browser. Posts are cached in-memory for the session.
// ─────────────────────────────────────────────────────────────────────────
const NEWS_API_BASE = 'https://esterotoday.com/wp-json/wp/v2/posts';
const NEWS_PAGE_SIZE = 20;
let newsData = [];
let newsCats = new Map(); // id -> {name, slug, count}
let newsActiveCat = 'all';
let newsActivePillar = 'all';
let newsLoaded = false;
let newsActiveId = null;
let newsNextPage = 2;
let newsHasMore = true;
let newsLoadingMore = false;
let currentView = 'meetings';

/**
 * Engage Estero markets four issue pillars on EsteroToday.com. Their WP
 * category slugs are stable; we hold the IDs as null until first discovered
 * by the runtime news fetch, then patch them in. This keeps the chips
 * functional even if WordPress reassigns IDs.
 */
const NEWS_PILLARS = [
    { slug: 'education',   label: 'Education',   icon: 'fa-graduation-cap', color: '#0369a1', bg: '#f0f9ff', bd: '#7dd3fc' },
    { slug: 'environment', label: 'Environment', icon: 'fa-leaf',           color: '#15803d', bg: '#f0fdf4', bd: '#86efac' },
    { slug: 'health',      label: 'Health',      icon: 'fa-heart-pulse',    color: '#b91c1c', bg: '#fef2f2', bd: '#fca5a5' },
    { slug: 'safety',      label: 'Safety',      icon: 'fa-shield-halved',  color: '#c2410c', bg: '#fff7ed', bd: '#fdba74' },
];

const NEWS_FALLBACK_IMG = null;

function stripHtml(html) {
    if (!html) return '';
    const tmp = document.createElement('div');
    tmp.innerHTML = html;
    return (tmp.textContent || tmp.innerText || '').replace(/\s+/g, ' ').trim();
}

function decodeEntities(html) {
    if (!html) return '';
    const tmp = document.createElement('textarea');
    tmp.innerHTML = html;
    return tmp.value;
}

function fmtNewsDate(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    if (isNaN(d)) return iso;
    return d.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
}

function getFeaturedImage(post) {
    if (post.jetpack_featured_media_url) return post.jetpack_featured_media_url;
    const media = post._embedded && post._embedded['wp:featuredmedia'];
    if (media && media[0]) {
        const m = media[0];
        if (m.source_url) return m.source_url;
        if (m.media_details && m.media_details.sizes) {
            const s = m.media_details.sizes;
            return (s.medium_large || s.medium || s.large || s.full || {}).source_url || null;
        }
    }
    return NEWS_FALLBACK_IMG;
}

function getPostCategories(post) {
    const terms = post._embedded && post._embedded['wp:term'];
    if (!terms) return [];
    // terms is an array-of-arrays; the first inner array is categories.
    const flat = [];
    terms.forEach(group => {
        (group || []).forEach(term => {
            if (term && term.taxonomy === 'category') flat.push(term);
        });
    });
    return flat;
}

function newsApiUrl(page) {
    const params = new URLSearchParams({
        _embed: '1',
        per_page: String(NEWS_PAGE_SIZE),
        page: String(page),
    });
    return `${NEWS_API_BASE}?${params.toString()}`;
}

async function loadNews() {
    const list = document.getElementById('data-list');
    list.innerHTML = `<div class="empty"><i class="fa-solid fa-spinner fa-spin"></i><p>Loading community news from EsteroToday.com...</p></div>`;
    try {
        const posts = await fetchWithSessionCache(newsApiUrl(1), 'news:p1', 5 * 60 * 1000);
        const list2 = Array.isArray(posts) ? posts : [];
        newsData = list2;
        newsNextPage = 2;
        newsHasMore = list2.length === NEWS_PAGE_SIZE;
        recomputeNewsCats();
        newsLoaded = true;
        buildNewsCatFilters();
        document.getElementById('tab-count-news').textContent = newsData.length;
        renderNews();
    } catch (err) {
        console.warn('News load failed:', err);
        list.innerHTML = `
            <div class="empty">
                <i class="fa-solid fa-triangle-exclamation" style="color:#ef4444;"></i>
                <p style="color:#ef4444;">Could not load community news.<br>
                <a href="https://esterotoday.com/" target="_blank" style="color:var(--accent);">Visit EsteroToday.com</a> directly.</p>
            </div>`;
    }
}

async function loadMoreNews() {
    if (newsLoadingMore || !newsHasMore) return;
    newsLoadingMore = true;
    const btn = document.querySelector('.load-more-btn');
    if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Loading…'; }
    try {
        const posts = await fetchWithSessionCache(
            newsApiUrl(newsNextPage),
            `news:p${newsNextPage}`,
            5 * 60 * 1000
        );
        const list2 = Array.isArray(posts) ? posts : [];
        if (!list2.length) {
            newsHasMore = false;
        } else {
            newsData = newsData.concat(list2);
            newsNextPage += 1;
            newsHasMore = list2.length === NEWS_PAGE_SIZE;
        }
        recomputeNewsCats();
        buildNewsCatFilters();
        document.getElementById('tab-count-news').textContent = newsData.length;
        renderNews();
    } catch (err) {
        // WordPress returns 400 when paginating past the last page; treat as
        // "no more" rather than an error.
        console.info('No more news pages:', err && err.message);
        newsHasMore = false;
        renderNews();
    } finally {
        newsLoadingMore = false;
    }
}

function recomputeNewsCats() {
    newsCats = new Map();
    newsData.forEach(p => {
        getPostCategories(p).forEach(c => {
            const prev = newsCats.get(c.id) || { id: c.id, name: c.name, slug: c.slug, count: 0 };
            prev.count += 1;
            newsCats.set(c.id, prev);
        });
    });
}

function buildNewsCatFilters() {
    const row = document.getElementById('news-cat-row');
    row.querySelectorAll('[data-cat]:not([data-cat="all"])').forEach(el => el.remove());
    const allBtn = row.querySelector('[data-cat="all"]');
    const existing = allBtn.querySelector('.chip-count');
    const allHtml = `<span class="chip-count">${newsData.length}</span>`;
    if (existing) existing.outerHTML = allHtml; else allBtn.insertAdjacentHTML('beforeend', allHtml);

    // Pillars are pulled out first so they don't compete for chip space in
    // the main topic list. Anything left over is rendered as a generic chip.
    const pillarSlugs = new Set(NEWS_PILLARS.map(p => p.slug.toLowerCase()));
    const generic = [...newsCats.values()].filter(c => !pillarSlugs.has((c.slug || '').toLowerCase()));
    generic.sort((a, b) => b.count - a.count);
    generic.forEach(c => {
        const btn = document.createElement('button');
        btn.className = 'filter-btn' + (newsActiveCat === String(c.id) ? '' : (newsActiveCat === 'all' ? '' : ' inactive'));
        btn.dataset.cat = String(c.id);
        btn.style.cssText = 'background:#f5f3ff;color:#6d28d9;border-color:#c4b5fd;';
        btn.innerHTML = `<i class="fa-solid fa-tag"></i> ${decodeEntities(c.name)}<span class="chip-count">${c.count}</span>`;
        row.appendChild(btn);
    });

    // Render pillar chips. We resolve the WP category id at runtime by
    // matching the slug from the loaded posts; chips for pillars that don't
    // appear in the loaded posts are still shown but disabled.
    const pillarRow = document.getElementById('news-pillar-row');
    pillarRow.innerHTML = '';
    NEWS_PILLARS.forEach(p => {
        const match = [...newsCats.values()].find(c => (c.slug || '').toLowerCase() === p.slug);
        const id = match ? String(match.id) : null;
        const count = match ? match.count : 0;
        const btn = document.createElement('button');
        const isActive = newsActivePillar === p.slug;
        btn.className = 'filter-btn' + (newsActivePillar === 'all' || isActive ? '' : ' inactive');
        btn.dataset.pillar = p.slug;
        if (id) btn.dataset.catId = id;
        btn.style.cssText = `background:${p.bg};color:${p.color};border-color:${p.bd};`;
        if (!id) btn.style.opacity = '0.55';
        btn.innerHTML = `<i class="fa-solid ${p.icon}"></i> ${p.label}<span class="chip-count">${count}</span>`;
        pillarRow.appendChild(btn);
    });
}

function filterNews() {
    const q = document.getElementById('main-search').value.trim().toLowerCase();
    // If a pillar is selected, narrow to posts in the matching category
    // (by slug, so the filter survives WordPress re-ID'ing the category).
    const pillarSlug = newsActivePillar !== 'all' ? newsActivePillar : null;
    return newsData.filter(p => {
        const cats = getPostCategories(p);
        if (newsActiveCat !== 'all') {
            const ids = cats.map(c => String(c.id));
            if (!ids.includes(newsActiveCat)) return false;
        }
        if (pillarSlug) {
            const slugs = cats.map(c => (c.slug || '').toLowerCase());
            if (!slugs.includes(pillarSlug)) return false;
        }
        if (!q) return true;
        const hay = (
            decodeEntities(p.title?.rendered || '') + ' ' +
            stripHtml(p.excerpt?.rendered || '') + ' ' +
            stripHtml(p.content?.rendered || '') + ' ' +
            cats.map(c => c.name).join(' ')
        ).toLowerCase();
        return hay.includes(q);
    });
}

function renderNews() {
    const list = document.getElementById('data-list');
    const filtered = filterNews();
    if (!filtered.length) {
        list.innerHTML = `<div class="empty"><i class="fa-solid fa-magnifying-glass"></i><p>No matching articles found.<br>Try a different search or topic.</p></div>`;
        return;
    }
    const qForHl = document.getElementById('main-search').value.trim();
    // Thumbnails are loaded lazily: we keep the src in `data-bg` and a
    // single IntersectionObserver swaps it onto background-image as cards
    // scroll into view. This keeps initial paint fast even with 40+ cards.
    const cardsHtml = filtered.map(p => {
        const img = getFeaturedImage(p);
        const cats = getPostCategories(p);
        const title = decodeEntities(p.title?.rendered || 'Untitled');
        const excerpt = stripHtml(p.excerpt?.rendered || '');
        const trimmedExcerpt = excerpt.length > 160 ? excerpt.slice(0, 160) + '…' : excerpt;
        const thumb = img
            ? `<div class="news-thumb" data-bg="${img}"></div>`
            : `<div class="news-thumb"><i class="fa-solid fa-newspaper"></i></div>`;
        const catPill = cats[0]
            ? `<span class="news-cat-pill">${decodeEntities(cats[0].name)}</span>`
            : '';
        return `
        <div class="news-card" data-id="${p.id}">
            ${thumb}
            <div class="news-body">
                <div class="news-title">${highlight(title, qForHl)}</div>
                <div class="news-meta">
                    ${catPill}
                    <span class="news-date"><i class="fa-regular fa-calendar" style="margin-right:3px;"></i>${fmtNewsDate(p.date)}</span>
                </div>
                <div class="news-excerpt">${highlight(trimmedExcerpt, qForHl)}</div>
            </div>
        </div>`;
    }).join('');

    const loadMoreHtml = newsHasMore
        ? `<div class="load-more-row">
               <button class="load-more-btn">
                   <i class="fa-solid fa-circle-down"></i>Load more articles
               </button>
           </div>`
        : '';

    list.innerHTML = cardsHtml + loadMoreHtml;

    list.querySelectorAll('.news-card').forEach(card => {
        card.addEventListener('click', () => openNewsDetail(parseInt(card.dataset.id, 10)));
        if (newsActiveId && parseInt(card.dataset.id, 10) === newsActiveId) {
            card.classList.add('active');
        }
    });
    const moreBtn = list.querySelector('.load-more-btn');
    if (moreBtn) moreBtn.addEventListener('click', loadMoreNews);

    lazyLoadThumbs(list);
}

let _thumbObserver = null;
function lazyLoadThumbs(scope) {
    const targets = scope.querySelectorAll('.news-thumb[data-bg]');
    if (!targets.length) return;
    if (!('IntersectionObserver' in window)) {
        targets.forEach(el => {
            el.style.backgroundImage = `url('${el.dataset.bg}')`;
            el.removeAttribute('data-bg');
        });
        return;
    }
    if (!_thumbObserver) {
        _thumbObserver = new IntersectionObserver(entries => {
            entries.forEach(entry => {
                if (!entry.isIntersecting) return;
                const el = entry.target;
                if (el.dataset.bg) {
                    el.style.backgroundImage = `url('${el.dataset.bg}')`;
                    el.removeAttribute('data-bg');
                }
                _thumbObserver.unobserve(el);
            });
        }, { rootMargin: '200px' });
    }
    targets.forEach(el => _thumbObserver.observe(el));
}

function openNewsDetail(id) {
    const post = newsData.find(p => p.id === id);
    if (!post) return;
    newsActiveId = id;
    document.querySelectorAll('.news-card').forEach(c => c.classList.remove('active'));
    const card = document.querySelector(`.news-card[data-id="${id}"]`);
    if (card) { card.classList.add('active'); card.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }

    // Re-skin detail header for news context
    document.getElementById('detail-header-icon').innerHTML = '<i class="fa-solid fa-newspaper"></i>';
    document.getElementById('detail-header-title').textContent = 'Community News';
    document.getElementById('detail-header-sub').textContent = 'EsteroToday.com · Engage Estero';

    const img = getFeaturedImage(post);
    const cats = getPostCategories(post);
    const title = decodeEntities(post.title?.rendered || 'Untitled');
    const excerptHtml = post.excerpt?.rendered || '';

    const hero = img
        ? `<div class="news-detail-hero" style="background-image:url('${img}');"></div>`
        : `<div class="news-detail-hero"><i class="fa-solid fa-newspaper"></i></div>`;

    const catChips = cats.map(c =>
        `<span class="news-cat-pill">${decodeEntities(c.name)}</span>`
    ).join('');

    document.getElementById('detail-content').innerHTML = `
        ${hero}
        <div class="news-detail-title">${title}</div>
        <div class="news-detail-meta">
            ${catChips}
            <span class="news-date"><i class="fa-regular fa-calendar" style="margin-right:4px;"></i>${fmtNewsDate(post.date)}</span>
        </div>
        <div class="news-detail-body">${excerptHtml || '<p style="font-style:italic;color:#9ca3af;">No preview available — read the full article on EsteroToday.com.</p>'}</div>
        <a class="pdf-btn" href="${post.link}" target="_blank" style="background:var(--accent);">
            <i class="fa-solid fa-arrow-up-right-from-square"></i>Read Full Article on EsteroToday.com
        </a>
        <div style="margin-top:10px;text-align:center;font-size:10px;color:var(--subtle);">
            Article courtesy of <a href="https://esterotoday.com/" target="_blank" style="color:var(--accent);font-weight:600;">EsteroToday.com</a> · Engage Estero
        </div>`;

    document.getElementById('detail-panel').classList.add('open');
    document.getElementById('map-spot').style.marginLeft = '380px';
}

function setupNewsControls() {
    document.getElementById('news-cat-row').addEventListener('click', ev => {
        const btn = ev.target.closest('.filter-btn');
        if (!btn) return;
        newsActiveCat = btn.dataset.cat;
        document.querySelectorAll('#news-cat-row .filter-btn').forEach(b => {
            b.classList.toggle('inactive', b.dataset.cat !== newsActiveCat && newsActiveCat !== 'all');
        });
        if (newsActiveCat === 'all') {
            document.querySelectorAll('#news-cat-row .filter-btn').forEach(b => b.classList.remove('inactive'));
        }
        renderNews();
    });

    // Engage Estero pillar chips behave like a single-select; clicking the
    // active chip again clears the filter.
    document.getElementById('news-pillar-row').addEventListener('click', ev => {
        const btn = ev.target.closest('.filter-btn');
        if (!btn) return;
        const slug = btn.dataset.pillar;
        newsActivePillar = (newsActivePillar === slug) ? 'all' : slug;
        document.querySelectorAll('#news-pillar-row .filter-btn').forEach(b => {
            const inactive = newsActivePillar !== 'all' && b.dataset.pillar !== newsActivePillar;
            b.classList.toggle('inactive', inactive);
        });
        renderNews();
    });
}

function setView(view) {
    if (view === currentView) return;
    currentView = view;
    document.body.classList.toggle('news-view', view === 'news');
    document.body.classList.toggle('upcoming-view', view === 'upcoming');
    document.querySelectorAll('.view-tab').forEach(t => {
        const isActive = t.dataset.view === view;
        t.classList.toggle('active', isActive);
        t.setAttribute('aria-selected', isActive ? 'true' : 'false');
    });

    const search = document.getElementById('main-search');
    search.value = '';
    search.placeholder = view === 'news'
        ? 'Search community news articles…'
        : view === 'upcoming'
            ? 'Search upcoming meetings, agendas, locations…'
            : 'Search minutes, projects, locations, titles…';

    // Reset detail header to default and close panel when switching
    document.getElementById('detail-header-icon').innerHTML = '<i class="fa-solid fa-file-lines"></i>';
    document.getElementById('detail-header-title').textContent = 'Meeting Detail';
    document.getElementById('detail-header-sub').textContent = 'Village of Estero Municipal Record';
    document.getElementById('detail-panel').classList.remove('open');
    document.getElementById('map-spot').style.marginLeft = '0';

    if (view === 'news') {
        newsActiveId = null;
        upcomingActiveId = null;
        // Surface the Reports panel as soon as we enter News view. The panel
        // itself is collapsed; the network call happens when the user clicks
        // to open it (kept light so the news list paints first).
        document.getElementById('reports-panel').style.display = '';
        if (!newsLoaded) loadNews();
        else renderNews();
        // Kick off reports load opportunistically when the tab is first
        // opened so the data is warm by the time the user expands the panel.
        if (!reportsLoaded) loadReports();
    } else if (view === 'upcoming') {
        newsActiveId = null;
        upcomingActiveId = null;
        if (!upcomingLoaded) loadUpcoming();
        else renderUpcoming();
    } else {
        newsActiveId = null;
        upcomingActiveId = null;
        run();
    }
}

function setupViewTabs() {
    document.querySelectorAll('.view-tab').forEach(tab => {
        tab.addEventListener('click', () => setView(tab.dataset.view));
    });
}

// ─────────────────────────────────────────────────────────────────────────
// 4. MINUTES INDEX — canonical PDF resolver
//
// The Village of Estero publishes Council and PZDB minutes as PDFs in a
// predictable folder structure. scripts/scrape_minutes_index.py rebuilds
// app/data/minutes_index.json from estero-fl.gov so the frontend can:
//   1. Backfill rows in the legacy CSV that lack a MinutesURL.
//   2. Light up "View Minutes" on past Tribe Events API entries.
// The lookup is keyed by (body, ISO date).
// ─────────────────────────────────────────────────────────────────────────
let minutesIndex = null;
async function loadMinutesIndex() {
    if (minutesIndex) return minutesIndex;
    try {
        const sha = siteManifest?.minutes_index?.sha256 || '';
        const url = versionedUrl('app/data/minutes_index.json', sha);
        const res = await fetch(url, { cache: 'force-cache' });
        if (!res.ok) throw new Error('HTTP ' + res.status);
        minutesIndex = await res.json();
    } catch (e) {
        console.warn('minutes_index.json unavailable; PDF resolution disabled:', e);
        minutesIndex = { council: {}, pzdb: {} };
    }
    // The CSV load and the manifest race; whichever finishes second needs to
    // trigger a re-render so backfilled PDFs become visible.
    if (allData && allData.length) {
        if (currentView === 'meetings') run();
        else if (currentView === 'upcoming' && upcomingLoaded) renderUpcoming();
    }
    return minutesIndex;
}

function meetingBodyKey(meetingType) {
    const t = (meetingType || '').toLowerCase();
    if (t.startsWith('pzdb') || t.includes('planning, zoning') || t.includes('planning zoning')) return 'pzdb';
    return 'council';
}

function resolveMinutesPdf(meetingType, isoDate) {
    if (!minutesIndex || !isoDate) return null;
    const key = meetingBodyKey(meetingType);
    return (minutesIndex[key] && minutesIndex[key][isoDate]) || null;
}

// ─────────────────────────────────────────────────────────────────────────
// 5. REPORTS & GOVERNING DOCS PANEL (Engage Estero)
//
// Pulls the /reports/ page from esterotoday.com via the WP REST API and
// regex-extracts the annual report PDFs and governing-document links from
// the Divi page-builder HTML. The strip is hidden until the user opens it.
// ─────────────────────────────────────────────────────────────────────────
const REPORTS_API = 'https://esterotoday.com/wp-json/wp/v2/pages?slug=reports&_embed=1';
let reportsLoaded = false;
let reportsData = null;

async function loadReports() {
    if (reportsLoaded) return reportsData;
    try {
        const res = await fetchWithSessionCache(REPORTS_API, 'reports', 30 * 60 * 1000);
        const pages = res || [];
        const page = Array.isArray(pages) ? pages[0] : null;
        const raw = page && page.content && page.content.rendered || '';
        reportsData = extractReports(raw);
    } catch (e) {
        console.warn('Reports load failed:', e);
        reportsData = { annual: [], governing: [] };
    }
    reportsLoaded = true;
    renderReportsPanel();
    return reportsData;
}

function extractReports(html) {
    const out = { annual: [], governing: [] };
    if (!html) return out;
    // Annual reports come from Divi `et_pb_blurb` modules whose title says
    // "YYYY Annual Report" and whose url/image attributes point at PDFs and
    // cover thumbnails.
    const blurbRe = /title=["']([^"']*Annual Report[^"']*)["'][^\]]*url=["']([^"']+\.pdf[^"']*)["'][^\]]*image=["']([^"']+)["']/gi;
    const seenUrls = new Set();
    let m;
    while ((m = blurbRe.exec(html)) !== null) {
        const url = m[2];
        if (seenUrls.has(url)) continue;
        seenUrls.add(url);
        const yearMatch = m[1].match(/(20\d{2})/);
        out.annual.push({
            year: yearMatch ? yearMatch[1] : m[1],
            label: m[1].trim(),
            url,
            cover: m[3],
        });
    }
    // Also catch annual-report PDFs that aren't wrapped in a blurb shortcode.
    const fallbackRe = /https:\/\/esterotoday\.com\/wp-content\/uploads\/\d{4}\/\d{2}\/[^"']*Annual[^"']*\.pdf/gi;
    while ((m = fallbackRe.exec(html)) !== null) {
        if (!seenUrls.has(m[0])) {
            seenUrls.add(m[0]);
            const ym = m[0].match(/(20\d{2})/);
            out.annual.push({ year: ym ? ym[1] : '', label: 'Annual Report', url: m[0], cover: null });
        }
    }
    out.annual.sort((a, b) => (b.year || '').localeCompare(a.year || ''));

    // Governing documents: Bylaws, Articles of Incorporation, Fictitious Name.
    const knownDocs = [
        { needle: 'bylaws', label: 'Bylaws', icon: 'fa-file-contract' },
        { needle: 'articles of incorporation', label: 'Articles of Incorporation', icon: 'fa-scroll' },
        { needle: 'fictitious', label: 'Fictitious Name Registration', icon: 'fa-id-card' },
        { needle: 'ficticious', label: 'Fictitious Name Registration', icon: 'fa-id-card' },
    ];
    const seenDocs = new Set();
    knownDocs.forEach(doc => {
        const re = new RegExp(
            'href=["\\\']([^"\\\']*' + doc.needle + '[^"\\\']*\\.pdf[^"\\\']*)["\\\']',
            'i'
        );
        const dm = html.match(re);
        if (dm && !seenDocs.has(doc.label)) {
            seenDocs.add(doc.label);
            out.governing.push({ label: doc.label, url: dm[1], icon: doc.icon });
        }
    });
    return out;
}

function renderReportsPanel() {
    const panel = document.getElementById('reports-panel');
    if (!panel || !reportsData) return;
    const { annual, governing } = reportsData;
    if (!annual.length && !governing.length) {
        // Keep collapsed and don't override the body-class display rule.
        panel.dataset.empty = '1';
        return;
    }
    delete panel.dataset.empty;
    const annualHtml = annual.map(r => `
        <a class="report-card" href="${r.url}" target="_blank" rel="noopener" title="${r.label}">
            ${r.cover
                ? `<div class="report-cover" style="background-image:url('${r.cover}');"></div>`
                : `<div class="report-cover"><i class="fa-solid fa-file-pdf"></i></div>`}
            <div class="report-year">${r.year || '—'}</div>
            <div class="report-label">Annual Report</div>
        </a>
    `).join('');
    const govHtml = governing.length
        ? `<ul class="governing-list">${governing.map(g => `
            <li><a href="${g.url}" target="_blank" rel="noopener">
                <i class="fa-solid ${g.icon}"></i> ${g.label}
            </a></li>
          `).join('')}</ul>`
        : '';
    document.getElementById('reports-strip').innerHTML = annualHtml;
    document.getElementById('reports-governing').innerHTML = govHtml;
    // Allow the body-class rule to control visibility; only news-view shows it.
    panel.style.display = '';
}

function setupReportsPanel() {
    const panel = document.getElementById('reports-panel');
    if (!panel) return;
    panel.querySelector('.reports-head').addEventListener('click', () => {
        panel.classList.toggle('open');
        if (panel.classList.contains('open') && !reportsLoaded) loadReports();
    });
}

// ─────────────────────────────────────────────────────────────────────────
// 6. UPCOMING MEETINGS TAB (Tribe Events API on estero-fl.gov)
//
// The Village of Estero publishes its meeting calendar via The Events
// Calendar (Tribe) plugin. The endpoint is open-CORS and returns a rich
// JSON object per event (title, start/end ISO timestamps, categories,
// description, venue with optional geo coords). We fetch a sliding window
// of "recent past + near future" so users can see what just happened and
// what's coming up.
// ─────────────────────────────────────────────────────────────────────────
const UPCOMING_API_BASE = 'https://estero-fl.gov/wp-json/tribe/events/v1/events';
let upcomingData = [];
let upcomingCats = new Map();
let upcomingActiveCat = 'all';
let upcomingRange = 'upcoming';
let upcomingLoaded = false;
let upcomingActiveId = null;

function isoDay(date) {
    return date.toISOString().slice(0, 10);
}

function buildUpcomingUrl() {
    // Pull events from 90 days ago through 180 days in the future. Tribe
    // accepts start_date/end_date in YYYY-MM-DD; pagination via per_page.
    const now = new Date();
    const back = new Date(now); back.setDate(back.getDate() - 90);
    const fwd  = new Date(now); fwd.setDate(fwd.getDate() + 180);
    const params = new URLSearchParams({
        per_page: '50',
        start_date: isoDay(back),
        end_date: isoDay(fwd),
    });
    return `${UPCOMING_API_BASE}?${params.toString()}`;
}

async function loadUpcoming() {
    const list = document.getElementById('data-list');
    list.innerHTML = `<div class="empty"><i class="fa-solid fa-spinner fa-spin"></i><p>Loading upcoming meetings from estero-fl.gov...</p></div>`;
    try {
        const data = await fetchWithSessionCache(buildUpcomingUrl(), 'upcoming', 10 * 60 * 1000);
        upcomingData = (data && data.events) || [];
        upcomingCats = new Map();
        upcomingData.forEach(ev => {
            (ev.categories || []).forEach(c => {
                const prev = upcomingCats.get(c.id) || { id: c.id, name: c.name, slug: c.slug, count: 0 };
                prev.count += 1;
                upcomingCats.set(c.id, prev);
            });
        });
        upcomingLoaded = true;
        buildUpcomingCatFilters();
        document.getElementById('tab-count-upcoming').textContent = upcomingData.length;
        renderUpcoming();
    } catch (err) {
        console.warn('Upcoming load failed:', err);
        list.innerHTML = `
            <div class="empty">
                <i class="fa-solid fa-triangle-exclamation" style="color:#ef4444;"></i>
                <p style="color:#ef4444;">Could not load upcoming meetings.<br>
                <a href="https://estero-fl.gov/meetings/" target="_blank" style="color:var(--accent);">Visit estero-fl.gov/meetings</a> directly.</p>
            </div>`;
    }
}

function buildUpcomingCatFilters() {
    const row = document.getElementById('upcoming-cat-row');
    row.querySelectorAll('[data-cat]:not([data-cat="all"])').forEach(el => el.remove());
    const allBtn = row.querySelector('[data-cat="all"]');
    const existing = allBtn.querySelector('.chip-count');
    const html = `<span class="chip-count">${upcomingData.length}</span>`;
    if (existing) existing.outerHTML = html; else allBtn.insertAdjacentHTML('beforeend', html);

    const ordered = [...upcomingCats.values()].sort((a, b) => b.count - a.count);
    ordered.forEach(c => {
        const btn = document.createElement('button');
        btn.className = 'filter-btn inactive';
        btn.dataset.cat = String(c.id);
        btn.style.cssText = 'background:#f0fdf4;color:#15803d;border-color:#86efac;';
        btn.innerHTML = `<i class="fa-solid fa-gavel"></i> ${decodeEntities(c.name)}<span class="chip-count">${c.count}</span>`;
        row.appendChild(btn);
    });
}

function filterUpcoming() {
    const q = document.getElementById('main-search').value.trim().toLowerCase();
    const todayIso = isoDay(new Date());
    return upcomingData.filter(ev => {
        if (upcomingActiveCat !== 'all') {
            const cats = (ev.categories || []).map(c => String(c.id));
            if (!cats.includes(upcomingActiveCat)) return false;
        }
        const startIso = (ev.start_date || '').slice(0, 10);
        if (upcomingRange === 'upcoming' && startIso < todayIso) return false;
        if (upcomingRange === 'past'     && startIso >= todayIso) return false;
        if (q) {
            const hay = (
                decodeEntities(ev.title || '') + ' ' +
                stripHtml(ev.description || '') + ' ' +
                (ev.categories || []).map(c => c.name).join(' ') + ' ' +
                (ev.venue && (ev.venue.venue || '') + ' ' + (ev.venue.address || ''))
            ).toLowerCase();
            if (!hay.includes(q)) return false;
        }
        return true;
    });
}

function fmtUpcomingTime(startIso) {
    if (!startIso) return '';
    const d = new Date(startIso.replace(' ', 'T'));
    if (isNaN(d)) return startIso;
    return d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
}

function dateChip(startIso) {
    const d = new Date((startIso || '').replace(' ', 'T'));
    if (isNaN(d)) return { month: '—', day: '—', year: '' };
    return {
        month: d.toLocaleDateString('en-US', { month: 'short' }),
        day:   d.toLocaleDateString('en-US', { day: 'numeric' }),
        year:  d.getFullYear().toString(),
    };
}

function renderUpcoming() {
    const list = document.getElementById('data-list');
    const filtered = filterUpcoming();
    if (!filtered.length) {
        list.innerHTML = `<div class="empty"><i class="fa-regular fa-calendar"></i><p>No meetings match your filters.<br>Try expanding the date range or category.</p></div>`;
        return;
    }
    const qForHl = document.getElementById('main-search').value.trim();
    const todayIso = isoDay(new Date());
    // Upcoming sorted ascending so the next meeting is on top; past
    // descending so the most recent is on top.
    filtered.sort((a, b) => {
        const aStart = (a.start_date || '').slice(0, 10);
        const bStart = (b.start_date || '').slice(0, 10);
        if (upcomingRange === 'past') return bStart.localeCompare(aStart);
        return aStart.localeCompare(bStart);
    });

    list.innerHTML = filtered.map(ev => {
        const startIso = (ev.start_date || '').slice(0, 10);
        const isToday = startIso === todayIso;
        const isPast = startIso < todayIso;
        const stateCls = isToday ? 'today' : isPast ? 'past' : '';
        const statusCls = isToday ? 'today' : isPast ? 'past' : 'future';
        const statusText = isToday ? 'Today' : isPast ? 'Past' : 'Upcoming';
        const chip = dateChip(ev.start_date);
        const title = decodeEntities(ev.title || 'Untitled meeting');
        const cats = (ev.categories || []).map(c => decodeEntities(c.name));
        const minutesUrl = isPast ? resolveMinutesPdf(cats.join(' '), startIso) : null;
        return `
        <div class="upcoming-card ${stateCls}" data-id="${ev.id}">
            <div class="upcoming-top">
                <div class="upcoming-date">
                    <div class="ud-month">${chip.month}</div>
                    <div class="ud-day">${chip.day}</div>
                    <div class="ud-year">${chip.year}</div>
                </div>
                <div class="upcoming-body">
                    <div class="upcoming-title">${highlight(title, qForHl)}</div>
                    <div class="upcoming-meta">
                        <span class="upcoming-status ${statusCls}">${statusText}</span>
                        <span class="upcoming-time"><i class="fa-regular fa-clock"></i>${fmtUpcomingTime(ev.start_date) || '—'}</span>
                        ${cats[0] ? `<span class="news-cat-pill">${cats[0]}</span>` : ''}
                    </div>
                    <div class="upcoming-actions">
                        <a class="btn-sm btn-outline" href="${ev.url}" target="_blank" rel="noopener" title="View on estero-fl.gov">
                            <i class="fa-solid fa-arrow-up-right-from-square"></i>Event
                        </a>
                        <button class="btn-sm btn-outline upcoming-ics" data-id="${ev.id}" title="Add to calendar (.ics)">
                            <i class="fa-regular fa-calendar-plus"></i>Calendar
                        </button>
                        ${minutesUrl
                            ? `<a class="btn-sm btn-solid" href="${minutesUrl}" target="_blank" rel="noopener" style="background:var(--accent);">
                                 <i class="fa-solid fa-file-pdf"></i>Minutes
                               </a>`
                            : ''}
                    </div>
                </div>
            </div>
        </div>`;
    }).join('');

    list.querySelectorAll('.upcoming-card').forEach(card => {
        card.addEventListener('click', e => {
            if (e.target.closest('a, button')) return;
            openUpcomingDetail(parseInt(card.dataset.id, 10));
        });
        if (upcomingActiveId && parseInt(card.dataset.id, 10) === upcomingActiveId) {
            card.classList.add('active');
        }
    });
    list.querySelectorAll('.upcoming-ics').forEach(btn => {
        btn.addEventListener('click', e => {
            e.stopPropagation();
            const ev = upcomingData.find(x => x.id === parseInt(btn.dataset.id, 10));
            if (ev) downloadIcs(ev);
        });
    });
}

function openUpcomingDetail(id) {
    const ev = upcomingData.find(e => e.id === id);
    if (!ev) return;
    upcomingActiveId = id;
    document.querySelectorAll('.upcoming-card').forEach(c => c.classList.remove('active'));
    const card = document.querySelector(`.upcoming-card[data-id="${id}"]`);
    if (card) { card.classList.add('active'); card.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }

    document.getElementById('detail-header-icon').innerHTML = '<i class="fa-regular fa-calendar"></i>';
    document.getElementById('detail-header-title').textContent = 'Upcoming Meeting';
    document.getElementById('detail-header-sub').textContent = 'estero-fl.gov · Village Calendar';

    const startIso = (ev.start_date || '').slice(0, 10);
    const todayIso = isoDay(new Date());
    const isPast = startIso < todayIso;
    const title = decodeEntities(ev.title || 'Untitled meeting');
    const cats = (ev.categories || []).map(c => decodeEntities(c.name));
    const venueName = ev.venue && (ev.venue.venue || ev.venue.address) ? decodeEntities(ev.venue.venue || ev.venue.address) : '';
    const geo = ev.venue && ev.venue.geo_lat && ev.venue.geo_lng ? `${ev.venue.geo_lat}, ${ev.venue.geo_lng}` : '';
    const descHtml = ev.description || '';
    const minutesUrl = isPast ? resolveMinutesPdf(cats.join(' '), startIso) : null;
    const chip = dateChip(ev.start_date);

    document.getElementById('detail-content').innerHTML = `
        <div class="detail-banner" style="background:var(--accent-light);border-color:var(--accent-border);">
            <div class="detail-banner-name" style="color:var(--accent);">
                <i class="fa-solid fa-gavel"></i>${title}
            </div>
            <div class="detail-banner-meta" style="color:var(--accent);margin-top:4px;">
                ${chip.month} ${chip.day}, ${chip.year} · ${fmtUpcomingTime(ev.start_date) || 'TBD'}
            </div>
            ${cats.length
                ? `<div style="margin-top:8px;display:flex;flex-wrap:wrap;gap:5px;">
                       ${cats.map(c => `<span class="news-cat-pill">${c}</span>`).join('')}
                   </div>`
                : ''}
        </div>

        <div class="detail-grid">
            ${venueName ? `
                <div class="detail-cell full">
                    <div class="dcl"><i class="fa-solid fa-location-dot"></i>Venue</div>
                    <div class="dcv" style="font-weight:500;font-size:12px;">${venueName}</div>
                    ${geo ? `<div style="font-family:'IBM Plex Mono',monospace;font-size:10px;color:#9ca3af;margin-top:3px;">${geo}</div>` : ''}
                </div>` : ''}
            <div class="detail-cell">
                <div class="dcl"><i class="fa-regular fa-clock"></i>Start</div>
                <div class="dcv" style="font-family:'IBM Plex Mono',monospace;font-size:11px;">${(ev.start_date || '—').replace('T', ' ')}</div>
            </div>
            <div class="detail-cell">
                <div class="dcl"><i class="fa-regular fa-clock"></i>End</div>
                <div class="dcv" style="font-family:'IBM Plex Mono',monospace;font-size:11px;">${(ev.end_date || '—').replace('T', ' ')}</div>
            </div>
        </div>

        ${descHtml
            ? `<div class="action-section">
                   <div class="action-header"><i class="fa-solid fa-circle-info"></i>Event Description</div>
                   <div class="action-box" style="font-size:12px;line-height:1.6;color:var(--muted);">${descHtml}</div>
               </div>`
            : ''}

        ${minutesUrl
            ? `<a class="pdf-btn" href="${minutesUrl}" target="_blank" rel="noopener" style="background:var(--accent);margin-bottom:8px;">
                   <i class="fa-solid fa-file-pdf"></i>View Approved Minutes PDF
               </a>`
            : ''}
        <a class="pdf-btn" href="${ev.url}" target="_blank" rel="noopener" style="background:var(--muted);margin-bottom:8px;">
            <i class="fa-solid fa-arrow-up-right-from-square"></i>Open on estero-fl.gov
        </a>
        <button class="pdf-btn" id="detail-ics" style="background:var(--surface2);color:var(--accent);border:1px solid var(--accent-border);">
            <i class="fa-regular fa-calendar-plus"></i>Add to Calendar (.ics)
        </button>
        <div style="margin-top:10px;text-align:center;font-size:10px;color:var(--subtle);">
            Live from <a href="https://estero-fl.gov/meetings/" target="_blank" style="color:var(--accent);font-weight:600;">estero-fl.gov</a> · Tribe Events API
        </div>`;

    const icsBtn = document.getElementById('detail-ics');
    if (icsBtn) icsBtn.addEventListener('click', () => downloadIcs(ev));

    document.getElementById('detail-panel').classList.add('open');
    document.getElementById('map-spot').style.marginLeft = '380px';
}

/**
 * Generate and download a minimal RFC 5545 .ics file for a Tribe event.
 * Tribe gives us local timestamps in the Village's timezone; we emit them
 * as floating times (no TZID) which Apple/Google/Outlook all accept.
 */
function downloadIcs(ev) {
    const fmt = s => (s || '').replace(/[-:T ]/g, '').slice(0, 15);
    const uid = `tribe-${ev.id}@estero-fl.gov`;
    const dt  = new Date().toISOString().replace(/[-:.]/g, '').slice(0, 15) + 'Z';
    const lines = [
        'BEGIN:VCALENDAR',
        'VERSION:2.0',
        'PRODID:-//EagleGIS//Village of Estero Upcoming//EN',
        'BEGIN:VEVENT',
        `UID:${uid}`,
        `DTSTAMP:${dt}`,
        `DTSTART:${fmt(ev.start_date)}`,
        `DTEND:${fmt(ev.end_date || ev.start_date)}`,
        `SUMMARY:${decodeEntities(ev.title || 'Village Meeting').replace(/[\r\n,;]/g, ' ')}`,
        `URL:${ev.url || ''}`,
        ev.venue && ev.venue.venue ? `LOCATION:${decodeEntities(ev.venue.venue)}` : '',
        'END:VEVENT',
        'END:VCALENDAR',
    ].filter(Boolean);
    const blob = new Blob([lines.join('\r\n')], { type: 'text/calendar' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `estero-meeting-${ev.id}.ics`;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

function setupUpcomingControls() {
    document.getElementById('upcoming-cat-row').addEventListener('click', ev => {
        const btn = ev.target.closest('.filter-btn');
        if (!btn) return;
        upcomingActiveCat = btn.dataset.cat;
        document.querySelectorAll('#upcoming-cat-row .filter-btn').forEach(b => {
            const inactive = upcomingActiveCat !== 'all' && b.dataset.cat !== upcomingActiveCat;
            b.classList.toggle('inactive', inactive);
        });
        renderUpcoming();
    });
    document.getElementById('upcoming-range-row').addEventListener('click', ev => {
        const btn = ev.target.closest('.upcoming-range');
        if (!btn) return;
        upcomingRange = btn.dataset.range;
        document.querySelectorAll('#upcoming-range-row .upcoming-range').forEach(b => {
            b.classList.toggle('inactive', b.dataset.range !== upcomingRange);
        });
        renderUpcoming();
    });
}

// ─────────────────────────────────────────────────────────────────────────
// SessionStorage cache helper used by News, Upcoming, and Reports loaders.
// Cuts repeat round-trips during a session, with a per-key TTL.
// ─────────────────────────────────────────────────────────────────────────
async function fetchWithSessionCache(url, key, ttlMs) {
    const cacheKey = `eaglegis:${key}:${url}`;
    try {
        const cached = sessionStorage.getItem(cacheKey);
        if (cached) {
            const { ts, data } = JSON.parse(cached);
            if (Date.now() - ts < ttlMs) return data;
        }
    } catch (e) { /* sessionStorage may be unavailable; fall through */ }
    const res = await fetch(url, { mode: 'cors' });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const data = await res.json();
    try {
        sessionStorage.setItem(cacheKey, JSON.stringify({ ts: Date.now(), data }));
    } catch (e) { /* quota exceeded — ignore */ }
    return data;
}

// ─────────────────────────────────────────────────────────────────────────
// 7. STARTUP — wire up the UI and load the data. Runs once per page load.
// ─────────────────────────────────────────────────────────────────────────
setupViewTabs();
setupNewsControls();
setupUpcomingControls();
setupReportsPanel();

// Fallback: ensure the map loads even if CSV parsing is slow or idle never fires.
window.addEventListener('load', () => {
    if (!document.getElementById('map-iframe')?.dataset.loaded) {
        scheduleIdle(loadDeferredMap, 800);
    }
});

init();
