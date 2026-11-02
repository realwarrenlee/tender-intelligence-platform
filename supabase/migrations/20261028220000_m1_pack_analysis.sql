-- Keep durable per-section model reservations private under existing RLS/grants.
ALTER TABLE m1_app.analysis_model_calls ADD COLUMN part_index integer NOT NULL DEFAULT 0 CHECK(part_index BETWEEN 0 AND 32);
ALTER TABLE m1_app.analysis_model_calls DROP CONSTRAINT analysis_model_calls_sequence_check;
ALTER TABLE m1_app.analysis_model_calls ADD CONSTRAINT analysis_model_calls_sequence_check CHECK(sequence BETWEEN 1 AND 96);
