-- Collapse workspace access to one MVP level, retaining business assignments and history.
ALTER TABLE m1_app.memberships DROP CONSTRAINT memberships_roles_check;
UPDATE m1_app.memberships SET roles = CASE
    WHEN 'admin' = ANY(roles) THEN ARRAY['admin']::text[]
    WHEN roles && ARRAY['bid_owner','service_reviewer','approver','member']::text[] THEN ARRAY['member']::text[]
    ELSE ARRAY['viewer']::text[] END;
ALTER TABLE m1_app.memberships ADD CONSTRAINT memberships_roles_check
    CHECK (cardinality(roles)=1 AND roles <@ ARRAY['member','admin','viewer']::text[]);
