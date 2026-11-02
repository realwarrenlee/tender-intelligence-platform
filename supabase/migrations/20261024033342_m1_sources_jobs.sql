ALTER TABLE m1_app.document_versions
    ADD COLUMN content_type text,
    ADD COLUMN byte_size bigint NOT NULL DEFAULT 0 CHECK(byte_size >= 0),
    ADD COLUMN page_count integer NOT NULL DEFAULT 0 CHECK(page_count >= 0),
    ADD COLUMN amends_version_id uuid,
    ADD CONSTRAINT amended_source_in_workspace FOREIGN KEY(workspace_id,amends_version_id)
        REFERENCES m1_app.document_versions(workspace_id,id);

ALTER TABLE m1_app.artifact_versions DROP CONSTRAINT artifact_versions_kind_check;
ALTER TABLE m1_app.artifact_versions ADD CONSTRAINT artifact_versions_kind_check
    CHECK(kind IN ('source_set','company_evidence','review_answer','assessment','parsed_sources'));

ALTER TABLE m1_app.jobs
    ADD COLUMN completed_stages jsonb NOT NULL DEFAULT '[]',
    ADD COLUMN warnings jsonb NOT NULL DEFAULT '[]',
    ADD COLUMN error_code text,
    ADD COLUMN output_version_id uuid,
    ADD COLUMN created_by uuid,
    ADD COLUMN deadline_at timestamptz,
    ADD CONSTRAINT job_output_in_workspace FOREIGN KEY(workspace_id,output_version_id)
        REFERENCES m1_app.artifact_versions(workspace_id,id);

CREATE TABLE m1_app.job_attempt_events (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    job_id uuid NOT NULL REFERENCES m1_app.jobs(id) ON DELETE CASCADE,
    attempt integer NOT NULL,
    event text NOT NULL CHECK(event IN ('started','finished','retry')),
    error_code text,
    created_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE m1_app.job_attempt_events ENABLE ROW LEVEL SECURITY;
CREATE TRIGGER immutable_job_attempt BEFORE UPDATE ON m1_app.job_attempt_events
    FOR EACH ROW EXECUTE FUNCTION m1_app.reject_version_update();
REVOKE ALL ON m1_app.job_attempt_events FROM PUBLIC,anon,authenticated;
REVOKE ALL ON SEQUENCE m1_app.job_attempt_events_id_seq FROM PUBLIC,anon,authenticated;
