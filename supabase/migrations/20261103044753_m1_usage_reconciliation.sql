-- Preserve the original dispatch limits. Only a matching private audit can authorize an actual-cost exception.
ALTER TABLE m1_app.usage_reservations
    ADD COLUMN counted_input_tokens bigint CHECK(counted_input_tokens >= 0 AND counted_input_tokens <= max_input_tokens);

CREATE TABLE m1_app.usage_reconciliations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL,
    budget_id uuid NOT NULL,
    reservation_id uuid NOT NULL UNIQUE REFERENCES m1_app.usage_reservations(id) ON DELETE CASCADE,
    actor_id uuid NOT NULL,
    authorized_cost numeric NOT NULL CHECK(authorized_cost > 0),
    authorization_reference text NOT NULL CHECK(length(trim(authorization_reference)) BETWEEN 1 AND 2000),
    reason text NOT NULL CHECK(length(trim(reason)) BETWEEN 1 AND 2000),
    original_reservation jsonb NOT NULL,
    provider_response jsonb NOT NULL,
    actual_cost numeric NOT NULL CHECK(actual_cost >= 0 AND actual_cost <= authorized_cost),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(id,reservation_id,workspace_id,budget_id,actual_cost),
    FOREIGN KEY(workspace_id,budget_id) REFERENCES m1_app.stage_budgets(workspace_id,id) ON DELETE CASCADE
);
ALTER TABLE m1_app.usage_reconciliations ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON m1_app.usage_reconciliations FROM PUBLIC,anon,authenticated;

ALTER TABLE m1_app.usage_reservations ADD COLUMN reconciliation_id uuid;
ALTER TABLE m1_app.usage_reservations ADD CONSTRAINT usage_reconciliation_receipt
    FOREIGN KEY(reconciliation_id,id,workspace_id,budget_id,actual_cost)
    REFERENCES m1_app.usage_reconciliations(id,reservation_id,workspace_id,budget_id,actual_cost)
    DEFERRABLE INITIALLY DEFERRED;

DO $$
DECLARE constraint_name text;
BEGIN
    SELECT conname INTO STRICT constraint_name FROM pg_constraint
    WHERE conrelid='m1_app.usage_reservations'::regclass AND contype='c'
      AND pg_get_constraintdef(oid) LIKE '%actual_cost <= maximum_cost%';
    EXECUTE format('ALTER TABLE m1_app.usage_reservations DROP CONSTRAINT %I',constraint_name);
END $$;
ALTER TABLE m1_app.usage_reservations ADD CONSTRAINT usage_actual_cost_authority
    CHECK(actual_cost IS NULL OR actual_cost <= maximum_cost OR reconciliation_id IS NOT NULL);
ALTER TABLE m1_app.usage_reservations ADD CONSTRAINT usage_reconciliation_settled
    CHECK(reconciliation_id IS NULL OR state='settled');
