CREATE TABLE m1_app.assistant_runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL,
    tender_id uuid NOT NULL,
    assessment_version_id uuid NOT NULL,
    actor_id uuid NOT NULL,
    status text NOT NULL CHECK(status IN ('running','completed','failed')),
    calls jsonb NOT NULL DEFAULT '[]',
    response jsonb,
    error_code text,
    created_at timestamptz NOT NULL DEFAULT now(),
    deadline_at timestamptz NOT NULL DEFAULT now()+interval '360 seconds',
    FOREIGN KEY(workspace_id,tender_id) REFERENCES m1_app.tenders(workspace_id,id) ON DELETE CASCADE,
    FOREIGN KEY(workspace_id,assessment_version_id) REFERENCES m1_app.artifact_versions(workspace_id,id)
);
ALTER TABLE m1_app.assistant_runs ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON m1_app.assistant_runs FROM PUBLIC,anon,authenticated;
