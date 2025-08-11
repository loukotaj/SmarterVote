"""
Database schema for SmarterVote race publishing.

This script creates the necessary tables for storing published race data
in PostgreSQL for enhanced querying and analytics.
"""

CREATE_TABLES_SQL = """
-- Races table for storing complete race data
CREATE TABLE IF NOT EXISTS races (
    id VARCHAR(255) PRIMARY KEY,
    data JSONB NOT NULL,
    updated_utc TIMESTAMP WITH TIME ZONE NOT NULL,
    title VARCHAR(500),
    office VARCHAR(200),
    jurisdiction VARCHAR(200),
    election_date DATE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT races_id_check CHECK (length(id) > 0)
);

-- Candidates table for normalized candidate data
CREATE TABLE IF NOT EXISTS candidates (
    id SERIAL PRIMARY KEY,
    race_id VARCHAR(255) NOT NULL REFERENCES races(id) ON DELETE CASCADE,
    name VARCHAR(300) NOT NULL,
    party VARCHAR(100),
    incumbent BOOLEAN DEFAULT FALSE,
    summary TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT candidates_race_name_unique UNIQUE(race_id, name),
    CONSTRAINT candidates_name_check CHECK (length(name) > 0)
);

-- Issue stances table for detailed policy positions
CREATE TABLE IF NOT EXISTS issue_stances (
    id SERIAL PRIMARY KEY,
    candidate_id INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
    issue VARCHAR(100) NOT NULL,
    stance TEXT NOT NULL,
    confidence VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT issue_stances_candidate_issue_unique UNIQUE(candidate_id, issue)
);

-- Publication history for audit trails
CREATE TABLE IF NOT EXISTS publication_history (
    id SERIAL PRIMARY KEY,
    race_id VARCHAR(255) NOT NULL,
    target VARCHAR(100) NOT NULL,
    success BOOLEAN NOT NULL,
    message TEXT,
    metadata JSONB,
    published_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    INDEX publication_history_race_idx (race_id),
    INDEX publication_history_target_idx (target),
    INDEX publication_history_published_idx (published_at)
);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS races_election_date_idx ON races(election_date);
CREATE INDEX IF NOT EXISTS races_office_idx ON races(office);
CREATE INDEX IF NOT EXISTS races_jurisdiction_idx ON races(jurisdiction);
CREATE INDEX IF NOT EXISTS races_updated_utc_idx ON races(updated_utc);
CREATE INDEX IF NOT EXISTS races_data_gin_idx ON races USING GIN(data);

CREATE INDEX IF NOT EXISTS candidates_race_id_idx ON candidates(race_id);
CREATE INDEX IF NOT EXISTS candidates_party_idx ON candidates(party);
CREATE INDEX IF NOT EXISTS candidates_incumbent_idx ON candidates(incumbent);

CREATE INDEX IF NOT EXISTS issue_stances_candidate_id_idx ON issue_stances(candidate_id);
CREATE INDEX IF NOT EXISTS issue_stances_issue_idx ON issue_stances(issue);
CREATE INDEX IF NOT EXISTS issue_stances_confidence_idx ON issue_stances(confidence);

-- Create a function to automatically update the updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger for candidates table
DROP TRIGGER IF EXISTS update_candidates_updated_at ON candidates;
CREATE TRIGGER update_candidates_updated_at
    BEFORE UPDATE ON candidates
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Grant appropriate permissions (adjust as needed for your setup)
-- GRANT SELECT, INSERT, UPDATE, DELETE ON races TO smartervote_app;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON candidates TO smartervote_app;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON issue_stances TO smartervote_app;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON publication_history TO smartervote_app;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO smartervote_app;
"""


async def create_database_schema(database_url: str) -> None:
    """
    Create the database schema for race publishing.

    Args:
        database_url: PostgreSQL connection URL
    """
    import asyncpg

    conn = await asyncpg.connect(database_url)

    try:
        # Execute schema creation
        await conn.execute(CREATE_TABLES_SQL)
        print("Database schema created successfully")

    except Exception as e:
        print(f"Error creating database schema: {e}")
        raise
    finally:
        await conn.close()


if __name__ == "__main__":
    import asyncio
    import os

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("Error: DATABASE_URL environment variable not set")
        exit(1)

    asyncio.run(create_database_schema(database_url))
