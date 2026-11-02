-- Private notice evidence and personal opportunity triage; no budget/role authority is seeded.
CREATE TABLE m1_app.opportunity_suggestions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL REFERENCES m1_app.workspaces(id) ON DELETE CASCADE,
    source_identity text NOT NULL CHECK(length(source_identity) BETWEEN 1 AND 200),
    intake_owner_user_id uuid NOT NULL,
    current_notice_version_id uuid,
    revision integer NOT NULL DEFAULT 1 CHECK(revision > 0),
    state text NOT NULL DEFAULT 'suggested' CHECK(state IN ('suggested','deferred','dismissed','activated')),
    match jsonb NOT NULL,
    tender_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    last_checked_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(workspace_id,id),
    UNIQUE(workspace_id,source_identity),
    FOREIGN KEY(workspace_id,tender_id) REFERENCES m1_app.tenders(workspace_id,id) ON DELETE CASCADE,
    CHECK((state='activated') = (tender_id IS NOT NULL))
);
CREATE INDEX opportunity_owner_page ON m1_app.opportunity_suggestions(workspace_id,intake_owner_user_id,state,created_at,id);

CREATE TABLE m1_app.notice_versions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL,
    suggestion_id uuid NOT NULL,
    version integer NOT NULL CHECK(version > 0),
    content_sha256 text NOT NULL CHECK(content_sha256 ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(workspace_id,id),
    UNIQUE(workspace_id,suggestion_id,id),
    UNIQUE(suggestion_id,version),
    FOREIGN KEY(workspace_id,suggestion_id) REFERENCES m1_app.opportunity_suggestions(workspace_id,id) ON DELETE CASCADE
);
ALTER TABLE m1_app.opportunity_suggestions ADD CONSTRAINT opportunity_current_notice
    FOREIGN KEY(workspace_id,id,current_notice_version_id)
    REFERENCES m1_app.notice_versions(workspace_id,suggestion_id,id) DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE m1_app.opportunity_triage_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL,
    suggestion_id uuid NOT NULL,
    actor_id uuid NOT NULL,
    action text NOT NULL CHECK(action IN ('start_assessment','defer','dismiss')),
    revision integer NOT NULL,
    notice_version_id uuid NOT NULL,
    tender_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY(workspace_id,suggestion_id) REFERENCES m1_app.opportunity_suggestions(workspace_id,id) ON DELETE CASCADE,
    FOREIGN KEY(workspace_id,suggestion_id,notice_version_id) REFERENCES m1_app.notice_versions(workspace_id,suggestion_id,id)
);
ALTER TABLE m1_app.opportunity_suggestions ENABLE ROW LEVEL SECURITY;
ALTER TABLE m1_app.notice_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE m1_app.opportunity_triage_events ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON m1_app.opportunity_suggestions,m1_app.notice_versions,m1_app.opportunity_triage_events FROM PUBLIC,anon,authenticated;
