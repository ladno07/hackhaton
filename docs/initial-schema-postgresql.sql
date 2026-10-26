BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 0001

CREATE TABLE competition_types (
    id SERIAL NOT NULL, 
    name VARCHAR(100) NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (name)
);

CREATE TABLE deadlines (
    id SERIAL NOT NULL, 
    title VARCHAR(240) NOT NULL, 
    due_on DATE NOT NULL, 
    done BOOLEAN NOT NULL, 
    PRIMARY KEY (id)
);

CREATE TABLE disciplines (
    id SERIAL NOT NULL, 
    name VARCHAR(150) NOT NULL, 
    short_name VARCHAR(60) NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (name)
);

CREATE TABLE organizations (
    id SERIAL NOT NULL, 
    name VARCHAR(200) NOT NULL, 
    kind VARCHAR(80) NOT NULL, 
    municipality VARCHAR(120) NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (name)
);

CREATE TABLE rating_rules (
    level VARCHAR(40) NOT NULL, 
    first INTEGER NOT NULL, 
    second INTEGER NOT NULL, 
    third INTEGER NOT NULL, 
    PRIMARY KEY (level)
);

CREATE TABLE roles (
    id VARCHAR(20) NOT NULL, 
    name VARCHAR(100) NOT NULL, 
    PRIMARY KEY (id)
);

CREATE TABLE users (
    id SERIAL NOT NULL, 
    email VARCHAR(254) NOT NULL, 
    password_hash TEXT NOT NULL, 
    full_name VARCHAR(200) NOT NULL, 
    birth_date DATE NOT NULL, 
    consent_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    consent_version VARCHAR(30) NOT NULL, 
    guardian_name VARCHAR(200), 
    guardian_consent_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id)
);

CREATE UNIQUE INDEX ix_users_email ON users (email);

CREATE TABLE athletes (
    id SERIAL NOT NULL, 
    user_id INTEGER NOT NULL, 
    organization_id INTEGER, 
    municipality VARCHAR(120) NOT NULL, 
    training_stage VARCHAR(120), 
    rusada_date DATE, 
    rusada_certificate TEXT, 
    suspended_until DATE, 
    suspension_reason TEXT, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organization_id) REFERENCES organizations (id), 
    FOREIGN KEY(user_id) REFERENCES users (id), 
    UNIQUE (user_id)
);

CREATE TABLE audit_logs (
    id SERIAL NOT NULL, 
    user_id INTEGER, 
    active_role VARCHAR(20) NOT NULL, 
    action VARCHAR(120) NOT NULL, 
    entity VARCHAR(100) NOT NULL, 
    entity_id VARCHAR(100) NOT NULL, 
    details JSON NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE TABLE coaches (
    id SERIAL NOT NULL, 
    user_id INTEGER NOT NULL, 
    organization_id INTEGER, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organization_id) REFERENCES organizations (id), 
    FOREIGN KEY(user_id) REFERENCES users (id), 
    UNIQUE (user_id)
);

CREATE TABLE competitions (
    id SERIAL NOT NULL, 
    title VARCHAR(240) NOT NULL, 
    discipline_id INTEGER NOT NULL, 
    type_id INTEGER NOT NULL, 
    start_date DATE NOT NULL, 
    end_date DATE NOT NULL, 
    deadline DATE NOT NULL, 
    location VARCHAR(200) NOT NULL, 
    format VARCHAR(20) NOT NULL, 
    level VARCHAR(40) NOT NULL, 
    min_age INTEGER NOT NULL, 
    max_age INTEGER NOT NULL, 
    calendar_plan VARCHAR(100) NOT NULL, 
    calendar_number VARCHAR(80) NOT NULL, 
    regulation_url TEXT, 
    state VARCHAR(20) NOT NULL, 
    revision INTEGER NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (format IN ('onsite','online','hybrid')), 
    CHECK (level IN ('regional','interregional','russian_championship','russian_junior')), 
    CHECK (state IN ('draft','open','closed','published')), 
    CHECK (end_date >= start_date), 
    CHECK (min_age <= max_age), 
    FOREIGN KEY(discipline_id) REFERENCES disciplines (id), 
    FOREIGN KEY(type_id) REFERENCES competition_types (id)
);

CREATE TABLE evsk_rules (
    id SERIAL NOT NULL, 
    discipline_id INTEGER NOT NULL, 
    level VARCHAR(40) NOT NULL, 
    rank_name VARCHAR(100) NOT NULL, 
    max_place INTEGER NOT NULL, 
    min_participants INTEGER NOT NULL, 
    source TEXT NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(discipline_id) REFERENCES disciplines (id)
);

CREATE TABLE judges (
    id SERIAL NOT NULL, 
    user_id INTEGER NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id), 
    UNIQUE (user_id)
);

CREATE TABLE notifications (
    id SERIAL NOT NULL, 
    user_id INTEGER NOT NULL, 
    title VARCHAR(240) NOT NULL, 
    body TEXT NOT NULL, 
    event_key VARCHAR(240) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    read_at TIMESTAMP WITH TIME ZONE, 
    mailed_at TIMESTAMP WITH TIME ZONE, 
    attempts INTEGER NOT NULL, 
    last_error TEXT, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id), 
    UNIQUE (user_id, event_key)
);

CREATE INDEX ix_notifications_user_id ON notifications (user_id);

CREATE TABLE user_roles (
    user_id INTEGER NOT NULL, 
    role_id VARCHAR(20) NOT NULL, 
    PRIMARY KEY (user_id, role_id), 
    FOREIGN KEY(role_id) REFERENCES roles (id), 
    FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE TABLE athlete_coaches (
    id SERIAL NOT NULL, 
    athlete_id INTEGER NOT NULL, 
    coach_id INTEGER NOT NULL, 
    discipline_id INTEGER NOT NULL, 
    status VARCHAR(20) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (status IN ('pending','active','paused','ended')), 
    FOREIGN KEY(athlete_id) REFERENCES athletes (id), 
    FOREIGN KEY(coach_id) REFERENCES coaches (id), 
    FOREIGN KEY(discipline_id) REFERENCES disciplines (id), 
    UNIQUE (athlete_id, coach_id, discipline_id)
);

CREATE TABLE athlete_disciplines (
    athlete_id INTEGER NOT NULL, 
    discipline_id INTEGER NOT NULL, 
    start_year INTEGER NOT NULL, 
    end_year INTEGER, 
    PRIMARY KEY (athlete_id, discipline_id), 
    CHECK (end_year IS NULL OR end_year >= start_year), 
    FOREIGN KEY(athlete_id) REFERENCES athletes (id), 
    FOREIGN KEY(discipline_id) REFERENCES disciplines (id)
);

CREATE TABLE competition_applications (
    id SERIAL NOT NULL, 
    competition_id INTEGER NOT NULL, 
    athlete_id INTEGER NOT NULL, 
    submitted_by INTEGER NOT NULL, 
    status VARCHAR(20) NOT NULL, 
    comment TEXT, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (status IN ('pending','approved','rejected')), 
    FOREIGN KEY(athlete_id) REFERENCES athletes (id), 
    FOREIGN KEY(competition_id) REFERENCES competitions (id), 
    FOREIGN KEY(submitted_by) REFERENCES users (id), 
    UNIQUE (competition_id, athlete_id)
);

CREATE TABLE competition_judges (
    competition_id INTEGER NOT NULL, 
    judge_id INTEGER NOT NULL, 
    position VARCHAR(120) NOT NULL, 
    PRIMARY KEY (competition_id, judge_id), 
    FOREIGN KEY(competition_id) REFERENCES competitions (id), 
    FOREIGN KEY(judge_id) REFERENCES judges (id)
);

CREATE TABLE competition_results (
    id SERIAL NOT NULL, 
    competition_id INTEGER NOT NULL, 
    athlete_id INTEGER NOT NULL, 
    place INTEGER NOT NULL, 
    score FLOAT NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (place > 0), 
    CHECK (score >= 0), 
    FOREIGN KEY(athlete_id) REFERENCES athletes (id), 
    FOREIGN KEY(competition_id) REFERENCES competitions (id), 
    UNIQUE (competition_id, athlete_id), 
    UNIQUE (competition_id, place)
);

CREATE TABLE judge_categories (
    id SERIAL NOT NULL, 
    judge_id INTEGER NOT NULL, 
    name VARCHAR(100) NOT NULL, 
    assigned_on DATE NOT NULL, 
    expires_on DATE NOT NULL, 
    order_number VARCHAR(120) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(judge_id) REFERENCES judges (id)
);

CREATE TABLE ratings (
    id SERIAL NOT NULL, 
    athlete_id INTEGER NOT NULL, 
    discipline_id INTEGER NOT NULL, 
    season INTEGER NOT NULL, 
    points FLOAT NOT NULL, 
    coefficient FLOAT NOT NULL, 
    breakdown JSON NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(athlete_id) REFERENCES athletes (id), 
    FOREIGN KEY(discipline_id) REFERENCES disciplines (id), 
    UNIQUE (athlete_id, discipline_id, season)
);

CREATE TABLE team_members (
    season INTEGER NOT NULL, 
    discipline_id INTEGER NOT NULL, 
    athlete_id INTEGER NOT NULL, 
    selected_by INTEGER NOT NULL, 
    PRIMARY KEY (season, discipline_id, athlete_id), 
    FOREIGN KEY(athlete_id) REFERENCES athletes (id), 
    FOREIGN KEY(discipline_id) REFERENCES disciplines (id), 
    FOREIGN KEY(selected_by) REFERENCES users (id)
);

CREATE TABLE link_history (
    id SERIAL NOT NULL, 
    link_id INTEGER NOT NULL, 
    actor_id INTEGER NOT NULL, 
    status VARCHAR(20) NOT NULL, 
    at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(actor_id) REFERENCES users (id), 
    FOREIGN KEY(link_id) REFERENCES athlete_coaches (id)
);

CREATE TABLE rank_applications (
    id SERIAL NOT NULL, 
    athlete_id INTEGER, 
    judge_id INTEGER, 
    result_id INTEGER, 
    submitted_by INTEGER NOT NULL, 
    name VARCHAR(100) NOT NULL, 
    kind VARCHAR(30) NOT NULL, 
    status VARCHAR(20) NOT NULL, 
    comment TEXT, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (status IN ('pending','approved','rejected')), 
    CHECK ((athlete_id IS NOT NULL AND judge_id IS NULL AND result_id IS NOT NULL) OR (judge_id IS NOT NULL AND athlete_id IS NULL AND result_id IS NULL)), 
    FOREIGN KEY(athlete_id) REFERENCES athletes (id), 
    FOREIGN KEY(judge_id) REFERENCES judges (id), 
    FOREIGN KEY(result_id) REFERENCES competition_results (id), 
    FOREIGN KEY(submitted_by) REFERENCES users (id)
);

CREATE TABLE sports_ranks (
    id SERIAL NOT NULL, 
    athlete_id INTEGER NOT NULL, 
    discipline_id INTEGER NOT NULL, 
    name VARCHAR(100) NOT NULL, 
    assigned_on DATE NOT NULL, 
    expires_on DATE NOT NULL, 
    order_number VARCHAR(120) NOT NULL, 
    result_id INTEGER NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(athlete_id) REFERENCES athletes (id), 
    FOREIGN KEY(discipline_id) REFERENCES disciplines (id), 
    FOREIGN KEY(result_id) REFERENCES competition_results (id)
);

INSERT INTO alembic_version (version_num) VALUES ('0001') RETURNING alembic_version.version_num;

COMMIT;

