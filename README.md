# Village of Estero Public Meetings and Legislation Database

A PostgreSQL-based relational database system for cataloging, organizing, and spatially mapping Village of Estero public meeting records. Built in partnership with Engage Estero (EsteroToday.com) to support municipal transparency and civic engagement through geospatial integration with ArcGIS StoryMaps.

Developed as part of COP 3710 - Database Systems at Florida Gulf Coast University under Dr. Vinod Ahuja.

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Team](#team)
3. [Community Partner](#community-partner)
4. [Repository Structure](#repository-structure)
5. [Database Schema](#database-schema)
6. [Getting Started](#getting-started)
7. [Web Scraper](#web-scraper)
8. [Populating the Database](#populating-the-database)
9. [Running Queries](#running-queries)
10. [ArcGIS Export](#arcgis-export)
11. [Maintenance Guide for Future Teams](#maintenance-guide-for-future-teams)
12. [Technologies Used](#technologies-used)
13. [License](#license)

---

## Project Overview

The Village of Estero, incorporated in 2014, holds regular public meetings where council members discuss zoning decisions, infrastructure projects, and community policy. These meeting records are scattered across PDFs, spreadsheets, and web pages with no centralized or searchable system.

This project addresses that gap by providing:

- A BCNF-normalized relational database hosted on Supabase (cloud PostgreSQL) that stores meeting records, associated documents, project metadata, meeting type classifications, and geographic locations.
- A Python web scraper that extracts meeting data from the Village of Estero website (estero-fl.gov).
- SQL queries for searching, filtering, and analyzing meeting history across projects.
- CSV export functionality with latitude and longitude coordinates for direct import into ArcGIS StoryMaps, enabling Estero residents to visually explore active projects, meeting locations, and council decisions on an interactive map.

### Data Pipeline

The data flows through the following stages:

1. **Source**: Village of Estero public meeting pages (estero-fl.gov)
2. **Collection**: Python web scraper extracts meeting records, dates, and document links
3. **Cleaning**: Raw data is structured, validated, and normalized
4. **Storage**: Data is loaded into five BCNF-normalized tables on Supabase PostgreSQL
5. **Output**: SQL queries for analysis and CSV exports with geospatial coordinates for ArcGIS

Some records were also entered manually by the team where web data was incomplete or unavailable. Requirements and feedback from community partner Terry Flanagan guided the database design and query development throughout the project.

---

## Team

| Name | Role |
|------|------|
| Krish Shah | Requirements Gathering, Database Architect |
| Nolan Stillwell | ArcGIS Implemnetation & Data Population |
| Ethan Malviala | Query Development and Documentation |

---

## Community Partner

**Engage Estero / EsteroToday.com**
Partner Contact: Terry Flanagan

Engage Estero is a civic organization that monitors Village of Estero governance, attends public meetings, and reports on legislative decisions through EsteroToday.com. Terry Flanagan served as the community partner for this project, providing domain expertise on meeting structures, project categories, and the types of queries most valuable for civic transparency. Terry facilitated Zoom meetings with the team to clarify database requirements and helped define how ArcGIS StoryMaps could visualize meeting data for public consumption.

---

## Repository Structure

```
estero-meetings-db/
|
|-- README.md                   # This file
|-- schema/
|   |-- create_tables.sql       # DDL statements to create all tables
|   |-- drop_tables.sql         # DDL statements to drop all tables
|   |-- seed_data.sql           # INSERT statements for initial data population
|
|-- queries/
|   |-- meeting_queries.sql     # Queries for filtering and searching meetings
|   |-- project_queries.sql     # Queries for tracking project timelines
|   |-- document_queries.sql    # Queries for document retrieval
|   |-- export_queries.sql      # Queries for ArcGIS CSV export
|
|-- scraper/
|   |-- scraper.py              # Python web scraping script
|   |-- requirements.txt        # Python dependencies
|
|-- exports/
|   |-- arcgis_export.csv       # Sample ArcGIS-ready CSV with lat/long
|
|-- diagrams/
|   |-- database_schema.png     # Relational schema diagram
|   |-- er_diagram.png          # Entity-Relationship diagram (Chen notation)
|   |-- data_pipeline.png       # Data flow pipeline diagram
|
|-- docs/
|   |-- milestone_report.docx   # Project milestone documentation
|   |-- poster.pptx             # EagleX research showcase poster
```

Note: Adjust the above structure to match your actual repository layout. This is a recommended organization.

---

## Database Schema

The database consists of five BCNF-normalized tables hosted on Supabase (cloud PostgreSQL).

### Tables

**projects**
Stores metadata about Village of Estero infrastructure and policy projects.

| Column | Type | Constraints |
|--------|------|-------------|
| project_id | int4 | PRIMARY KEY |
| project_name | varchar | NOT NULL |
| description | text | |
| status | varchar | |

**meeting_types**
Classifies meetings by type (e.g., Regular Council Meeting, Public Hearing, Workshop).

| Column | Type | Constraints |
|--------|------|-------------|
| type_id | int4 | PRIMARY KEY |
| type_name | varchar | NOT NULL |
| description | text | |

**meetings**
Central table storing individual meeting records tied to projects and meeting types.

| Column | Type | Constraints |
|--------|------|-------------|
| meeting_id | int4 | PRIMARY KEY |
| project_id | int4 | FOREIGN KEY references projects(project_id) |
| type_id | int4 | FOREIGN KEY references meeting_types(type_id) |
| meeting_date | date | NOT NULL |
| meeting_year | int4 | NOT NULL |
| location | text | |
| start_time | varchar | |
| end_time | varchar | |
| action_taken | varchar | |
| status | varchar | |
| approved_by_council_date | date | |
| doc_ref_code | varchar | |
| filename | varchar | |
| notes | text | |

**documents**
Stores meeting-related documents such as agendas, minutes, and resolutions.

| Column | Type | Constraints |
|--------|------|-------------|
| document_id | int4 | PRIMARY KEY |
| meeting_id | int4 | FOREIGN KEY references meetings(meeting_id) |
| title | varchar | NOT NULL |
| document_type | varchar | |
| file_name | varchar | |
| file_url | text | |
| upload_date | date | |
| notes | text | |
| doc_date | date | |

**locations**
Stores geographic coordinates for project locations, enabling ArcGIS integration.

| Column | Type | Constraints |
|--------|------|-------------|
| location_id | int4 | PRIMARY KEY |
| project_id | int4 | FOREIGN KEY references projects(project_id) |
| location_name | varchar | |
| location_type | varchar | |
| address | text | |
| description | text | |
| latitude | numeric | |
| longitude | numeric | |

### Relationships

- One project has many meetings (projects 1:N meetings)
- One meeting has many documents (meetings 1:N documents)
- One meeting type classifies many meetings (meeting_types 1:N meetings)
- One project has many locations (projects 1:N locations)

### ER Diagram

See `diagrams/er_diagram.png` for the full Chen notation Entity-Relationship diagram showing all entities, attributes, and relationships.

### Relational Schema Diagram

See `diagrams/database_schema.png` for the relational schema showing table structures, data types, primary keys, and foreign key connections.

---

## Getting Started

### Prerequisites

- A Supabase account (free tier works): https://supabase.com
- Python 3.8 or higher (for the web scraper)
- A SQL client such as pgAdmin, DBeaver, or the Supabase SQL Editor
- Git

### Setting Up the Database

1. Clone the repository:

```bash
git clone https://github.com/your-username/estero-meetings-db.git
cd estero-meetings-db
```

2. Create a new Supabase project at https://supabase.com/dashboard. Note your project URL and API key.

3. Open the Supabase SQL Editor (or connect via pgAdmin using your Supabase connection string) and run the DDL script to create the tables:

```bash
# In the Supabase SQL Editor, paste and execute:
schema/create_tables.sql
```

4. Populate the database with the initial seed data:

```bash
# In the Supabase SQL Editor, paste and execute:
schema/seed_data.sql
```

5. Verify the tables were created and populated:

```sql
SELECT COUNT(*) FROM projects;
SELECT COUNT(*) FROM meetings;
SELECT COUNT(*) FROM documents;
SELECT COUNT(*) FROM meeting_types;
SELECT COUNT(*) FROM locations;
```

### Connecting to Supabase

Your Supabase connection details can be found under Project Settings > Database in the Supabase dashboard. You will need:

- Host: `db.<your-project-ref>.supabase.co`
- Port: `5432`
- Database: `postgres`
- User: `postgres`
- Password: Your database password (set during project creation)

---

## Web Scraper

The Python web scraper in `scraper/scraper.py` extracts meeting records from the Village of Estero website.

### Setup

```bash
cd scraper
pip install -r requirements.txt
```

### Usage

```bash
python scraper.py
```

The scraper will output structured data that can be reviewed and then inserted into the database using the seed data scripts or direct SQL inserts.

### How It Works

1. The scraper sends HTTP requests to the Village of Estero public meeting pages on estero-fl.gov.
2. It parses the HTML response to extract meeting dates, titles, agenda links, minute links, and associated project information.
3. The extracted data is cleaned, deduplicated, and formatted to match the database schema.
4. Output is saved in a format ready for database insertion.

### Notes for Future Teams

- The Village of Estero website structure may change over time. If the scraper stops working, inspect the current HTML structure of the meeting pages and update the parsing logic accordingly.
- Always review scraped data before inserting it into the database. Some records may be incomplete or require manual correction.
- Be respectful of the website's server. Add appropriate delays between requests and avoid excessive scraping frequency.

---

## Populating the Database

### Using Seed Data

The `schema/seed_data.sql` file contains INSERT statements for the initial dataset, including records for the following Village of Estero projects:

- BERT Rail Trail
- Septic to Sewer Initiative
- Corkscrew Road Improvements

Run this file in the Supabase SQL Editor or through pgAdmin to populate the database.

### Adding New Records

To add new meeting records:

1. First ensure the associated project exists in the `projects` table. If not, insert it:

```sql
INSERT INTO projects (project_id, project_name, description, status)
VALUES (4, 'New Project Name', 'Description of the project', 'Active');
```

2. Ensure the meeting type exists in `meeting_types`. If not, insert it:

```sql
INSERT INTO meeting_types (type_id, type_name, description)
VALUES (5, 'Special Session', 'A specially called council session');
```

3. Insert the meeting record:

```sql
INSERT INTO meetings (meeting_id, project_id, type_id, meeting_date, meeting_year, location, start_time, action_taken, status)
VALUES (101, 4, 5, '2026-03-15', 2026, 'Estero Village Hall', '5:30 PM', 'Approved', 'Completed');
```

4. Insert any associated documents:

```sql
INSERT INTO documents (document_id, meeting_id, title, document_type, file_url, doc_date)
VALUES (201, 101, 'Meeting Minutes - March 15 2026', 'Minutes', 'https://estero-fl.gov/docs/minutes-031526.pdf', '2026-03-15');
```

5. If the project has a physical location, add it to the `locations` table with latitude and longitude:

```sql
INSERT INTO locations (location_id, project_id, location_name, location_type, address, latitude, longitude)
VALUES (10, 4, 'Project Site', 'Construction Zone', '123 Main St, Estero, FL', 26.4381, -81.8068);
```

---

## Running Queries

The `queries/` directory contains pre-written SQL queries organized by use case. Below are some key examples.

### Filter Meetings by Project

```sql
SELECT m.meeting_id, m.meeting_date, m.action_taken, m.status, p.project_name
FROM meetings m
JOIN projects p ON m.project_id = p.project_id
WHERE p.project_name = 'BERT Rail Trail'
ORDER BY m.meeting_date;
```

### Find Documents for a Specific Meeting

```sql
SELECT d.title, d.document_type, d.file_url, d.doc_date
FROM documents d
WHERE d.meeting_id = 1
ORDER BY d.doc_date;
```

### Track All Meetings for a Project Chronologically

```sql
SELECT m.meeting_date, mt.type_name, m.action_taken, m.status, m.notes
FROM meetings m
JOIN meeting_types mt ON m.type_id = mt.type_id
WHERE m.project_id = 1
ORDER BY m.meeting_date ASC;
```

### Find Meetings Where Council Approved Action

```sql
SELECT m.meeting_date, p.project_name, m.action_taken, m.approved_by_council_date
FROM meetings m
JOIN projects p ON m.project_id = p.project_id
WHERE m.approved_by_council_date IS NOT NULL
ORDER BY m.approved_by_council_date;
```

### Count Meetings Per Project

```sql
SELECT p.project_name, COUNT(m.meeting_id) AS total_meetings
FROM projects p
LEFT JOIN meetings m ON p.project_id = m.project_id
GROUP BY p.project_name
ORDER BY total_meetings DESC;
```

---

## ArcGIS Export

The database is designed with geospatial readiness in mind. The `locations` table stores latitude and longitude coordinates for each project location, enabling direct export to ArcGIS StoryMaps.

### Generating the CSV Export

Run the following query to generate an ArcGIS-compatible CSV:

```sql
SELECT
    p.project_name,
    p.description AS project_description,
    p.status AS project_status,
    m.meeting_date,
    m.meeting_year,
    mt.type_name AS meeting_type,
    m.action_taken,
    m.status AS meeting_status,
    l.location_name,
    l.address,
    l.latitude,
    l.longitude
FROM meetings m
JOIN projects p ON m.project_id = p.project_id
JOIN meeting_types mt ON m.type_id = mt.type_id
JOIN locations l ON p.project_id = l.project_id
ORDER BY p.project_name, m.meeting_date;
```

In the Supabase SQL Editor, run this query and download the results as CSV. In pgAdmin, you can use the "Export" option or the `\copy` command.

### Importing into ArcGIS

1. Open ArcGIS Online or ArcGIS StoryMaps.
2. Add a new layer and select "Add layer from file."
3. Upload the exported CSV file.
4. ArcGIS will automatically detect the `latitude` and `longitude` columns and plot the locations on the map.
5. Configure pop-ups to display project name, meeting date, action taken, and status for each point.

### Notes

- Ensure latitude and longitude values are in decimal degrees (WGS 84 coordinate system), which is the standard for ArcGIS.
- All coordinates in the database should reference locations within or near the Village of Estero, Florida (approximate center: 26.44 N, -81.81 W).
- If a project spans multiple locations, each location gets its own row in the `locations` table with a separate `location_id` but the same `project_id`.

---

## Maintenance Guide for Future Teams

This section is written for anyone who picks up this project in a future semester. Here is what you need to know.

### Understanding the Current State

- The database is hosted on Supabase. You will need access credentials from the previous team or from Dr. Ahuja. If credentials are unavailable, you can create a new Supabase project and re-run the DDL and seed scripts from this repository.
- The current dataset covers three major Village of Estero projects: BERT Rail Trail, Septic to Sewer, and Corkscrew Road. These were selected in collaboration with Terry Flanagan as representative examples.
- The web scraper was built to extract data from the Village of Estero website as it existed during Spring 2026. Website structures change, so the scraper may require updates.

### Expanding the Database

The most impactful next step is expanding coverage to include all Village of Estero public meeting records from 2014 (incorporation) to the present. To do this:

1. Identify all meeting types held by the Village (council meetings, planning and zoning boards, design review boards, etc.) and ensure they exist in the `meeting_types` table.
2. For each new project the Village discusses, add a row to the `projects` table.
3. Scrape or manually collect meeting records and insert them into the `meetings` and `documents` tables.
4. For projects with physical locations, geocode the addresses to get latitude and longitude and add them to the `locations` table. Google Maps or the US Census Geocoder (https://geocoding.geo.census.gov/geocoder/) can be used for this.

### Keeping the Scraper Updated

- If the Village of Estero website changes its HTML structure, the scraper will break. Open the scraper script, inspect the new page structure using your browser's developer tools, and update the CSS selectors or XPath expressions accordingly.
- Consider adding error handling and logging to make future debugging easier.
- If the website adds an API or RSS feed for meeting data, that would be a more reliable data source than HTML scraping.

### Working with Terry Flanagan and Engage Estero

- Terry Flanagan (Engage Estero / EsteroToday.com) is the community partner for this project. He can provide context on which projects are most important to track, what types of queries Estero residents would find most useful, and how the ArcGIS StoryMap should be designed for public consumption.
- Previous communication with Terry was conducted via Zoom and email. He is responsive and knowledgeable about Village governance.
- Kim Dailey was the ArcGIS contact who can assist with StoryMap configuration and best practices.

### Potential Future Enhancements

- Build an interactive web dashboard with search and filter capabilities for Engage Estero volunteers, potentially using Supabase's REST API and a frontend framework like React.
- Integrate automated PDF parsing to extract structured data from meeting agendas and minutes without manual entry.
- Add full-text search capabilities using PostgreSQL's built-in `tsvector` and `tsquery` features for searching through meeting notes and document titles.
- Set up a scheduled scraping job (e.g., using GitHub Actions or a cron job) to automatically check for new meeting records on the Village website.
- Create user roles and access controls in Supabase if multiple volunteers will be entering data.

---

## Technologies Used

| Technology | Purpose |
|------------|---------|
| PostgreSQL | Relational database engine |
| Supabase | Cloud-hosted PostgreSQL platform with dashboard and REST API |
| Python | Web scraping and data processing |
| SQL | Query development, data analysis, and export |
| ArcGIS StoryMaps | Geospatial visualization for public-facing map |
| Git / GitHub | Version control and project handoff |

---

## License

This project was developed for academic purposes as part of COP 3710 - Database Systems at Florida Gulf Coast University. It is intended for use by Engage Estero and future FGCU student teams continuing this work. Please contact the team or Dr. Vinod Ahuja for questions about usage and permissions.
