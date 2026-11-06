---
name: ai-fair-rating
description: "Build or refresh both Artificial Analysis Intelligence Index and Coding Agent Index charts, with one measured API model per developer, country flags, input icons and open-weight hatching. Use for AI Fair Rating or deduplicated AI developer rankings; not for subscription prices or unrelated benchmarks."
---

# AI Fair Rating

Generate both current developer rankings from public Artificial Analysis data using [scripts/rating.py](scripts/rating.py). The helper fetches the full model and coding-agent catalogs, selects results, and writes PNG, SVG, CSV, metadata, and reusable source snapshots. No API key is needed. Keep one skill and one entry point.

## Rules

- Group by the source's `creator.id`, using its developer names and countries.
- Include only finite numeric `intelligenceIndex` scores. The source no longer publishes an estimate flag, so every finite numeric score counts; skip missing or non-numeric scores and do not invent a status.
- Require public API availability: `hostModelCount` must be a positive integer AND `aa_public_api_unavailable` must explicitly be false. The fetcher reads the public client's model-ID list that drives the **No publicly available API** label, then annotates every catalog entry with this boolean. A true marker always excludes the model, even with a positive provider count. Apply this to Intelligence candidates, the Qwen reference and matched Coding Agent models before choosing each developer's best result. Do not infer availability from prices, open weights, model names, effort labels or provider count alone.
- Save the marker list, its public script URL and content hash in the source snapshot and both metadata files. Parse the source as data without executing JavaScript or maintaining a hand-written model exclusion list. Fail with an actionable error if the marker-list source format changes or a snapshot lacks the boolean; refresh old snapshots rather than assuming unmarked availability. Snapshot replay must use its recorded markers, without silently fetching newer availability.
- Apply the same rule to all developers. Allow every API reasoning setting, including max, and choose by the measured score. Do not enforce xhigh or maintain model-name exceptions. A subscription-only variant with no API provider is ineligible under the general rule.
- For Intelligence Index, resolve the reference release `qwen3-8-27b` in the same model catalog. Its highest numeric API score across reasoning settings is the inclusive minimum score. Choose each developer's best eligible model and retain results **at least that exact reference score**. Do not use a fixed number or round before selection. If no numeric API score exists for the reference, fail with an actionable error instead of substituting another model or an old score. Record the reference name, slug, effort, exact score and source link in metadata; identify the reference on the chart. Display scores to two decimals.
- Use 12 pt bold developer names, 10 pt model names, and an 8 pt detail line under each bar in both charts. Shift the labels 5 pixels left at the 180 dpi PNG export size. Keep country flags above the values with a visible gap and preserve the zero baseline.
- The Intelligence Index detail line shows the selected model's API prices in USD per million tokens. List cached input (`cacheHitPrice`) first, then uncached input (`price1mInputTokens`), then output (`price1mOutputTokens`). Separate the amounts with vertical bars, show at least two decimal places, and retain extra source precision. Show a dash for an unavailable price.
- Overlay diagonal hatching on the original bar color for models whose source boolean `isOpenWeights` is true. Include an open-weights legend and CSV flag. Fail on missing or malformed status; do not infer it from the developer, model name, or license category.
- Inside each bar, stack supported input icons from bottom to top: text, photo, audio, video. Read the source's boolean `inputModalityText`, `inputModalityImage`, `inputModalitySpeech`, and `inputModalityVideo` fields; omit unsupported types and fail on missing or malformed flags. These are input capabilities of the selected model, not output capabilities or all models from the developer. Include a legend, preserve icon clearance inside the bars, and export the types in CSV. If a bar is too short or zero-height, place the stack just above it and move the value and flag above the stack; do not drop that result to make the icons fit.
- Use the subtitle `Рейтинг лучших разработчиков AI по их лучшей модели`. Put `https://t.me/warlocksu` and `https://warlock.su` in the upper-right corner by default; CLI options allow replacement.

## Coding Agent Index

- Fetch the complete `benchmarkRows` from [Coding Agent Index](https://artificialanalysis.ai/agents/coding-agents), resolving JSON Flight references. Do not use only the highlighted cards or default selection. Validate the full count (the source's selector excludes router rows) and index version.
- Group by the **model developer**, not the agent/harness developer. Include the measured model and harness in labels and CSV. Use the 8 pt detail line for the harness. Exclude `isRouter == true` mixed-model routers and `isUnavailable == true` configurations. Missing/malformed flags are errors. The user explicitly chose this grouping.
- Use the published `indexScore * 100`, retaining full precision. Any finite numeric score counts, as for Intelligence Index; skip missing scores. A score outside the source 0..1 scale is an actionable error, not a value to rescale.
- Match the model to the complete model catalog by exact name or short name (case-insensitive) and model creator slug. Do not remove release dates, substitute efforts, or guess aliases. No unique match is an actionable error. Use that entry's API provider count and explicit No publicly available API marker, creator identity/country, open-weight flag and input modalities. The separate Intelligence Index score may be missing or estimated; it is not the Coding Agent score.
- Apply the same API requirement and one-best-per-developer selection, but **no score threshold**: include all eligible developers, including zero-score results. The Qwen reference applies only to Intelligence Index. Use subtitle `Рейтинг разработчиков AI по лучшей модели в coding-агенте`. Model input icons and open-weight hatching describe the underlying model, not extra features of the harness.

## Run

Resolve paths relative to this skill directory, not the caller's working directory. Install dependencies from [requirements.txt](requirements.txt) in an available Python 3.10+ environment, preferably a virtual environment:

```bash
python -m pip install -r /path/to/ai-fair-rating/requirements.txt
python /path/to/ai-fair-rating/scripts/rating.py --output /path/to/output
```

The default run writes Intelligence results directly in the output directory and Coding Agent results in its `coding-agents/` subdirectory. Each has `rating.png`, `rating.svg`, `rating.csv`, `metadata.json`, and `snapshot.json`. Coding metadata also records excluded configurations and the model-catalog hash/date used for API and visual attributes.

For reproducible historical charts, add both `--snapshot /path/to/output/snapshot.json --agents-snapshot /path/to/output/coding-agents/snapshot.json`. Original retrieval dates stay on the charts and the Qwen reference is recalculated from that same snapshot. Never present saved snapshots as fresh fetches. If explicitly asked for one index, use `--only models` or `--only coding-agents`; Coding Agent output still needs the model catalog, but does not require a Qwen reference score. `--telegram` and `--website` override contact defaults when requested.

Inspect both generated PNGs before delivering them. Report each source date, index version and developer count; show both images and link downloadable output. If fetching or the source schema fails, report the error and preserve existing output rather than inventing values or silently using a partial catalog. An empty selection is a valid error, not a blank chart.

This is a comparison within the AA index under these filters. Do not claim equal compute budgets, subscription availability, or that the name max proves multi-agent inference. Do not publish, push, or message anyone merely because this skill was invoked.
