---
name: ai-fair-rating
description: "Build or refresh an Artificial Analysis Intelligence Index chart with one independently measured flagship per AI developer, country flags, and transparent reasoning-effort filters. Use for AI Fair Rating or a deduplicated AI developer ranking; not for subscription prices or unrelated benchmarks."
---

# AI Fair Rating

Generate the current developer ranking from public Artificial Analysis data using [scripts/rating.py](scripts/rating.py). The helper fetches the full catalog, selects models, and writes PNG, SVG, CSV, metadata, and a reusable source snapshot. No API key is needed.

## Rules

- Group by the source's `creator.id`, using its developer names and countries.
- Include only finite numeric `intelligenceIndex` scores with `intelligenceIndexIsEstimated` explicitly false. Missing status is not a measured result.
- For OpenAI and Anthropic, require `effort.slug == "xhigh"`. Do not fall back to max or another setting. Other developers have no effort restriction.
- Exclude the `muse-wonder-full` release, including its effort variants: it is not offered through the public Meta Model API. Use the eligible Muse Wonder result for Meta. This is an availability rule, not a claim that Full is an ensemble or merely a harness mode.
- Choose the highest exact eligible score per developer, then retain scores **at least 35** by default. Rank before rounding; display two decimals.
- Keep companies bold, model names readable, and country flags above the values with a visible gap. Preserve the zero baseline.
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
