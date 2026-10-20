#!/usr/bin/env python3
"""Fetch Artificial Analysis and draw each developer's best measured API model."""

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
from datetime import datetime, timezone
from urllib.parse import urljoin
from urllib.request import Request, urlopen

SOURCE = "https://artificialanalysis.ai/models/comparisons"
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


def parse_page(page):
    """Read JSON-encoded Next.js flight strings without executing site code."""
    chunks = []
    for match in re.finditer(r"self\.__next_f\.push\((\[.*?\])\)</script>", page):
        item = json.loads(match.group(1))
        if len(item) > 1 and isinstance(item[1], str):
            chunks.append(item[1])
    flight = "".join(chunks)
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


def decode_catalog(payload, key_hex):
    """Decode the same public catalog payload used by the site's client."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    key = bytes.fromhex(key_hex)
    iv = hashlib.sha256(key).digest()[:12]
    return json.loads(gzip.decompress(AESGCM(key).decrypt(iv, payload, None)))


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
    return {"source_url": SOURCE, "fetched_at": datetime.now(timezone.utc).isoformat(),
            "index_version": version, "models": models}


def select_models(models, min_score=35):
    best = {}
    for model in models:
        score = model.get("intelligenceIndex")
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score):
            continue
        if model.get("intelligenceIndexIsEstimated") is not False:
            continue
        hosts = model.get("hostModelCount")
        if type(hosts) is not int or hosts < 0:
            raise ValueError(
                f"Missing or invalid API availability (hostModelCount) for {model.get('slug', '?')}. "
                "Refresh the source snapshot; if the source schema changed, update the fetcher. "
                "Do not infer API availability.")
        if hosts == 0:
            continue
        creator = model.get("creator") or {}
        if not all(creator.get(key) for key in ("id", "slug", "name")):
            raise ValueError(f"Missing developer identity for model {model.get('slug', '?')}.")
        effort = (model.get("effort") or {}).get("slug")
        modalities = []
        for kind, field, _ in INPUT_MODALITIES:
            if type(model.get(field)) is not bool:
                raise ValueError(f"Missing or invalid input modality {field} for {model.get('slug', '?')}. "
                                 "Refresh the snapshot or update the source parser; do not infer support.")
            if model[field]:
                modalities.append(kind)
        candidate = {"company": creator["name"], "creator_id": creator["id"],
                     "company_slug": creator["slug"], "country": creator.get("country"),
                     "color": creator.get("color") or "#626a75", "model": model["name"],
                     "short_name": model.get("shortName") or model["name"],
                     "score": score, "effort": effort, "api_provider_count": hosts, "slug": model["slug"],
                     "input_modalities": modalities,
                     "url": "https://artificialanalysis.ai/models/" + model["slug"]}
        previous = best.get(creator["id"])
        if previous is None or (-score, candidate["slug"]) < (-previous["score"], previous["slug"]):
            best[creator["id"]] = candidate
    rows = sorted((m for m in best.values() if m["score"] >= min_score),
                  key=lambda m: (-m["score"], m["company"], m["slug"]))
    for rank, row in enumerate(rows, 1):
        row["rank"] = rank
    return rows


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


def render_chart(rows, snapshot, output, min_score, telegram, website):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import is_color_like
    from matplotlib.font_manager import FontProperties
    from matplotlib.offsetbox import AnnotationBbox, OffsetImage
    from matplotlib.transforms import ScaledTranslation
    from PIL import Image

    if not rows:
        raise ValueError(f"No measured eligible developer scores at least {min_score:g}.")
    font_dir = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
    regular = FontProperties(fname=str(font_dir / "DejaVuSans.ttf"))
    bold = FontProperties(fname=str(font_dir / "DejaVuSans-Bold.ttf"))
    plt.rcParams.update({"font.family": "DejaVu Sans", "svg.fonttype": "none",
                         "mathtext.fontset": "dejavusans", "savefig.facecolor": "white"})
    width = max(14.5, 3 + len(rows) * .98)
    fig, ax = plt.subplots(figsize=(width, 9.4), dpi=180)
    fig.subplots_adjust(left=.062, right=.985, bottom=.32, top=.78)
    colors = [m["color"] if is_color_like(m["color"]) else "#626a75" for m in rows]
    bars = ax.bar(range(len(rows)), [m["score"] for m in rows], width=.70, color=colors, zorder=3)
    values = []
    for bar, row in zip(bars, rows):
        center = bar.get_x() + bar.get_width() / 2
        values.append(ax.annotate(f"{row['score']:.2f}", (center, row["score"]),
                                 xytext=(0, 7), textcoords="offset points", ha="center", va="bottom",
                                 fontproperties=regular, fontsize=12.5, color="#1b2027", zorder=4))
    labels = [company_label(m["company"]) + "\n" + "\n".join(textwrap.wrap(
        m["short_name"].replace(" with fallback", "; fallback"), 25)) for m in rows]
    ax.set_xticks(range(len(rows)), labels, rotation=58, ha="right", rotation_mode="anchor", fontsize=12)
    ax.tick_params(axis="x", length=0, pad=14)
    ax.tick_params(axis="y", length=0, pad=9, labelsize=12)
    ax.set_ylim(0, max(m["score"] for m in rows) * 1.24)
    ax.set_xlim(-.65, len(rows) - .35)
    ax.set_axisbelow(True)
    ax.grid(axis="y", color="#d7dce2", linestyle=(0, (2, 4)), linewidth=.8)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_ylabel("Intelligence Index, баллы", fontsize=12.5, labelpad=11)
    fig.text(.062, .948, "Artificial Analysis Intelligence Index", fontproperties=bold, fontsize=22)
    fig.text(.062, .902, "Рейтинг лучших разработчиков AI по их лучшей модели",
             fontproperties=regular, fontsize=15, color="#414a56")
    fig.text(.062, .862, f"Одна лучшая модель на компанию · доступна по API · измеренные результаты ≥ {min_score:g}",
             fontproperties=regular, fontsize=11.5, color="#515965")
    for y, url in ((.954, telegram), (.925, website)):
        fig.text(.985, y, url, ha="right", fontproperties=regular, fontsize=11,
                 color="#414a56", url=url)
    fig.text(.062, .811, "Ввод (AA):", fontproperties=regular, fontsize=10.5,
             color="#515965", va="center")
    for index, (kind, _, label) in enumerate(INPUT_MODALITIES):
        x = .13 + index * .079
        fig.add_artist(AnnotationBbox(input_icon(kind), (x, .811), xycoords=fig.transFigure,
                                      frameon=False, pad=0))
        fig.text(x, .811, label, transform=fig.transFigure + ScaledTranslation(18 / 72, 0, fig.dpi_scale_trans),
                 fontproperties=regular, fontsize=10.5, va="center", color="#515965")
    data_date = datetime.fromisoformat(snapshot["fetched_at"]).strftime("%d.%m.%Y")
    fig.text(.062, .064, f"{len(rows)} разработчиков · индекс v{snapshot['index_version']} · данные AA: {data_date} (UTC)",
             fontproperties=regular, fontsize=11, color="#515965")
    fig.text(.062, .039, "Флаги: страна разработчика по данным Artificial Analysis. Отбор и сортировка — по исходным точным баллам.",
             fontproperties=regular, fontsize=10.5, color="#515965")
    fig.text(.062, .015, "Источник: artificialanalysis.ai/models/comparisons · Флаги: Twemoji 14.0.2, CC BY 4.0.",
             fontproperties=regular, fontsize=10.5, color="#515965")

    # Use the rendered number's top edge, not a fixed distance in score units.
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    input_icons = []
    for bar, row in zip(bars, rows):
        center = bar.get_x() + bar.get_width() / 2
        for index, kind in enumerate(row["input_modalities"]):
            icon_box = AnnotationBbox(input_icon(kind), (center, 0), xybox=(0, 9 + index * 29),
                                       boxcoords="offset points", box_alignment=(.5, 0),
                                       frameon=False, pad=0, zorder=4)
            ax.add_artist(icon_box)
            input_icons.append((bar, icon_box))
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
    if min(gaps) < 6:
        plt.close(fig)
        raise ValueError("Layout check failed: country flags are too close to score labels.")
    clearances = []
    for bar, icon in input_icons:
        bounds, badge = bar.get_window_extent(renderer), icon.get_window_extent(renderer)
        clearances.append(min(badge.x0 - bounds.x0, bounds.x1 - badge.x1,
                              badge.y0 - bounds.y0, bounds.y1 - badge.y1) * 72 / fig.dpi)
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
            "input_icons_shown": len(input_icons),
            "minimum_input_icon_bar_clearance_points": round(min(clearances), 2) if clearances else None}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("output"))
    parser.add_argument("--snapshot", type=Path, help="Reuse a previously saved snapshot; no source refresh")
    parser.add_argument("--min-score", type=float, default=35)
    parser.add_argument("--telegram", default="https://t.me/warlocksu")
    parser.add_argument("--website", default="https://warlock.su")
    args = parser.parse_args(argv)
    if not math.isfinite(args.min_score):
        parser.error("--min-score must be finite")
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8")) if args.snapshot else fetch_snapshot()
    if not isinstance(snapshot, dict) or not all(key in snapshot for key in ("models", "fetched_at", "index_version", "source_url")):
        raise ValueError("Snapshot must contain models, fetched_at, index_version, and source_url.")
    datetime.fromisoformat(snapshot["fetched_at"])
    rows = select_models(snapshot["models"], args.min_score)
    args.output.mkdir(parents=True, exist_ok=True)
    layout = render_chart(rows, snapshot, args.output, args.min_score, args.telegram, args.website)
    fields = ["rank", "company", "country", "model", "score", "effort", "api_provider_count", "input_modalities", "url"]
    with (args.output / "rating.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows({**row, "input_modalities": ";".join(row["input_modalities"])} for row in rows)
    (args.output / "snapshot.json").write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    metadata = {key: snapshot[key] for key in ("source_url", "fetched_at", "index_version")}
    metadata.update({"catalog_entries": len(snapshot["models"]), "developers_shown": len(rows),
                     "minimum_score_inclusive": args.min_score, "estimated_scores_included": False,
                     "public_api_required": True, "api_availability_field": "hostModelCount > 0",
                     "restricted_effort": {},
                     "snapshot_sha256": hashlib.sha256(json.dumps(snapshot, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
                     "layout": layout})
    (args.output / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(rows)} developers from {len(snapshot['models'])} entries; AA v{snapshot['index_version']}; data {snapshot['fetched_at']}")
    print(f"Chart: {args.output / 'rating.png'}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Rating failed: {error}", file=sys.stderr)
        sys.exit(1)
