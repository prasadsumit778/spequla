-- Sprint 7, corpus/12: "Model cost tracking per tenant." Extends query_log
-- (0007) rather than adding a new table -- one query, one row, is already
-- the right grain for a cost figure, since cost is a property of one model
-- call. All three columns are nullable and stay null for every query_log
-- row written today: intent classification and IR generation are the only
-- model calls (corpus/07 section 9), and src/semantic/model_client.py's
-- AnthropicModelClient is deliberately left unconfigured until a vendor
-- decision is made (your own instruction, sprint 4) -- StubModelClient,
-- the only ModelClient wired up anywhere right now, reports no usage
-- because it calls no model. These columns exist so the moment a real
-- client is configured, cost recording has somewhere to write to without
-- another migration.

ALTER TABLE app.query_log ADD COLUMN input_tokens int;
ALTER TABLE app.query_log ADD COLUMN output_tokens int;
ALTER TABLE app.query_log ADD COLUMN cost_inr numeric(12,4);

COMMENT ON COLUMN app.query_log.cost_inr IS
  'Null until a real ModelClient reports usage. No per-token or per-call rate is invented here -- that number belongs to whichever model vendor is eventually configured, per CLAUDE.md section 3.2.';
