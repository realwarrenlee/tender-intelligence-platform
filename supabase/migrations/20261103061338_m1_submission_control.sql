ALTER TABLE m1_app.preparation_reviews
 ADD COLUMN requirements_checked boolean NOT NULL DEFAULT false;

CREATE TABLE m1_app.submission_packages (
 workspace_id uuid NOT NULL,
 tender_id uuid NOT NULL,
 id uuid NOT NULL DEFAULT gen_random_uuid(),
 version integer NOT NULL CHECK(version > 0),
 preparation_approval_id uuid NOT NULL,
 approver_id uuid NOT NULL,
 sealed_by uuid NOT NULL CHECK(sealed_by <> approver_id),
 closing_at timestamptz NOT NULL,
 snapshot text NOT NULL,
 files jsonb NOT NULL,
 sealed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(workspace_id,id),
 UNIQUE(workspace_id,tender_id,version),
 FOREIGN KEY(workspace_id,tender_id) REFERENCES m1_app.tenders(workspace_id,id) ON DELETE CASCADE,
 FOREIGN KEY(workspace_id,preparation_approval_id) REFERENCES m1_app.preparation_decisions(workspace_id,id)
);

CREATE TABLE m1_app.submission_decisions (
 workspace_id uuid NOT NULL,
 package_id uuid NOT NULL,
 outcome text NOT NULL CHECK(outcome IN ('approved','rejected')),
 actor_id uuid NOT NULL,
 note text NOT NULL,
 decided_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(workspace_id,package_id),
 UNIQUE(workspace_id,package_id,outcome),
 FOREIGN KEY(workspace_id,package_id) REFERENCES m1_app.submission_packages(workspace_id,id) ON DELETE CASCADE
);

CREATE TABLE m1_app.submission_receipts (
 workspace_id uuid NOT NULL,
 package_id uuid NOT NULL,
 decision_outcome text NOT NULL DEFAULT 'approved' CHECK(decision_outcome='approved'),
 portal_reference text NOT NULL,
 submitted_at timestamptz NOT NULL,
 recorded_by uuid NOT NULL,
 recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 filename text NOT NULL,
 sha256 text NOT NULL,
 storage_key text NOT NULL,
 PRIMARY KEY(workspace_id,package_id),
 FOREIGN KEY(workspace_id,package_id,decision_outcome)
   REFERENCES m1_app.submission_decisions(workspace_id,package_id,outcome) ON DELETE CASCADE
);

ALTER TABLE m1_app.submission_packages ENABLE ROW LEVEL SECURITY;
ALTER TABLE m1_app.submission_decisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE m1_app.submission_receipts ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON m1_app.submission_packages,m1_app.submission_decisions,m1_app.submission_receipts FROM PUBLIC,anon,authenticated;

CREATE TRIGGER immutable_submission_package BEFORE UPDATE ON m1_app.submission_packages
FOR EACH ROW EXECUTE FUNCTION m1_app.reject_version_update();
CREATE TRIGGER immutable_submission_decision BEFORE UPDATE ON m1_app.submission_decisions
FOR EACH ROW EXECUTE FUNCTION m1_app.reject_version_update();
CREATE TRIGGER immutable_submission_receipt BEFORE UPDATE ON m1_app.submission_receipts
FOR EACH ROW EXECUTE FUNCTION m1_app.reject_version_update();
