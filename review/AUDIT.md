# README Audit — plato-types

**Date:** 2026-05-17 | **Reviewer:** Forgemaster ⚒️

## Scores

| Criterion | Score | Notes |
|-----------|:-----:|-------|
| WHAT it is | ✅ | "Core types for the PLATO tile protocol" — clear |
| WHY you'd use it | ⚠️ | "Used across the fleet" is vague. Doesn't explain what the tile protocol enables or why you need these types. |
| HOW to install | ✅ | Has `pip install plato-types` |
| HOW to use (code) | ✅ | Good usage examples with lifecycle, Lamport clock, content hash |
| Links / context | ✅ | "Used By" section lists dependent repos |

**Total: 4/5**

## Issues

1. **Weak "Why".** Needs one sentence explaining the tile protocol: "Tiles are signed, content-addressed training artifacts that flow between PLATO rooms and fleet agents."

## Action Taken

- ✅ Minor improvement: added one-sentence "Why" context
