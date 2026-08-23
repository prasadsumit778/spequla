-- Verbatim shape from corpus/04_SPEQULA_CANONICAL_DATA_MODEL.md section 3.7
-- (map_account itself is Sprint 2 scope and is not created here).
--
-- Built now, ahead of Sprint 2, purely as infrastructure: fact_gl_entry's
-- mapping_version_id is NOT NULL per the corpus DDL, but the mapping loop
-- (map_account, the proposer, the review UI) is explicitly Sprint 2 work.
-- Every tenant is seeded with exactly one placeholder row -- version_no = 0,
-- status = 'draft' (an existing enum value from the corpus DDL comment, not
-- a new one), approved_by/approved_at left null -- so Sprint 1's canonical
-- writes have a valid, non-fabricated value to reference. dim_account.is_mapped
-- stays false throughout, so nothing downstream can mistake this placeholder
-- for an approved mapping.

CREATE TABLE __SCHEMA__.mapping_version (
    mapping_version_id  serial      PRIMARY KEY,
    tenant_id            uuid        NOT NULL,
    entity_id            int         NOT NULL,
    version_no           int         NOT NULL,
    status                text        NOT NULL,   -- 'draft' | 'approved' | 'superseded'
    effective_from        date        NOT NULL,
    effective_to          date        NOT NULL DEFAULT '9999-12-31',
    created_by            text        NOT NULL,
    approved_by           text,
    approved_at           timestamptz,
    change_reason         text,
    UNIQUE (tenant_id, entity_id, version_no)
);
COMMENT ON TABLE __SCHEMA__.mapping_version IS
  'Grain: one mapping version header. Version 0 per tenant is a system-created draft placeholder so fact_gl_entry.mapping_version_id (NOT NULL) has somewhere to point before sprint 2 approves version 1.';
