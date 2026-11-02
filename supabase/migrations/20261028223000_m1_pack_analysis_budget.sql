ALTER TABLE m1_app.analysis_model_calls DROP CONSTRAINT analysis_model_calls_part_index_check;
ALTER TABLE m1_app.analysis_model_calls ADD CONSTRAINT analysis_model_calls_part_index_check CHECK(part_index BETWEEN 0 AND 64);
ALTER TABLE m1_app.analysis_model_calls DROP CONSTRAINT analysis_model_calls_sequence_check;
ALTER TABLE m1_app.analysis_model_calls ADD CONSTRAINT analysis_model_calls_sequence_check CHECK(sequence BETWEEN 1 AND 192);
