-- Versioned bounded screening shares existing sources, jobs and confirmed human tasks.
ALTER TABLE m1_app.artifact_versions DROP CONSTRAINT artifact_versions_kind_check;
ALTER TABLE m1_app.artifact_versions ADD CONSTRAINT artifact_versions_kind_check
 CHECK(kind IN ('source_set','company_evidence','review_answer','assessment','parsed_sources','screening'));
ALTER TABLE m1_app.jobs ADD COLUMN job_kind text NOT NULL DEFAULT 'analysis' CHECK(job_kind IN ('analysis','screening'));
CREATE UNIQUE INDEX one_active_screening_job ON m1_app.jobs(workspace_id,tender_id)
 WHERE job_kind='screening' AND status IN ('queued','running');
CREATE INDEX current_screening_version ON m1_app.artifact_versions(workspace_id,tender_id,created_at DESC,id DESC)
 WHERE kind='screening';

CREATE TABLE m1_app.preparation_decisions (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 workspace_id uuid NOT NULL,
 tender_id uuid NOT NULL,
 screening_version_id uuid NOT NULL,
 approval_task_id uuid NOT NULL,
 actor_id uuid NOT NULL,
 input_revision integer NOT NULL,
 evidence_revision integer NOT NULL,
 outcome text NOT NULL CHECK(outcome IN ('approve_preparation','request_information','decline')),
 reason text NOT NULL,
 preparation_scope text,
 preparation_budget jsonb,
 conditions jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(workspace_id,id),
 FOREIGN KEY(workspace_id,tender_id) REFERENCES m1_app.tenders(workspace_id,id) ON DELETE CASCADE,
 FOREIGN KEY(workspace_id,screening_version_id) REFERENCES m1_app.artifact_versions(workspace_id,id),
 FOREIGN KEY(workspace_id,approval_task_id) REFERENCES m1_app.review_tasks(workspace_id,id),
 UNIQUE(approval_task_id)
);
CREATE INDEX latest_preparation_decision ON m1_app.preparation_decisions(workspace_id,tender_id,created_at DESC,id DESC);
ALTER TABLE m1_app.preparation_decisions ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON m1_app.preparation_decisions FROM PUBLIC,anon,authenticated;
