-- Append-only history of edits made to a pack before it is signed.
--
-- Exists to make "edits per pack" measurable. corpus/02 section 8 defines it
-- as "count of commentary and number corrections made by the analyst before
-- signing" and calls it the primary commercial metric; corpus/11 section 4
-- lists it as tracked, not gated, with no target ("setting a target on any of
-- them before pilot one would be inventing a number").
--
-- Number corrections need no table: report_artefact already holds one row per
-- generation (db/migrations/tenant/0013), so a change in a period's `sections`
-- between two draft generations is recoverable from those rows. Commentary
-- edits are not: report_artefact.commentary is rewritten in place by
-- src/reports/signoff.edit_commentary. This table is where the superseded text
-- goes, so an edit is counted AND the prior wording survives -- CLAUDE.md
-- invariant 4, nothing in this system is overwritten without the prior value
-- being retained somewhere.
--
-- Not bitemporal: these rows are immutable events, not facts about the
-- business. Nothing ever supersedes one, so there is no valid_from/valid_to
-- pair to maintain (CLAUDE.md invariant 3 governs fact tables).

CREATE TABLE __SCHEMA__.pack_edit_event (
    pack_edit_event_id  bigserial   PRIMARY KEY,
    tenant_id           uuid        NOT NULL,
    entity_id           int         NOT NULL,
    report_artefact_id  bigint      NOT NULL REFERENCES __SCHEMA__.report_artefact(report_artefact_id),
    period_key          text        NOT NULL,
    edit_type           text        NOT NULL,   -- 'commentary' only; number corrections derive from report_artefact
    edited_by           text        NOT NULL,   -- named analyst, corpus/02 section 8 ("made by the analyst")
    edited_at           timestamptz NOT NULL DEFAULT now(),
    previous_commentary text,                   -- the superseded wording, NULL on the first commentary written
    new_commentary      text,
    CONSTRAINT ck_pack_edit_event_type CHECK (edit_type IN ('commentary'))
);

CREATE INDEX ix_pack_edit_event_artefact ON __SCHEMA__.pack_edit_event (report_artefact_id, edited_at);
CREATE INDEX ix_pack_edit_event_period   ON __SCHEMA__.pack_edit_event (tenant_id, entity_id, period_key);

COMMENT ON TABLE __SCHEMA__.pack_edit_event IS
  'Grain: one edit to a draft pack. Append-only, never updated or deleted. Feeds the edits-per-pack measure in corpus/02 section 8 and corpus/11 section 4.';

REVOKE ALL ON __SCHEMA__.pack_edit_event FROM model_reachable;
