-- Dashlets stay self-contained (a plain copy of chat's chart/table/actions
-- payload, captured at save time) rather than a live-replayable reference —
-- "question"/"model" were only needed to re-run the answer later, which
-- this design deliberately doesn't do.
ALTER TABLE "dashlets" DROP COLUMN "question";
ALTER TABLE "dashlets" DROP COLUMN "model";
