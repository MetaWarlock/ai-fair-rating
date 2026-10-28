#!/usr/bin/env python3
"""Build Intelligence and Coding Agent rankings, one measured API model per developer."""

import argparse
import csv
import gzip
import hashlib
import html
import json
import math
from pathlib import Path
import re
import sys
import textwrap
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import urljoin
from urllib.request import Request, urlopen

SOURCE = "https://artificialanalysis.ai/models/comparisons"
AGENT_SOURCE = "https://artificialanalysis.ai/agents/coding-agents"
AGENT_COMPONENTS = {"frontiercode-v1.1-main", "swe-atlas-qna", "terminal-bench-v4"}
REFERENCE_RELEASE = "qwen3-8-27b"
SKILL_DIR = Path(__file__).resolve().parents[1]
FLAG_SOURCE = "https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/72x72/"
INPUT_MODALITIES = (("text", "inputModalityText", "Текст"),
                    ("image", "inputModalityImage", "Фото"),
                    ("audio", "inputModalitySpeech", "Аудио"),
                    ("video", "inputModalityVideo", "Видео"))


def download(url):
    request = Request(url, headers={"User-Agent": "AI-Fair-Rating/1.0"})
    with urlopen(request, timeout=30) as response:
        return response.read()


def flight_text(page):
    """Read JSON-encoded Next.js flight strings without executing site code."""
    chunks = []
    for match in re.finditer(r"self\.__next_f\.push\((\[.*?\])\)</script>", page):
        item = json.loads(match.group(1))
        if len(item) > 1 and isinstance(item[1], str):
            chunks.append(item[1])
    return "".join(chunks)


def parse_page(page):
    flight = flight_text(page)
    manifests = []
    for match in re.finditer(r'"manifest"\s*:\s*(\{[^}]+\})', flight):
        item = json.loads(match.group(1))
        if item.get("path", "").startswith("/data/") and re.fullmatch(r"[0-9a-f]{64}", item.get("key", "")):
            if item not in manifests:
                manifests.append(item)
    if not manifests:
        raise ValueError("Full catalog manifest not found. The source page format may have changed.")
    version = re.search(r"Intelligence Index v(\d+(?:\.\d+)+)", html.unescape(page))
    plain = html.unescape(re.sub(r"<[^>]+>", " ", page))
    counts = [int(n) for n in re.findall(r"of\s+(\d+)\s+models", plain)]
    return manifests, version.group(1) if version else None, max(counts, default=0)


def parse_agents_page(page):
    """Read the complete benchmarkRows, including React Flight references."""
    records = {}
    decoder = json.JSONDecoder()
    for line in flight_text(page).splitlines():
        match = re.match(r"^([0-9a-f]+):([\[{])", line)
        if match:
            try:
                records[match[1]] = decoder.raw_decode(line[match.end() - 1:])[0]
            except ValueError:
                continue

    def resolve(value, seen=()):
        if isinstance(value, str) and re.fullmatch(r"\$[0-9a-f]+(?::[A-Za-z0-9_]+)*", value):
            if value in seen:
                raise ValueError("Cyclic Coding Agent source reference; update the parser.")
            parts = value[1:].split(":")
            try:
                target = records[parts[0]]
                for part in parts[1:]:
                    target = target[3] if part == "props" and isinstance(target, list) else (
                        target[int(part)] if isinstance(target, list) else target[part])
                return resolve(target, seen + (value,))
            except (KeyError, IndexError, TypeError, ValueError) as error:
                raise ValueError(f"Unresolved Coding Agent reference {value}; update the parser.") from error
        if isinstance(value, list):
            return [resolve(item, seen) for item in value]
        if isinstance(value, dict):
            return {key: resolve(item, seen) for key, item in value.items()}
        return value

    catalogs = []

    def find(value):
        if isinstance(value, dict):
            if "benchmarkRows" in value:
                catalogs.append(resolve(value["benchmarkRows"]))
            for item in value.values():
                find(item)
        elif isinstance(value, list):
            for item in value:
                find(item)

    for record in records.values():
        find(record)
    version = re.search(r"Coding Agent Index v(\d+(?:\.\d+)+)", html.unescape(page))
    counts = [int(n) for n in re.findall(r"of\s+(\d+)\s+models", html.unescape(re.sub(r"<[^>]+>", " ", page)))]
    if len(catalogs) != 1 or not isinstance(catalogs[0], list) or not version or not counts:
        raise ValueError("Complete Coding Agent benchmarkRows, version or model count missing; update the source parser.")
    rows = catalogs[0]
    if not rows or any(not isinstance(row, dict) or not row.get("id") for row in rows):
        raise ValueError("Invalid Coding Agent catalog rows; update the source parser.")
    # The page's selector counts models with its router toggle off.
    non_routers = sum(row.get("isRouter") is False for row in rows)
    if len({row['id'] for row in rows}) != len(rows) or non_routers != max(counts):
        raise ValueError(f"Incomplete Coding Agent catalog: {len(rows)} configurations, page declares {max(counts)} models.")
    return rows, version.group(1)


def fetch_agents_snapshot():
    rows, version = parse_agents_page(download(AGENT_SOURCE).decode("utf-8"))
    return {"source_url": AGENT_SOURCE, "fetched_at": datetime.now(timezone.utc).isoformat(),
            "index_version": version, "agents": rows}


def decode_catalog(payload, key_hex):
    """Decode the same public catalog payload used by the site's client."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    key = bytes.fromhex(key_hex)
    iv = hashlib.sha256(key).digest()[:12]
    return json.loads(gzip.decompress(AESGCM(key).decrypt(iv, payload, None)))


def parse_unavailable_api_ids(script):
    """Read the public client's checkered-pattern list, without executing JavaScript."""
    identifier = r"[A-Za-z_$][\w$]*"
    pattern = (r"new Set\((\[[^\]]*\])\)," + identifier + r'="checkered",' + identifier +
               r"=\{\[" + identifier + r"\]:" + identifier + r"\.I\.notPubliclyAvailable\}")
    matches = re.findall(pattern, script)
    if not matches:
        return None
    if len(matches) != 1:
        raise ValueError("Ambiguous No publicly available API marker lists; update the source parser.")
    ids = json.loads(matches[0])
    if not isinstance(ids, list) or any(not isinstance(item, str) or not re.fullmatch(
            r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", item) for item in ids) or len(set(ids)) != len(ids):
        raise ValueError("Invalid No publicly available API model IDs; update the source parser.")
    return ids


def fetch_api_markers(page):
    scripts = list(dict.fromkeys(urljoin(SOURCE, path) for path in re.findall(
        r'<script[^>]+src="([^"]+\.js[^"]*)"', page)))
    scripts = [url for url in scripts if url.startswith("https://artificialanalysis.ai/_next/static/")]

    def inspect(url):
        script = download(url).decode("utf-8")
        ids = parse_unavailable_api_ids(script)
        if ids is not None:
            return {"label": "No publicly available API", "source_url": url,
                    "source_sha256": hashlib.sha256(script.encode("utf-8")).hexdigest(),
                    "unavailable_model_ids": ids}
        return None

    with ThreadPoolExecutor(max_workers=6) as pool:
        matches = [result for result in pool.map(inspect, scripts) if result is not None]
    if len(matches) != 1:
        raise ValueError("No unique No publicly available API marker catalog found in the public client. "
                         "Update the source parser; do not rely on hostModelCount alone.")
    return matches[0]


def fetch_snapshot():
    page = download(SOURCE).decode("utf-8")
    manifests, version, declared_count = parse_page(page)
    catalogs = []
    for manifest in manifests:
        data = decode_catalog(download(urljoin(SOURCE, manifest["path"])), manifest["key"])
        if isinstance(data, dict) and isinstance(data.get("models"), list):
            catalogs.append(data["models"])
    if not catalogs:
        raise ValueError("The public payload contains no model catalog.")
    models = max(catalogs, key=len)
    if not models or len(models) < declared_count:
        raise ValueError(f"Incomplete catalog: received {len(models)}, page declares {declared_count}.")
    if version is None:
        raise ValueError("Intelligence Index version not found; check the source page format.")
    markers = fetch_api_markers(page)
    unavailable = set(markers["unavailable_model_ids"])
    for model in models:
        if not isinstance(model.get("id"), str) or not model["id"]:
            raise ValueError("Missing model ID for public API marker matching; update the source parser.")
        model["aa_public_api_unavailable"] = model["id"] in unavailable
    return {"source_url": SOURCE, "fetched_at": datetime.now(timezone.utc).isoformat(),
            "index_version": version, "models": models, "public_api_markers": markers}


def finite_number(value):
    return type(value) in (int, float) and math.isfinite(value)


def model_details(model):
    hosts = model.get("hostModelCount")
    if type(hosts) is not int or hosts < 0:
        raise ValueError(f"Missing or invalid API availability (hostModelCount) for {model.get('slug', '?')}. "
                         "Refresh the source snapshot or update the fetcher; do not infer API availability.")
    if type(model.get("aa_public_api_unavailable")) is not bool:
        raise ValueError(f"Missing or invalid AA public API marker for {model.get('slug', '?')}. "
                         "Fetch a fresh model snapshot including No publicly available API markers; "
                         "do not rely on hostModelCount alone.")
    if model["aa_public_api_unavailable"] or hosts == 0:
        return None
    creator = model.get("creator") or {}
    if not all(creator.get(key) for key in ("id", "slug", "name")):
        raise ValueError(f"Missing developer identity for model {model.get('slug', '?')}.")
    if type(model.get("isOpenWeights")) is not bool:
        raise ValueError(f"Missing or invalid isOpenWeights for {model.get('slug', '?')}. "
                         "Refresh the snapshot or update the source parser; do not infer weight availability.")
    modalities = []
    for kind, field, _ in INPUT_MODALITIES:
        if type(model.get(field)) is not bool:
            raise ValueError(f"Missing or invalid input modality {field} for {model.get('slug', '?')}. "
                             "Refresh the snapshot or update the source parser; do not infer support.")
        if model[field]:
            modalities.append(kind)
    return {"company": creator["name"], "creator_id": creator["id"],
            "company_slug": creator["slug"], "country": creator.get("country"),
            "color": creator.get("color") or "#626a75", "model": model["name"],
            "short_name": model.get("shortName") or model["name"],
            "effort": (model.get("effort") or {}).get("slug"), "api_provider_count": hosts,
            "slug": model["slug"], "input_modalities": modalities, "open_weights": model["isOpenWeights"],
            "url": "https://artificialanalysis.ai/models/" + model["slug"]}


def best_per_developer(candidates, min_score=None):
    best = {}
    for candidate in candidates:
        previous = best.get(candidate["creator_id"])
        if previous is None or (-candidate["score"], candidate["slug"], candidate.get("agent_id", "")) < (
                -previous["score"], previous["slug"], previous.get("agent_id", "")):
            best[candidate["creator_id"]] = candidate
    rows = sorted((m for m in best.values() if min_score is None or m["score"] >= min_score),
                  key=lambda m: (-m["score"], m["company"], m["slug"]))
    for rank, row in enumerate(rows, 1):
        row["rank"] = rank
    return rows


def reference_model(models):
    """Use the best measured API setting of the named reference release."""
    eligible = []
    for model in models:
        if (model.get("release") or {}).get("slug") != REFERENCE_RELEASE:
            continue
        score = model.get("intelligenceIndex")
        if not finite_number(score) or model.get("intelligenceIndexIsEstimated") is not False:
            continue
        details = model_details(model)
        if details:
            eligible.append({"slug": model["slug"], "name": model["name"], "score": score,
                             "effort": details["effort"], "url": details["url"], "release_slug": REFERENCE_RELEASE})
    if not eligible:
        raise ValueError(f"No measured API result for reference release {REFERENCE_RELEASE}. "
                         "Refresh the model catalog or check the source; do not substitute a fixed threshold.")
    return min(eligible, key=lambda m: (-m["score"], m["slug"]))


def select_models(models, min_score=None):
    if min_score is None:
        min_score = reference_model(models)["score"]
    candidates = []
    for model in models:
        score = model.get("intelligenceIndex")
        if not finite_number(score) or model.get("intelligenceIndexIsEstimated") is not False:
            continue
        candidate = model_details(model)
        if candidate:
            candidates.append({**candidate, "score": score})
    return best_per_developer(candidates, min_score)


def model_name_key(name):
    return name.casefold().strip()


def select_agents(agents, models):
    names = {}
    for model in models:
        for name in {model.get("name"), model.get("shortName")} - {None}:
            key = (model.get("creator", {}).get("slug"), model_name_key(name))
            names.setdefault(key, {})[model["slug"]] = model
    candidates = []
    excluded = []
    for agent in agents:
        score = agent.get("indexScore")
        reason = None
        if not finite_number(score):
            reason = "missing_score"
        elif not 0 <= score <= 1:
            raise ValueError(f"Invalid Coding Agent indexScore for {agent.get('id')}; expected 0..1.")
        elif agent.get("indexScoreIsEstimated") is True:
            reason = "estimated_score"
        for field in ("isRouter", "isUnavailable"):
            if type(agent.get(field)) is not bool:
                raise ValueError(f"Missing Coding Agent {field} for {agent.get('id')}; update the parser.")
        if agent["isRouter"]:
            reason = "mixed_model_router"
        elif agent["isUnavailable"]:
            reason = "unavailable_configuration"
        elif not reason:
            evals = agent.get("evals")
            if not isinstance(evals, list) or agent.get("indexComponentCount") != 3 or len(evals) != 3:
                reason = "incomplete_benchmarks"
            elif any(not finite_number(e.get("mean", {}).get("reward")) or
                     not 0 <= e["mean"]["reward"] <= 1 or
                     not isinstance(e.get("safety"), dict) or
                     type(e["safety"].get("attemptCount")) is not int or e["safety"]["attemptCount"] <= 0 for e in evals):
                reason = "missing_measured_attempts"
            elif {e.get("datasetIndexName") for e in evals} != AGENT_COMPONENTS:
                raise ValueError("Coding Agent benchmark components changed; update the parser and methodology.")
            elif not math.isclose(score, sum(e["mean"]["reward"] for e in evals) / 3, abs_tol=1e-10):
                raise ValueError("Coding Agent index disagrees with measured components; check index methodology.")
        if reason:
            excluded.append({"id": agent.get("id"), "label": agent.get("displayLabel"), "reason": reason})
            continue
        creators = agent.get("modelCreators")
        if not isinstance(creators, list) or len(creators) != 1:
            raise ValueError(f"Ambiguous model developer for Coding Agent {agent.get('id')}.")
        label = agent.get("display", {}).get("model")
        if not isinstance(label, str):
            raise ValueError(f"Missing Coding Agent model label for {agent.get('id')}.")
        matches = names.get((creators[0].get("slug"), model_name_key(label)), {})
        if len(matches) != 1:
            raise ValueError(f"Cannot uniquely match Coding Agent model {label!r} to API catalog "
                             f"({len(matches)} matches). Refresh both sources or update name matching.")
        candidate = model_details(next(iter(matches.values())))
        if candidate is None:
            excluded.append({"id": agent["id"], "label": agent.get("displayLabel"), "reason": "no_public_api"})
            continue
        agent_name = agent.get("display", {}).get("agent")
        if not isinstance(agent_name, str) or not agent_name:
            raise ValueError(f"Missing agent name for {agent['id']}.")
        candidates.append({**candidate, "score": score * 100, "agent_id": agent["id"], "agent": agent_name,
                           "agent_model_label": label, "agent_url": AGENT_SOURCE + "#coding-agents-index"})
    return best_per_developer(candidates), excluded


def flag_path(country, output):
    if not isinstance(country, str) or not re.fullmatch(r"[a-z]{2}", country):
        raise ValueError(f"Missing or unsupported source country code: {country!r}. Do not infer a country.")
    bundled = SKILL_DIR / "assets" / "flags" / f"{country}.png"
    if bundled.exists():
        return bundled
    cached = output / ".flags" / f"{country}.png"
    if not cached.exists():
        code = "-".join(f"{0x1F1E6 + ord(char) - ord('a'):x}" for char in country)
        payload = download(FLAG_SOURCE + code + ".png")
        cached.parent.mkdir(exist_ok=True)
        cached.write_bytes(payload)
    return cached


def company_label(name):
    lines = textwrap.wrap(name, 24)
    escaped = [re.sub(r"([_{}$%&#])", r"\\\1", line).replace(" ", r"\ ") for line in lines]
    return "\n".join(r"$\mathbf{" + line + "}$" for line in escaped)


def input_icon(kind):
    """Small vector pictograms, shared by the bars and their legend."""
    from matplotlib.lines import Line2D
    from matplotlib.offsetbox import DrawingArea
    from matplotlib.patches import Arc, Circle, FancyBboxPatch, Polygon, Rectangle

    icon = DrawingArea(24, 24)
    icon.add_artist(FancyBboxPatch((.5, .5), 23, 23, boxstyle="round,pad=0,rounding_size=4",
                                  facecolor="white", edgecolor="#cbd1da", linewidth=.6))
    stroke = {"edgecolor": "#263342", "facecolor": "none", "linewidth": 1.25}

    def line(xs, ys):
        icon.add_artist(Line2D(xs, ys, color="#263342", linewidth=1.25, solid_capstyle="round"))

    if kind == "text":
        icon.add_artist(Rectangle((7, 5.5), 10, 13, **stroke))
        for y in (9, 12, 15):
            line([9.5, 14.5], [y, y])
    elif kind == "image":
        icon.add_artist(Rectangle((5.5, 6.5), 13, 11, **stroke))
        icon.add_artist(Circle((14.7, 14), 1.1, color="#263342"))
        line([6.5, 10, 13, 15, 17.5], [8, 12, 9, 11, 8])
    elif kind == "audio":
        icon.add_artist(FancyBboxPatch((10, 10), 4, 8, boxstyle="round,pad=0,rounding_size=2", **stroke))
        icon.add_artist(Arc((12, 13), 10, 12, theta1=180, theta2=360,
                            edgecolor="#263342", linewidth=1.25))
        line([12, 12], [7, 5])
        line([9, 15], [5, 5])
    elif kind == "video":
        icon.add_artist(Rectangle((5, 7), 10, 10, **stroke))
        icon.add_artist(Polygon([(15, 10), (19, 7), (19, 17), (15, 14)], closed=True, **stroke))
    else:
        raise ValueError(f"Unknown input icon: {kind}")
    return icon


def render_chart(rows, snapshot, output, reference, telegram, website, coding=False):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import is_color_like
    from matplotlib.font_manager import FontProperties
    from matplotlib.offsetbox import AnnotationBbox, OffsetImage
    from matplotlib.patches import Rectangle
    from matplotlib.transforms import ScaledTranslation
    from PIL import Image

    if not rows:
        raise ValueError("No eligible measured developer scores; existing output preserved.")
    font_dir = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
    regular = FontProperties(fname=str(font_dir / "DejaVuSans.ttf"))
    bold = FontProperties(fname=str(font_dir / "DejaVuSans-Bold.ttf"))
    plt.rcParams.update({"font.family": "DejaVu Sans", "svg.fonttype": "none",
                         "mathtext.fontset": "dejavusans", "savefig.facecolor": "white",
                         "hatch.linewidth": .6})
    width = max(14.5, 3 + len(rows) * .98)
    fig, ax = plt.subplots(figsize=(width, 9.4), dpi=180)
    fig.subplots_adjust(left=.062, right=.985, bottom=.36, top=.78)
    colors = [m["color"] if is_color_like(m["color"]) else "#626a75" for m in rows]
    bars = ax.bar(range(len(rows)), [m["score"] for m in rows], width=.70, color=colors, zorder=3)
    for bar, row in zip(bars, rows):
        if row["open_weights"]:
            bar.set_hatch("///")
            bar.set_edgecolor((1, 1, 1, .65))
            bar.set_linewidth(0)
    values = []
    for bar, row in zip(bars, rows):
        center = bar.get_x() + bar.get_width() / 2
        values.append(ax.annotate(f"{row['score']:.2f}", (center, row["score"]),
                                 xytext=(0, 7), textcoords="offset points", ha="center", va="bottom",
                                 fontproperties=regular, fontsize=12.5, color="#1b2027", zorder=4))
    labels = [company_label(m["company"]) + "\n" + "\n".join(textwrap.wrap(
        m["short_name"].replace(" with fallback", "; fallback"), 25)) +
        ("\n" + "\n".join(textwrap.wrap(m["agent"], 25)) if coding else "") for m in rows]
    ax.set_xticks(range(len(rows)), labels, rotation=58, ha="right", rotation_mode="anchor", fontsize=12)
    ax.tick_params(axis="x", length=0, pad=14)
    ax.tick_params(axis="y", length=0, pad=9, labelsize=12)
    ax.set_ylim(0, max(1, max(m["score"] for m in rows)) * 1.24)
    ax.set_xlim(-.65, len(rows) - .35)
    ax.set_axisbelow(True)
    ax.grid(axis="y", color="#d7dce2", linestyle=(0, (2, 4)), linewidth=.8)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_ylabel("Coding Agent Index, баллы" if coding else "Intelligence Index, баллы", fontsize=12.5, labelpad=11)
    fig.text(.062, .948, "Artificial Analysis Coding Agent Index" if coding else "Artificial Analysis Intelligence Index",
             fontproperties=bold, fontsize=22)
    fig.text(.062, .902, "Рейтинг разработчиков AI по лучшей модели в coding-агенте" if coding else
             "Рейтинг лучших разработчиков AI по их лучшей модели",
             fontproperties=regular, fontsize=15, color="#414a56")
    rule = ("Одна конфигурация на разработчика модели · без роутеров · API · без порога по баллам" if coding else
            f"Одна лучшая модель на компанию · API · результат ≥ {reference['name']} ({reference['score']:.2f})")
    fig.text(.062, .862, rule,
             fontproperties=regular, fontsize=11.5, color="#515965")
    for y, url in ((.954, telegram), (.925, website)):
        fig.text(.985, y, url, ha="right", fontproperties=regular, fontsize=11,
                 color="#414a56", url=url)
    fig.text(.062, .811, "Ввод модели:", fontproperties=regular, fontsize=10.5,
             color="#515965", va="center")
    for index, (kind, _, label) in enumerate(INPUT_MODALITIES):
        x = .155 + index * .079
        fig.add_artist(AnnotationBbox(input_icon(kind), (x, .811), xycoords=fig.transFigure,
                                      frameon=False, pad=0))
        fig.text(x, .811, label, transform=fig.transFigure + ScaledTranslation(18 / 72, 0, fig.dpi_scale_trans),
                 fontproperties=regular, fontsize=10.5, va="center", color="#515965")
    fig.add_artist(Rectangle((.51, .801), .022, .020, transform=fig.transFigure,
                             facecolor="#697586", edgecolor=(1, 1, 1, .65), linewidth=0, hatch="///"))
    fig.text(.542, .811, "Открытые веса модели", fontproperties=regular, fontsize=10.5,
             va="center", color="#515965")
    data_date = datetime.fromisoformat(snapshot["fetched_at"]).strftime("%d.%m.%Y")
    date_label = fig.text(.062, .064, f"{len(rows)} разработчиков · индекс v{snapshot['index_version']} · данные AA: {data_date} (UTC)",
             fontproperties=regular, fontsize=11, color="#515965")
    fig.text(.062, .039, "Флаги: страна разработчика по данным Artificial Analysis. Отбор и сортировка — по исходным точным баллам.",
             fontproperties=regular, fontsize=10.5, color="#515965")
    source_label = snapshot["source_url"].removeprefix("https://")
    fig.text(.062, .015, f"Источник: {source_label} · Флаги: Twemoji 14.0.2, CC BY 4.0.",
             fontproperties=regular, fontsize=10.5, color="#515965")

    # Use the rendered number's top edge, not a fixed distance in score units.
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    input_icons = []
    for bar, row, value in zip(bars, rows, values):
        center = bar.get_x() + bar.get_width() / 2
        count = len(row["input_modalities"])
        height_points = bar.get_window_extent(renderer).height * 72 / fig.dpi
        step = min(29, (height_points - 36) / (count - 1)) if count > 1 else 29
        inside = height_points >= 36 and step >= 24
        if not inside and count:
            step = 29
            value.set_position((0, count * step + 11))
        anchor = (center, 0 if inside else row["score"])
        for index, kind in enumerate(row["input_modalities"]):
            icon_box = AnnotationBbox(input_icon(kind), anchor, xybox=(0, 9 + index * step),
                                       boxcoords="offset points", box_alignment=(.5, 0),
                                       frameon=False, pad=0, zorder=4)
            ax.add_artist(icon_box)
            input_icons.append((bar, icon_box, inside, value))
    flags = []
    for row, value in zip(rows, values):
        bbox = value.get_window_extent(renderer)
        anchor_y = ax.transData.transform((0, row["score"]))[1]
        offset = (bbox.y1 - anchor_y) * 72 / fig.dpi + 7
        with Image.open(flag_path(row["country"], output)) as image:
            image = image.convert("RGBA")
            flag = OffsetImage(image, zoom=.33)
        flag_box = AnnotationBbox(flag, value.xy, xybox=(0, offset),
                                  boxcoords="offset points", box_alignment=(.5, 0), frameon=False, pad=0, zorder=5)
        ax.add_artist(flag_box)
        flags.append(flag_box)
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    gaps = [(flag.get_window_extent(renderer).y0 - value.get_window_extent(renderer).y1) * 72 / fig.dpi
            for flag, value in zip(flags, values)]
    label_gap = min(label.get_window_extent(renderer).y0 for label in ax.get_xticklabels())
    label_gap = (label_gap - date_label.get_window_extent(renderer).y1) * 72 / fig.dpi
    if label_gap < 8:
        plt.close(fig)
        raise ValueError("Layout check failed: model labels are too close to the footer.")
    if min(gaps) < 6:
        plt.close(fig)
        raise ValueError("Layout check failed: country flags are too close to score labels.")
    clearances = []
    for bar, icon, inside, value in input_icons:
        bounds, badge = bar.get_window_extent(renderer), icon.get_window_extent(renderer)
        if inside:
            clearances.append(min(badge.x0 - bounds.x0, bounds.x1 - badge.x1,
                                  badge.y0 - bounds.y0, bounds.y1 - badge.y1) * 72 / fig.dpi)
        elif badge.y1 > value.get_window_extent(renderer).y0:
            plt.close(fig)
            raise ValueError("Layout check failed: short-bar input icons overlap the score.")
    if clearances and min(clearances) < 0:
        plt.close(fig)
        raise ValueError("Layout check failed: input icons do not fit inside the bars.")
    for extension in ("png", "svg"):
        target = output / f"rating.{extension}"
        fig.savefig(target, dpi=180)
        if extension == "svg":
            clean = "\n".join(line.rstrip() for line in target.read_text(encoding="utf-8").splitlines()) + "\n"
            target.write_text(clean, encoding="utf-8", newline="\n")
    plt.close(fig)
    return {"minimum_flag_value_gap_points": round(min(gaps), 2),
            "minimum_label_footer_gap_points": round(label_gap, 2),
            "open_weight_bars_hatched": sum(row["open_weights"] for row in rows),
            "input_icons_shown": len(input_icons),
            "input_icons_above_short_bars": sum(not inside for _, _, inside, _ in input_icons),
            "minimum_input_icon_bar_clearance_points": round(min(clearances), 2) if clearances else None}


def write_result(rows, snapshot, output, args, coding=False, model_snapshot=None, excluded=None, reference=None):
    output.mkdir(parents=True, exist_ok=True)
    layout = render_chart(rows, snapshot, output, reference, args.telegram, args.website, coding=coding)
    fields = ["rank", "company", "country", "model", "score", "effort", "api_provider_count",
              "input_modalities", "open_weights", "url"]
    if coding:
        fields += ["agent", "agent_id", "agent_model_label", "agent_url"]
    with (output / "rating.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows({**row, "input_modalities": ";".join(row["input_modalities"])} for row in rows)
    (output / "snapshot.json").write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    metadata = {key: snapshot[key] for key in ("source_url", "fetched_at", "index_version")}
    metadata.update({"catalog_entries": len(snapshot["agents" if coding else "models"]), "developers_shown": len(rows),
                     "minimum_score_inclusive": reference["score"] if reference else None,
                     "score_filter": "at_least_reference_model" if reference else "none",
                     "estimated_scores_included": False,
                     "public_api_required": True,
                     "api_availability_field": "hostModelCount > 0 and aa_public_api_unavailable is False",
                     "restricted_effort": {},
                     "snapshot_sha256": hashlib.sha256(json.dumps(snapshot, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
                     "layout": layout})
    if reference:
        metadata["reference_model"] = reference
    catalog = model_snapshot if coding else snapshot
    if "public_api_markers" in catalog:
        metadata["public_api_markers"] = catalog["public_api_markers"]
    if coding:
        metadata.update({"grouped_by": "model_creator.id", "routers_included": False,
                         "score_scale": "indexScore * 100", "required_components": 3,
                         "model_catalog_fetched_at": model_snapshot["fetched_at"],
                         "model_catalog_source_url": model_snapshot["source_url"],
                         "model_catalog_sha256": hashlib.sha256(json.dumps(model_snapshot, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
                         "excluded_configurations": excluded})
    (output / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{'Coding agents' if coding else 'Intelligence'}: {len(rows)} developers from {metadata['catalog_entries']} entries; "
          f"AA v{snapshot['index_version']}; data {snapshot['fetched_at']}")
    print(f"Chart: {output / 'rating.png'}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("output"))
    parser.add_argument("--snapshot", type=Path, help="Reuse a saved model catalog; no model source refresh")
    parser.add_argument("--agents-snapshot", type=Path, help="Reuse a saved Coding Agent catalog")
    parser.add_argument("--only", choices=("models", "coding-agents", "both"), default="both")
    parser.add_argument("--telegram", default="https://t.me/warlocksu")
    parser.add_argument("--website", default="https://warlock.su")
    args = parser.parse_args(argv)
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8")) if args.snapshot else fetch_snapshot()
    if not isinstance(snapshot, dict) or not all(key in snapshot for key in ("models", "fetched_at", "index_version", "source_url")):
        raise ValueError("Snapshot must contain models, fetched_at, index_version, and source_url.")
    datetime.fromisoformat(snapshot["fetched_at"])
    reference = reference_model(snapshot["models"]) if args.only != "coding-agents" else None
    rows = select_models(snapshot["models"], reference["score"]) if reference else None
    agents_snapshot = None
    if args.only != "models":
        agents_snapshot = json.loads(args.agents_snapshot.read_text(encoding="utf-8")) if args.agents_snapshot else fetch_agents_snapshot()
        if not isinstance(agents_snapshot, dict) or not all(key in agents_snapshot for key in ("agents", "fetched_at", "index_version", "source_url")):
            raise ValueError("Agent snapshot must contain agents, fetched_at, index_version, and source_url.")
        datetime.fromisoformat(agents_snapshot["fetched_at"])
        if agents_snapshot["index_version"] != "2.0":
            raise ValueError("Coding Agent index methodology changed; update the three-component validation before running.")
        agents, excluded = select_agents(agents_snapshot["agents"], snapshot["models"])
        if not agents:
            raise ValueError("No eligible measured Coding Agent configurations; existing output preserved.")
    if rows is not None:
        write_result(rows, snapshot, args.output, args, reference=reference)
    if agents_snapshot is not None:
        write_result(agents, agents_snapshot, args.output / "coding-agents", args, coding=True,
                     model_snapshot=snapshot, excluded=excluded)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Rating failed: {error}", file=sys.stderr)
        sys.exit(1)
