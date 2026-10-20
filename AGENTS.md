# Project instructions

Keep this project small: one self-contained skill and one Python entry point. Prefer the standard library; do not add a web app, database, scheduler, or abstraction layer without a concrete request.

The ranking rules live in `skills/ai-fair-rating/SKILL.md`. Keep the script, README, and examples consistent with those rules. Filter out estimated and missing scores before selecting each creator's best eligible model. Compare full precision scores; 35 is included. Never substitute max for OpenAI/Anthropic xhigh. Exclude the Muse Wonder Full release because it is not offered through the public API; do not present a hypothesis about its architecture as fact.

Use public source data; do not infer scores, countries, or unavailable settings. A source format change must produce an actionable error instead of silently using the initial few models or an old snapshot.

Keep generated snapshots, caches, virtual environments, and local paths out of Git. Only `examples/` contains intentional published output. Preserve source attribution and flag licensing.

For changes to selection or fetching, run `python -m unittest discover -s tests -v`. For chart changes, also render a real chart and inspect the PNG. Flag and value bounds must not overlap. Validate the skill with the skill-creator validator when available.
