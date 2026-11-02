-- Application records are private; browser clients use the authenticated API.
CREATE TABLE m1_app.workspaces (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL CHECK(length(name) BETWEEN 1 AND 300),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE m1_app.memberships (
    workspace_id uuid NOT NULL REFERENCES m1_app.workspaces(id) ON DELETE CASCADE,
    user_id uuid NOT NULL,
    roles text[] NOT NULL CHECK(cardinality(roles)>0 AND roles <@ ARRAY['bid_owner','service_reviewer','approver','admin','viewer']::text[]),
    PRIMARY KEY(workspace_id,user_id)
);

CREATE INDEX membership_user ON m1_app.memberships(user_id);

CREATE TABLE m1_app.tenders (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL REFERENCES m1_app.workspaces(id) ON DELETE CASCADE,
    title text NOT NULL CHECK(length(title) BETWEEN 1 AND 300),
    source_label text NOT NULL,
    owner_user_id uuid NOT NULL,
    input_revision integer NOT NULL DEFAULT 1 CHECK(input_revision>=1),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(workspace_id,id)
);

CREATE TABLE m1_app.document_versions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL,
    tender_id uuid NOT NULL,
    filename text NOT NULL,
    sha256 text NOT NULL CHECK(sha256 ~ '^[0-9a-f]{64}$'),
    storage_key text NOT NULL,
    role text NOT NULL CHECK(role IN ('tender','addendum','company_evidence','reference_note')),
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY(workspace_id,tender_id) REFERENCES m1_app.tenders(workspace_id,id) ON DELETE CASCADE,
    UNIQUE(workspace_id,id)
);

CREATE TABLE m1_app.artifact_versions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL REFERENCES m1_app.workspaces(id) ON DELETE CASCADE,
    tender_id uuid,
    kind text NOT NULL CHECK(kind IN ('source_set','company_evidence','review_answer','assessment')),
    input_revision integer,
    manifest jsonb NOT NULL,
    payload jsonb NOT NULL,
    created_by uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY(workspace_id,tender_id) REFERENCES m1_app.tenders(workspace_id,id) ON DELETE CASCADE,
    UNIQUE(workspace_id,id)
);

CREATE TABLE m1_app.review_tasks (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL,
    tender_id uuid NOT NULL,
    assessment_version_id uuid NOT NULL,
    requirement_ref text NOT NULL,
    assignee_id uuid NOT NULL,
    question text NOT NULL,
    status text NOT NULL CHECK(status IN ('open','answered','cancelled')),
    revision integer NOT NULL DEFAULT 1,
    due_at timestamptz NOT NULL,
    FOREIGN KEY(workspace_id,tender_id) REFERENCES m1_app.tenders(workspace_id,id) ON DELETE CASCADE,
    FOREIGN KEY(workspace_id,assessment_version_id) REFERENCES m1_app.artifact_versions(workspace_id,id),
    UNIQUE(workspace_id,id)
);

CREATE TABLE m1_app.review_answers (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL,
    task_id uuid NOT NULL,
    evidence_version_id uuid NOT NULL,
    actor_id uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY(workspace_id,task_id) REFERENCES m1_app.review_tasks(workspace_id,id) ON DELETE CASCADE,
    FOREIGN KEY(workspace_id,evidence_version_id) REFERENCES m1_app.artifact_versions(workspace_id,id)
);

CREATE TABLE m1_app.decisions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL,
    tender_id uuid NOT NULL,
    assessment_version_id uuid NOT NULL,
    input_revision integer NOT NULL,
    manifest jsonb NOT NULL,
    decision text NOT NULL CHECK(decision IN ('pursue','hold','decline')),
    reason text NOT NULL,
    review_complete boolean NOT NULL,
    actor_id uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY(workspace_id,tender_id) REFERENCES m1_app.tenders(workspace_id,id) ON DELETE CASCADE,
    FOREIGN KEY(workspace_id,assessment_version_id) REFERENCES m1_app.artifact_versions(workspace_id,id)
);

CREATE TABLE m1_app.jobs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL,
    tender_id uuid NOT NULL,
    input_revision integer NOT NULL,
    manifest jsonb NOT NULL,
    status text NOT NULL CHECK(status IN ('queued','running','needs_input','failed','completed','cancelled','non_current')),
    attempt integer NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY(workspace_id,tender_id) REFERENCES m1_app.tenders(workspace_id,id) ON DELETE CASCADE
);

CREATE TABLE m1_app.command_requests (
    workspace_id uuid NOT NULL REFERENCES m1_app.workspaces(id) ON DELETE CASCADE,
    user_id uuid NOT NULL,
    request_id text NOT NULL,
    request_hash text NOT NULL,
    response jsonb,
    PRIMARY KEY(workspace_id,user_id,request_id)
);

CREATE TABLE m1_app.audit_events (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    workspace_id uuid NOT NULL REFERENCES m1_app.workspaces(id) ON DELETE CASCADE,
    user_id uuid NOT NULL,
    action text NOT NULL,
    details jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE FUNCTION m1_app.reject_version_update() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Historical versions are immutable; insert a new version';
END;
$$;
REVOKE ALL ON FUNCTION m1_app.reject_version_update() FROM PUBLIC;

CREATE TRIGGER immutable_document BEFORE UPDATE ON m1_app.document_versions
FOR EACH ROW EXECUTE FUNCTION m1_app.reject_version_update();
CREATE TRIGGER immutable_artifact BEFORE UPDATE ON m1_app.artifact_versions
FOR EACH ROW EXECUTE FUNCTION m1_app.reject_version_update();
CREATE TRIGGER immutable_answer BEFORE UPDATE ON m1_app.review_answers
FOR EACH ROW EXECUTE FUNCTION m1_app.reject_version_update();
CREATE TRIGGER immutable_decision BEFORE UPDATE ON m1_app.decisions
FOR EACH ROW EXECUTE FUNCTION m1_app.reject_version_update();
CREATE TRIGGER immutable_audit BEFORE UPDATE ON m1_app.audit_events
FOR EACH ROW EXECUTE FUNCTION m1_app.reject_version_update();

DO $$ DECLARE item record; BEGIN
    FOR item IN SELECT tablename FROM pg_tables WHERE schemaname='m1_app' LOOP
        EXECUTE format('ALTER TABLE m1_app.%I ENABLE ROW LEVEL SECURITY',item.tablename);
    END LOOP;
END $$;

REVOKE ALL ON SCHEMA m1_app FROM PUBLIC,anon,authenticated;
REVOKE ALL ON ALL TABLES IN SCHEMA m1_app FROM PUBLIC,anon,authenticated;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA m1_app FROM PUBLIC,anon,authenticated;
