# Project instructions

Keep this project small: one self-contained skill and one Python entry point. Prefer the standard library; do not add a web app, database, scheduler, or abstraction layer without a concrete request.

The ranking rules live in `skills/ai-fair-rating/SKILL.md`. Keep the script, README, and examples consistent with those rules. Filter out estimated and missing scores and models without a public API before selecting each creator's best eligible model. API availability requires a positive integer `hostModelCount` from the source; missing or malformed availability is an actionable error. Apply the same rule to every developer, with no effort restrictions or model-name exclusions. Intelligence Index includes scores at least the current best measured API score of the `qwen3-8-27b` release, with equality included and full precision compared. Missing or unmeasured reference data is an actionable error, never a fixed-number fallback. Record the reference model, setting and exact score in metadata. Do not present a hypothesis about a model's architecture as fact.

Use public source data; do not infer scores, countries, or unavailable settings. A source format change must produce an actionable error instead of silently using the initial few models or an old snapshot.

One default run produces both Intelligence Index and Coding Agent Index charts. Coding results are grouped by model developer, not harness developer; exclude mixed-model routers and unavailable configurations. Require complete measured Coding Agent components, match the exact model/effort to the full model catalog, and apply the same API requirement, with no score threshold. Include every eligible developer's best result, even zero. Use model attributes for flags, input icons and open-weight hatching; label the harness separately. Keep index versions and scales distinct. Save Coding Agent outputs under `coding-agents/`.

Keep generated snapshots, caches, virtual environments, and local paths out of Git. Only `examples/` contains intentional published output. Preserve source attribution and flag licensing.

For changes to selection or fetching, run `python -m unittest discover -s tests -v`. For chart changes, also render a real chart and inspect the PNG. Flag and value bounds must not overlap. Validate the skill with the skill-creator validator when available.
