-- Approvals are explicitly provisioned server-side; no paid authority is seeded here.
CREATE TABLE m1_app.workspace_spending_policies (
    workspace_id uuid PRIMARY KEY REFERENCES m1_app.workspaces(id) ON DELETE CASCADE,
    daily_limit_usd numeric NOT NULL CHECK(daily_limit_usd > 0),
    approved_by uuid NOT NULL,
    approved_at timestamptz NOT NULL DEFAULT now(),
    paused boolean NOT NULL DEFAULT false
);

CREATE TABLE m1_app.stage_budgets (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL REFERENCES m1_app.workspaces(id) ON DELETE CASCADE,
    tender_id uuid,
    stage text NOT NULL CHECK(stage IN ('screening','discovery')),
    scope_key text NOT NULL CHECK(length(scope_key) BETWEEN 1 AND 256),
    limit_usd numeric NOT NULL CHECK(limit_usd > 0),
    max_requests integer NOT NULL CHECK(max_requests > 0),
    max_responses_requests integer NOT NULL CHECK(max_responses_requests >= 0),
    max_input_tokens bigint NOT NULL CHECK(max_input_tokens > 0),
    approved_by uuid NOT NULL,
    approved_at timestamptz NOT NULL DEFAULT now(),
    blocked_reason text,
    UNIQUE(workspace_id,id),
    UNIQUE(workspace_id,stage,scope_key),
    CHECK(stage='screening' OR tender_id IS NULL),
    FOREIGN KEY(workspace_id,tender_id) REFERENCES m1_app.tenders(workspace_id,id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX one_screening_budget_per_tender
    ON m1_app.stage_budgets(workspace_id,tender_id) WHERE stage='screening' AND tender_id IS NOT NULL;

CREATE TABLE m1_app.usage_reservations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL,
    budget_id uuid NOT NULL,
    actor_id uuid NOT NULL,
    idempotency_key text NOT NULL CHECK(length(idempotency_key) BETWEEN 1 AND 256),
    request_hash text NOT NULL,
    model text NOT NULL,
    api text NOT NULL CHECK(api IN ('responses','decisions')),
    max_input_tokens bigint NOT NULL CHECK(max_input_tokens >= 0),
    max_output_tokens integer NOT NULL CHECK(max_output_tokens > 0),
    maximum_cost numeric NOT NULL CHECK(maximum_cost >= 0),
    price jsonb NOT NULL,
    budget_day date NOT NULL DEFAULT (now() AT TIME ZONE 'Asia/Singapore')::date,
    state text NOT NULL DEFAULT 'reserved' CHECK(state IN ('reserved','unknown','settled')),
    outcome text CHECK(outcome IN ('completed','rejected','unknown')),
    actual_input_tokens bigint CHECK(actual_input_tokens >= 0),
    actual_output_tokens integer CHECK(actual_output_tokens >= 0),
    actual_cost numeric CHECK(actual_cost >= 0),
    provider_usage jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    settled_at timestamptz,
    UNIQUE(budget_id,idempotency_key),
    FOREIGN KEY(workspace_id,budget_id) REFERENCES m1_app.stage_budgets(workspace_id,id) ON DELETE CASCADE,
    CHECK((state='settled') = (actual_cost IS NOT NULL)),
    CHECK(actual_cost IS NULL OR actual_cost <= maximum_cost)
);
CREATE INDEX workspace_daily_usage ON m1_app.usage_reservations(workspace_id,budget_day);

ALTER TABLE m1_app.workspace_spending_policies ENABLE ROW LEVEL SECURITY;
ALTER TABLE m1_app.stage_budgets ENABLE ROW LEVEL SECURITY;
ALTER TABLE m1_app.usage_reservations ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON m1_app.workspace_spending_policies,m1_app.stage_budgets,m1_app.usage_reservations FROM PUBLIC,anon,authenticated;
