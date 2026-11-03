CREATE TABLE m1_app.preparation_items (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 workspace_id uuid NOT NULL,
 tender_id uuid NOT NULL,
 approval_id uuid NOT NULL,
 kind text NOT NULL CHECK(kind IN ('technical_response','pricing_workbook')),
 owner_id uuid NOT NULL,
 reviewer_id uuid NOT NULL CHECK(reviewer_id <> owner_id),
 due_at timestamptz NOT NULL,
 finding_ids text[] NOT NULL,
 revision integer NOT NULL DEFAULT 1,
 plan_revision integer NOT NULL DEFAULT 1,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(workspace_id,id),
 UNIQUE(workspace_id,tender_id,kind),
 FOREIGN KEY(workspace_id,tender_id) REFERENCES m1_app.tenders(workspace_id,id) ON DELETE CASCADE,
 FOREIGN KEY(workspace_id,approval_id) REFERENCES m1_app.preparation_decisions(workspace_id,id)
);

CREATE TABLE m1_app.preparation_plans (
 workspace_id uuid NOT NULL,
 item_id uuid NOT NULL,
 revision integer NOT NULL,
 approval_id uuid NOT NULL,
 owner_id uuid NOT NULL,
 reviewer_id uuid NOT NULL,
 due_at timestamptz NOT NULL,
 finding_ids text[] NOT NULL,
 actor_id uuid NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(workspace_id,item_id,revision),
 FOREIGN KEY(workspace_id,item_id) REFERENCES m1_app.preparation_items(workspace_id,id) ON DELETE CASCADE,
 FOREIGN KEY(workspace_id,approval_id) REFERENCES m1_app.preparation_decisions(workspace_id,id)
);

CREATE TABLE m1_app.preparation_files (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 workspace_id uuid NOT NULL,
 item_id uuid NOT NULL,
 version integer NOT NULL,
 filename text NOT NULL,
 content_type text NOT NULL,
 sha256 text NOT NULL,
 storage_key text NOT NULL,
 actor_id uuid NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(workspace_id,item_id,id),
 UNIQUE(workspace_id,item_id,version),
 FOREIGN KEY(workspace_id,item_id) REFERENCES m1_app.preparation_items(workspace_id,id) ON DELETE CASCADE
);

CREATE TABLE m1_app.preparation_reviews (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 workspace_id uuid NOT NULL,
 item_id uuid NOT NULL,
 file_id uuid NOT NULL,
 approval_id uuid NOT NULL,
 plan_revision integer NOT NULL,
 requested_by uuid NOT NULL,
 reviewer_id uuid NOT NULL,
 scope text NOT NULL,
 outcome text CHECK(outcome IN ('accepted','changes_requested')),
 reason text,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 reviewed_at timestamptz,
 UNIQUE(workspace_id,item_id,file_id,plan_revision),
 FOREIGN KEY(workspace_id,item_id,plan_revision) REFERENCES m1_app.preparation_plans(workspace_id,item_id,revision) ON DELETE CASCADE,
 FOREIGN KEY(workspace_id,item_id,file_id) REFERENCES m1_app.preparation_files(workspace_id,item_id,id) ON DELETE CASCADE,
 FOREIGN KEY(workspace_id,approval_id) REFERENCES m1_app.preparation_decisions(workspace_id,id)
);

CREATE INDEX preparation_owner_queue ON m1_app.preparation_items(workspace_id,owner_id,created_at,id);
CREATE INDEX preparation_reviewer_queue ON m1_app.preparation_items(workspace_id,reviewer_id,created_at,id);
ALTER TABLE m1_app.preparation_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE m1_app.preparation_plans ENABLE ROW LEVEL SECURITY;
ALTER TABLE m1_app.preparation_files ENABLE ROW LEVEL SECURITY;
ALTER TABLE m1_app.preparation_reviews ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON m1_app.preparation_items,m1_app.preparation_plans,m1_app.preparation_files,m1_app.preparation_reviews FROM PUBLIC,anon,authenticated;
