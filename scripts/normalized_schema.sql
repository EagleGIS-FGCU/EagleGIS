CREATE TABLE public.meeting_types (
  type_id integer PRIMARY KEY,
  type_name varchar NOT NULL UNIQUE,
  description text
);

CREATE TABLE public.locations (
  location_id integer PRIMARY KEY,
  location_name varchar NOT NULL,
  location_type varchar
    CHECK (location_type IN (
      'Meeting Venue', 'Trail', 'Road', 'Infrastructure',
      'Park', 'Development', 'Neighborhood', 'Parcel', 'General Area'
    )),
  address text,
  description text,
  latitude numeric,
  longitude numeric
);

CREATE TABLE public.meetings (
  meeting_id integer PRIMARY KEY,
  type_id integer NOT NULL REFERENCES public.meeting_types(type_id),
  meeting_date date,
  meeting_year integer CHECK (meeting_year >= 2015 AND meeting_year <= 2030),
  venue_location_id integer REFERENCES public.locations(location_id),
  venue_name varchar,
  venue_address text,
  start_time varchar,
  end_time varchar,
  status varchar NOT NULL DEFAULT 'Pending'
    CHECK (status IN ('Accepted', 'Pending', 'Rejected', 'Tabled', 'Cancelled')),
  notes text
);

CREATE TABLE public.documents (
  document_id integer PRIMARY KEY,
  meeting_id integer NOT NULL REFERENCES public.meetings(meeting_id) ON DELETE CASCADE,
  title varchar NOT NULL,
  document_type varchar
    CHECK (document_type IN (
      'Agenda', 'Staff Report', 'Resolution', 'Ordinance',
      'Minutes', 'Presentation', 'Public Notice', 'Packet'
    )),
  file_name varchar,
  file_url text,
  upload_date date,
  doc_date date,
  notes text
);

CREATE TABLE public.projects (
  project_id integer PRIMARY KEY,
  project_name varchar NOT NULL UNIQUE,
  description text,
  start_year integer CHECK (start_year >= 2015 AND start_year <= 2030),
  status varchar NOT NULL DEFAULT 'Active'
    CHECK (status IN ('Active', 'Completed', 'Pending', 'On Hold'))
);

CREATE TABLE public.agenda_categories (
  category_id integer PRIMARY KEY,
  category_name varchar NOT NULL UNIQUE,
  description text
);

CREATE TABLE public.agenda_items (
  item_id integer PRIMARY KEY,
  meeting_id integer NOT NULL REFERENCES public.meetings(meeting_id) ON DELETE CASCADE,
  category_id integer REFERENCES public.agenda_categories(category_id),
  item_order integer,
  item_title varchar,
  item_text text NOT NULL,
  action_taken text,
  action_type varchar
    CHECK (action_type IN (
      'Vote', 'Motion', 'Discussion', 'Presentation',
      'Public Comment', 'Public Hearing', 'Consent Agenda',
      'Ordinance', 'Resolution', 'Contract Approval',
      'Budget', 'Administrative', 'No Action', 'Unknown'
    )),
  vote_detected boolean NOT NULL DEFAULT false,
  vote_result varchar,
  motion_text text,
  staff_code varchar,
  needs_review boolean NOT NULL DEFAULT false,
  extraction_confidence numeric CHECK (extraction_confidence >= 0 AND extraction_confidence <= 1),
  extraction_notes text
);

CREATE TABLE public.agenda_item_projects (
  item_id integer NOT NULL REFERENCES public.agenda_items(item_id) ON DELETE CASCADE,
  project_id integer NOT NULL REFERENCES public.projects(project_id) ON DELETE CASCADE,
  PRIMARY KEY (item_id, project_id)
);

CREATE TABLE public.agenda_item_locations (
  item_id integer NOT NULL REFERENCES public.agenda_items(item_id) ON DELETE CASCADE,
  location_id integer NOT NULL REFERENCES public.locations(location_id) ON DELETE CASCADE,
  PRIMARY KEY (item_id, location_id)
);
