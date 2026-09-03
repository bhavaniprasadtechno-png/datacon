# 01 — Retire/repurpose the dead pipeline modules

**What to build:** Clear the ground for the new pipeline by resolving the existing (currently unreferenced) Retriever, Validator, Responder, context-filter, live-query, and connector-query components: each is either rewritten in place for its role in the new pipeline, or removed entirely if nothing in the new design will call it. The previously-unused Analytics calculation functions get the same treatment. No user-visible behavior changes in this ticket — all five specialized agents keep responding exactly as they do today.

**Blocked by:** None — can start immediately

**Status:** done

- [ ] Each of Retriever, Validator, Responder, context-filter, live-query, and connector-query has a documented disposition (repurposed vs. removed) and that disposition is applied.
- [ ] Modules with no remaining caller after this change are deleted entirely — no orphaned files left behind.
- [ ] Modules kept for later reuse (Retriever, Validator) are stripped of logic built around the old context-dict input shape that no longer exists in the live `/stream` path.
- [ ] The previously-unused Analytics calculation functions are evaluated: any that fit a `NormalizedResult`-shaped input are kept for reuse in ticket 02; the rest are removed rather than left alongside the new implementation.
- [ ] `chat_router`'s per-intent dispatch and all five specialized agents behave exactly as they do today — the existing test suite passes unmodified, with no new or changed assertions needed.
- [ ] A repo-wide search confirms no remaining imports of any removed module.
