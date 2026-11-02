ALTER TABLE m1_app.analysis_model_calls ADD COLUMN input_sha256 text CHECK(input_sha256 ~ '^[0-9a-f]{64}$');
ALTER TABLE m1_app.analysis_model_calls ADD COLUMN validated boolean NOT NULL DEFAULT false;
CREATE INDEX analysis_validated_input ON m1_app.analysis_model_calls(workspace_id,input_sha256) WHERE validated;
