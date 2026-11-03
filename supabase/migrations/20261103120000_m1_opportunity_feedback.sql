CREATE TABLE m1_app.opportunity_feedback (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL,
    suggestion_id uuid NOT NULL,
    notice_version_id uuid NOT NULL,
    sender_id uuid NOT NULL,
    recipient_id uuid NOT NULL CHECK(recipient_id <> sender_id),
    question text NOT NULL CHECK(length(question) BETWEEN 1 AND 1000),
    answer text CHECK(length(answer) BETWEEN 1 AND 2000),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    answered_at timestamptz,
    CHECK((answer IS NULL) = (answered_at IS NULL)),
    FOREIGN KEY(workspace_id,suggestion_id,notice_version_id)
      REFERENCES m1_app.notice_versions(workspace_id,suggestion_id,id) ON DELETE CASCADE
);
CREATE INDEX opportunity_feedback_sender ON m1_app.opportunity_feedback(workspace_id,sender_id,created_at DESC,id DESC);
CREATE INDEX opportunity_feedback_recipient ON m1_app.opportunity_feedback(workspace_id,recipient_id,created_at DESC,id DESC);
ALTER TABLE m1_app.opportunity_feedback ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON m1_app.opportunity_feedback FROM PUBLIC,anon,authenticated;

CREATE TABLE m1_app.opportunity_discovery_preferences (
    workspace_id uuid PRIMARY KEY REFERENCES m1_app.workspaces(id) ON DELETE CASCADE,
    enabled boolean NOT NULL,
    updated_by uuid NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
ALTER TABLE m1_app.opportunity_discovery_preferences ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON m1_app.opportunity_discovery_preferences FROM PUBLIC,anon,authenticated;
