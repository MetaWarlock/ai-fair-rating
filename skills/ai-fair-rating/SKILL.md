---
name: ai-fair-rating
description: "Build or refresh both Artificial Analysis Intelligence Index and Coding Agent Index charts, with one measured API model per developer, country flags, input icons and open-weight hatching. Use for AI Fair Rating or deduplicated AI developer rankings; not for subscription prices or unrelated benchmarks."
---

# AI Fair Rating

Generate both current developer rankings from public Artificial Analysis data using [scripts/rating.py](scripts/rating.py). The helper fetches the full model and coding-agent catalogs, selects results, and writes PNG, SVG, CSV, metadata, and reusable source snapshots. No API key is needed. Keep one skill and one entry point.

## Rules

- Group by the source's `creator.id`, using its developer names and countries.
- Include only finite numeric `intelligenceIndex` scores with `intelligenceIndexIsEstimated` explicitly false. Missing status is not a measured result.
- Require public API availability: the source must list at least one API provider (`hostModelCount` is a positive integer). Exclude zero; fail with an actionable error on missing or malformed availability. Do not infer availability from prices, open weights, model names, or effort labels.
- Apply the same rule to all developers. Allow every API reasoning setting, including max, and choose by the measured score. Do not enforce xhigh or maintain model-name exceptions. A subscription-only variant with no API provider is ineligible under the general rule.
- For Intelligence Index, resolve the reference release `qwen3-8-27b` in the same model catalog. Its highest independently measured API result across reasoning settings is the inclusive minimum score. Choose each developer's best eligible model and retain results **at least that exact reference score**. Do not use a fixed number or round before selection. If no measured API result exists for the reference, fail with an actionable error instead of substituting another model or an old score. Record the reference name, slug, effort, exact score and source link in metadata; identify the reference on the chart. Display scores to two decimals.
- Keep companies bold, model names readable, and country flags above the values with a visible gap. Preserve the zero baseline.
- Overlay diagonal hatching on the original bar color for models whose source boolean `isOpenWeights` is true. Include an open-weights legend and CSV flag. Fail on missing or malformed status; do not infer it from the developer, model name, or license category.
- Inside each bar, stack supported input icons from bottom to top: text, photo, audio, video. Read the source's boolean `inputModalityText`, `inputModalityImage`, `inputModalitySpeech`, and `inputModalityVideo` fields; omit unsupported types and fail on missing or malformed flags. These are input capabilities of the selected model, not output capabilities or all models from the developer. Include a legend, preserve icon clearance inside the bars, and export the types in CSV. If a bar is too short or zero-height, place the stack just above it and move the value and flag above the stack; do not drop that result to make the icons fit.
- Use the subtitle `Рейтинг лучших разработчиков AI по их лучшей модели`. Put `https://t.me/warlocksu` and `https://warlock.su` in the upper-right corner by default; CLI options allow replacement.

## Coding Agent Index

- Fetch the complete `benchmarkRows` from [Coding Agent Index](https://artificialanalysis.ai/agents/coding-agents), resolving JSON Flight references. Do not use only the highlighted cards or default selection. Validate the full count (the source's selector excludes router rows) and index version.
- Group by the **model developer**, not the agent/harness developer. Include the measured model and harness in labels and CSV. Exclude `isRouter == true` mixed-model routers and `isUnavailable == true` configurations. Missing/malformed flags are errors. The user explicitly chose this grouping.
- For v2.0, use the published `indexScore * 100`, retaining full precision, and require measured attempts for all three components: `frontiercode-v1.1-main`, `swe-atlas-qna`, `terminal-bench-v4`. Reject missing/estimated scores and incomplete coverage; check that the published score equals the mean of the three measured component scores. A new index version or component set requires updating validation, not silently reusing v2.0 rules.
- Match the model to the complete model catalog by exact name or short name (case-insensitive) and model creator slug. Do not remove release dates, substitute efforts, or guess aliases. No unique match is an actionable error. Use that entry's `hostModelCount`, creator identity/country, open-weight flag and input modalities. The separate Intelligence Index score may be missing or estimated; it is not the Coding Agent score.
- Apply the same API requirement and one-best-per-developer selection, but **no score threshold**: include all eligible developers, including zero-score results. The Qwen reference applies only to Intelligence Index. Use subtitle `Рейтинг разработчиков AI по лучшей модели в coding-агенте`. Model input icons and open-weight hatching describe the underlying model, not extra features of the harness.

## Run

Resolve paths relative to this skill directory, not the caller's working directory. Install dependencies from [requirements.txt](requirements.txt) in an available Python 3.10+ environment, preferably a virtual environment:

```bash
python -m pip install -r /path/to/ai-fair-rating/requirements.txt
python /path/to/ai-fair-rating/scripts/rating.py --output /path/to/output
```

The default run writes Intelligence results directly in the output directory and Coding Agent results in its `coding-agents/` subdirectory. Each has `rating.png`, `rating.svg`, `rating.csv`, `metadata.json`, and `snapshot.json`. Coding metadata also records excluded configurations and the model-catalog hash/date used for API and visual attributes.

For reproducible historical charts, add both `--snapshot /path/to/output/snapshot.json --agents-snapshot /path/to/output/coding-agents/snapshot.json`. Original retrieval dates stay on the charts and the Qwen reference is recalculated from that same snapshot. Never present saved snapshots as fresh fetches. If explicitly asked for one index, use `--only models` or `--only coding-agents`; Coding Agent output still needs the model catalog, but does not require a measured Qwen reference. `--telegram` and `--website` override contact defaults when requested.

Inspect both generated PNGs before delivering them. Report each source date, index version and developer count; show both images and link downloadable output. If fetching or the source schema fails, report the error and preserve existing output rather than inventing values or silently using a partial catalog. An empty selection is a valid error, not a blank chart.

This is a comparison within the AA index under these filters. Do not claim equal compute budgets, subscription availability, or that the name max proves multi-agent inference. Do not publish, push, or message anyone merely because this skill was invoked.
