CREATE TABLE m1_app.source_extractions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL REFERENCES m1_app.workspaces(id) ON DELETE CASCADE,
    sha256 text NOT NULL CHECK(sha256 ~ '^[0-9a-f]{64}$'),
    parser_version text NOT NULL,
    extraction_sha256 text NOT NULL,
    status text NOT NULL CHECK(status IN ('complete','partial','failed')),
    locations jsonb NOT NULL,
    anchor_count integer NOT NULL CHECK(anchor_count >= 0),
    UNIQUE(workspace_id,id),
    UNIQUE(workspace_id,sha256,parser_version)
);
CREATE TABLE m1_app.source_extraction_anchors (
    workspace_id uuid NOT NULL,
    extraction_id uuid NOT NULL,
    ordinal integer NOT NULL,
    anchor_key text NOT NULL,
    metadata jsonb NOT NULL,
    text text NOT NULL,
    search tsvector GENERATED ALWAYS AS (to_tsvector('simple',text)) STORED,
    PRIMARY KEY(extraction_id,ordinal),
    FOREIGN KEY(workspace_id,extraction_id) REFERENCES m1_app.source_extractions(workspace_id,id) ON DELETE CASCADE
);
CREATE INDEX source_anchor_search ON m1_app.source_extraction_anchors USING gin(search);
CREATE TABLE m1_app.source_index_versions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL,
    tender_id uuid NOT NULL,
    parsed_sources_version_id uuid NOT NULL,
    input_revision integer NOT NULL,
    parser_version text NOT NULL,
    inventory jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(workspace_id,id),
    UNIQUE(workspace_id,parsed_sources_version_id,parser_version),
    FOREIGN KEY(workspace_id,tender_id) REFERENCES m1_app.tenders(workspace_id,id) ON DELETE CASCADE,
    FOREIGN KEY(workspace_id,parsed_sources_version_id) REFERENCES m1_app.artifact_versions(workspace_id,id) ON DELETE CASCADE
);
CREATE TABLE m1_app.source_index_documents (
    workspace_id uuid NOT NULL,
    index_id uuid NOT NULL,
    document_version_id uuid NOT NULL,
    extraction_id uuid NOT NULL,
    filename text NOT NULL,
    source_role text NOT NULL,
    PRIMARY KEY(index_id,document_version_id),
    FOREIGN KEY(workspace_id,index_id) REFERENCES m1_app.source_index_versions(workspace_id,id) ON DELETE CASCADE,
    FOREIGN KEY(workspace_id,extraction_id) REFERENCES m1_app.source_extractions(workspace_id,id) ON DELETE CASCADE
);
ALTER TABLE m1_app.source_extractions ENABLE ROW LEVEL SECURITY;
ALTER TABLE m1_app.source_extraction_anchors ENABLE ROW LEVEL SECURITY;
ALTER TABLE m1_app.source_index_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE m1_app.source_index_documents ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON m1_app.source_extractions,m1_app.source_extraction_anchors,m1_app.source_index_versions,m1_app.source_index_documents FROM PUBLIC,anon,authenticated;
