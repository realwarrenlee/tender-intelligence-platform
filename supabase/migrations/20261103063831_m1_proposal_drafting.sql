ALTER TABLE m1_app.preparation_files ADD COLUMN proposal_manifest jsonb;
ALTER TABLE m1_app.preparation_items ADD COLUMN proposal_entity text;
ALTER TABLE m1_app.preparation_plans ADD COLUMN proposal_entity text;
