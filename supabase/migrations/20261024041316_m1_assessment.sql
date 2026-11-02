ALTER TABLE m1_app.workspaces ADD COLUMN evidence_revision integer NOT NULL DEFAULT 0;
ALTER TABLE m1_app.jobs ADD CONSTRAINT job_workspace_identity UNIQUE(workspace_id,id);
CREATE TABLE m1_app.analysis_model_calls (
    workspace_id uuid NOT NULL,
    job_id uuid NOT NULL,
    sequence integer NOT NULL CHECK(sequence BETWEEN 1 AND 3),
    purpose text NOT NULL CHECK(purpose IN ('initial','repair')),
    state text NOT NULL CHECK(state IN ('reserved','completed','failed','transient_failure')),
    result jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(job_id,sequence),
    FOREIGN KEY(workspace_id,job_id) REFERENCES m1_app.jobs(workspace_id,id) ON DELETE CASCADE
);
ALTER TABLE m1_app.analysis_model_calls ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON m1_app.analysis_model_calls FROM PUBLIC,anon,authenticated;
