ALTER TABLE m1_app.review_tasks
    ADD COLUMN draft_ref text,
    ADD COLUMN requirement_ids text[] NOT NULL DEFAULT '{}',
    ADD COLUMN manifest jsonb NOT NULL DEFAULT '{}',
    ADD COLUMN purpose text NOT NULL DEFAULT 'qualification_review',
    ADD COLUMN created_by uuid,
    ADD COLUMN created_at timestamptz NOT NULL DEFAULT now();
CREATE UNIQUE INDEX open_review_equivalent ON m1_app.review_tasks
    (workspace_id,tender_id,requirement_ref,assignee_id,purpose) WHERE status='open';
CREATE UNIQUE INDEX one_answer_per_review ON m1_app.review_answers(workspace_id,task_id);
ALTER TABLE m1_app.review_answers
    ADD COLUMN reassessment_job_id uuid,
    ADD CONSTRAINT answer_job_in_workspace FOREIGN KEY(workspace_id,reassessment_job_id)
        REFERENCES m1_app.jobs(workspace_id,id);
