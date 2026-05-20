---
status: draft
created: 2026-05-13
updated: 2026-05-13
related_features: [2, 4]
related_prs: []
related_user_stories: [11988, 11989]
---

# Add timed triggers and parametrised entities to subscriptions

Expand the architecture of subscriptions to support:
- Time-based triggers (single postponable ones and recurring ones) in addition as an alternative or addition to the current on-data-change condition checks.
- Parametrised entities; this is mostly for parameterised searches with global VOR Search or the entity-specific VOR Search tools.

These are technically two separate pieces of work, but both will require architecture changes, therefore worth planning and executing jointly.

After time triggers are added, the non-subscription logistics summary warnings daily notifications code (Feature 04) can be removed.


