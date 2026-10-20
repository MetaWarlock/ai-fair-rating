---
name: ai-fair-rating
description: "Build or refresh an Artificial Analysis Intelligence Index chart with each AI developer's best independently measured API model and country flags. Use for AI Fair Rating or a deduplicated AI developer ranking; not for subscription prices or unrelated benchmarks."
---

# AI Fair Rating

Generate the current developer ranking from public Artificial Analysis data using [scripts/rating.py](scripts/rating.py). The helper fetches the full catalog, selects models, and writes PNG, SVG, CSV, metadata, and a reusable source snapshot. No API key is needed.

## Rules

- Group by the source's `creator.id`, using its developer names and countries.
- Include only finite numeric `intelligenceIndex` scores with `intelligenceIndexIsEstimated` explicitly false. Missing status is not a measured result.
- Require public API availability: the source must list at least one API provider (`hostModelCount` is a positive integer). Exclude zero; fail with an actionable error on missing or malformed availability. Do not infer availability from prices, open weights, model names, or effort labels.
- Apply the same rule to all developers. Allow every API reasoning setting, including max, and choose by the measured score. Do not enforce xhigh or maintain model-name exceptions. A subscription-only variant with no API provider is ineligible under the general rule.
- Choose the highest exact eligible score per developer, then retain scores **at least 35** by default. Rank before rounding; display two decimals.
- Keep companies bold, model names readable, and country flags above the values with a visible gap. Preserve the zero baseline.
- Inside each bar, stack supported input icons from bottom to top: text, photo, audio, video. Read the source's boolean `inputModalityText`, `inputModalityImage`, `inputModalitySpeech`, and `inputModalityVideo` fields; omit unsupported types and fail on missing or malformed flags. These are input capabilities of the selected model, not output capabilities or all models from the developer. Include a legend, preserve icon clearance inside the bars, and export the types in CSV.
- Use the subtitle `Рейтинг лучших разработчиков AI по их лучшей модели`. Put `https://t.me/warlocksu` and `https://warlock.su` in the upper-right corner by default; CLI options allow replacement.

## Run

Resolve paths relative to this skill directory, not the caller's working directory. Install dependencies from [requirements.txt](requirements.txt) in an available Python 3.10+ environment, preferably a virtual environment:

```bash
python -m pip install -r /path/to/ai-fair-rating/requirements.txt
python /path/to/ai-fair-rating/scripts/rating.py --output /path/to/output
```

For a reproducible historical chart, add `--snapshot /path/to/output/snapshot.json`. The original retrieval date stays on the chart. Never present a saved snapshot as a fresh fetch. `--min-score`, `--telegram`, and `--website` override presentation defaults when requested.

Inspect the generated PNG before delivering it. Report the data date and developer count; show the image and link the downloadable output. If fetching or the source schema fails, report the error and preserve existing output rather than inventing values or silently using a partial catalog. An empty selection is a valid error, not a blank chart.

This is a comparison within the AA index under these filters. Do not claim equal compute budgets, subscription availability, or that the name max proves multi-agent inference. Do not publish, push, or message anyone merely because this skill was invoked.
