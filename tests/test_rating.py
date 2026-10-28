import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "skills/ai-fair-rating/scripts/rating.py"
spec = importlib.util.spec_from_file_location("rating", SCRIPT)
rating = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rating)


def model(slug, score, creator="example", effort=None, estimated=False, **extra):
    return {"slug": slug, "name": slug, "shortName": slug, "intelligenceIndex": score,
            "intelligenceIndexIsEstimated": estimated,
            "hostModelCount": 1,
            "aa_public_api_unavailable": False,
            "isOpenWeights": False,
            "inputModalityText": True, "inputModalityImage": False,
            "inputModalitySpeech": False, "inputModalityVideo": False,
            "creator": {"id": creator, "slug": creator, "name": creator, "country": "us", "color": "#123456"},
            "effort": {"slug": effort} if effort else None, **extra}


def agent(identifier, label, score, creator="example", **extra):
    return {"id": identifier, "displayLabel": "Harness - " + label,
            "display": {"model": label, "agent": "Harness"},
            "modelCreators": [{"slug": creator}], "agentCreator": {"slug": "unrelated-harness-company"},
            "isRouter": False, "isUnavailable": False, "indexComponentCount": 3,
            "indexScore": score, "evals": [{"datasetIndexName": component, "mean": {"reward": score},
            "safety": {"attemptCount": 3}} for component in sorted(rating.AGENT_COMPONENTS)], **extra}


def agent_page(rows, declared=None):
    if declared is None:
        declared = sum(r.get("isRouter") is False for r in rows if isinstance(r, dict))
    record = ["$", "div", None, {"benchmarkRows": rows}]
    return ('Artificial Analysis Coding Agent Index v2.0 1 of ' + str(declared) + ' models'
            '<script>self.__next_f.push(' + json.dumps([1, 'a:' + json.dumps(record) + '\n']) + ')</script>')


class SelectionTests(unittest.TestCase):
    def test_reference_threshold_tracks_current_best_measured_setting(self):
        release = {"slug": rating.REFERENCE_RELEASE}
        reference = model("reference-xhigh", 20.1068756031705, "alibaba", "xhigh", release=release)
        models = [reference, model("reference-low", 19, "alibaba", "low", release=release),
                  model("reference-estimate", 80, "alibaba", "max", estimated=True, release=release),
                  model("reference-unavailable", 90, "alibaba", "max", hostModelCount=0, release=release),
                  model("equal", reference["intelligenceIndex"], "equal"),
                  model("below", reference["intelligenceIndex"] - .0000000001, "below"),
                  model("above", reference["intelligenceIndex"] + .0000000001, "above")]
        self.assertEqual(rating.reference_model(models)["slug"], "reference-xhigh")
        self.assertEqual({r["slug"] for r in rating.select_models(models)}, {"reference-xhigh", "equal", "above"})
        reference["intelligenceIndex"] = 21
        self.assertEqual([r["slug"] for r in rating.select_models(models)], ["reference-xhigh"])

    def test_missing_or_unmeasured_reference_is_an_error(self):
        for entries in ([], [model("only-unrelated", 50)],
                        [model("reference", None, release={"slug": rating.REFERENCE_RELEASE})],
                        [model("reference", 50, estimated=True, release={"slug": rating.REFERENCE_RELEASE})]):
            with self.subTest(entries=entries), self.assertRaisesRegex(ValueError, "reference release"):
                rating.select_models(entries)

    def test_measured_winner_and_inclusive_threshold(self):
        rows = rating.select_models([
            model("estimate", 90, estimated=True), model("measured", 41.123456),
            model("almost-equal", 41.123455), model("at-threshold", 35, "threshold"),
            model("below", 34.99999, "below"), model("no-score", None, "missing"),
            model("nan", float("nan"), "nan"), model("boolean", True, "bool"),
            model("unknown-status", 80, "unknown", estimated=None),
        ], min_score=35)
        self.assertEqual([m["slug"] for m in rows], ["measured", "at-threshold"])
        self.assertEqual(rows[0]["score"], 41.123456)

    def test_unrestricted_effort_and_creator_grouping(self):
        models = []
        for creator in ("openai", "anthropic", "other"):
            models.extend([model(creator + "-max", 70, creator, "max"),
                           model(creator + "-high", 60, creator, "high"),
                           model(creator + "-xhigh", 45, creator, "xhigh"),
                           model(creator + "-old", 44, creator, "xhigh")])
        rows = rating.select_models(models, min_score=35)
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(m["effort"] == "max" for m in rows))
        self.assertEqual(len({m["creator_id"] for m in rows}), 3)

    def test_selects_best_score_rather_than_effort_label(self):
        rows = rating.select_models([
            model("max", 40, "openai", "max"), model("high", 42, "openai", "high"),
            model("lower-exact-score", 41.999999, "another", "max"),
        ], min_score=35)
        self.assertEqual([row["slug"] for row in rows], ["high", "lower-exact-score"])

    def test_api_filter_applies_before_best_model_for_every_developer(self):
        for creator in ("openai", "anthropic", "meta", "other"):
            with self.subTest(creator=creator):
                rows = rating.select_models([
                    model("offline-best", 90, creator, "max", hostModelCount=0),
                    model("marked-unavailable", 91, creator, "max", hostModelCount=9, aa_public_api_unavailable=True),
                    model("online-estimate", 95, creator, "max", estimated=True),
                    model("online-best", 52, creator, "max", hostModelCount=2),
                    model("online-older", 48, creator, "xhigh"),
                ], min_score=35)
                self.assertEqual([row["slug"] for row in rows], ["online-best"])
                self.assertEqual(rows[0]["api_provider_count"], 2)

    def test_missing_or_malformed_api_marker_is_not_treated_as_available(self):
        for marker in (None, 0, 1, "false"):
            with self.subTest(marker=marker), self.assertRaisesRegex(ValueError, "AA public API marker"):
                rating.select_models([model("unknown", 60, aa_public_api_unavailable=marker)], min_score=35)
        old_snapshot_model = model("old", 60)
        del old_snapshot_model["aa_public_api_unavailable"]
        with self.assertRaisesRegex(ValueError, "fresh model snapshot"):
            rating.select_models([old_snapshot_model], min_score=35)

    def test_reference_also_excludes_explicit_no_api_marker(self):
        release = {"slug": rating.REFERENCE_RELEASE}
        reference = model("reference", 20, release=release)
        marked = model("marked-reference", 50, release=release, hostModelCount=3, aa_public_api_unavailable=True)
        self.assertEqual(rating.reference_model([marked, reference])["score"], 20)
        with self.assertRaisesRegex(ValueError, "reference release"):
            rating.reference_model([marked])

    def test_model_names_are_not_excluded_when_api_becomes_available(self):
        full = model("muse-wonder-full", 56, "meta", "max", hostModelCount=0)
        wonder = model("muse-wonder", 52.393894697293, "meta", "max")
        self.assertEqual(rating.select_models([full, wonder], min_score=35)[0]["slug"], "muse-wonder")
        full["hostModelCount"] = 1
        self.assertEqual(rating.select_models([full, wonder], min_score=35)[0]["slug"], "muse-wonder-full")

    def test_missing_or_malformed_api_availability_fails(self):
        for count in (None, True, False, -1, 1.0, "1"):
            with self.subTest(count=count), self.assertRaisesRegex(ValueError, "hostModelCount"):
                rating.select_models([model("unknown-api", 60, hostModelCount=count)], min_score=35)
        missing = model("missing-api", 60)
        del missing["hostModelCount"]
        with self.assertRaisesRegex(ValueError, "hostModelCount"):
            rating.select_models([missing], min_score=35)

    def test_input_modalities_belong_to_selected_model(self):
        rows = rating.select_models([
            model("winner", 50, inputModalityImage=True, inputModalitySpeech=True, inputModalityVideo=True),
            model("older", 40, isOpenWeights=True), model("text-only", 39, "another", isOpenWeights=True),
        ], min_score=35)
        self.assertEqual(rows[0]["input_modalities"], ["text", "image", "audio", "video"])
        self.assertEqual(rows[1]["input_modalities"], ["text"])
        self.assertFalse(rows[0]["open_weights"])
        self.assertTrue(rows[1]["open_weights"])

    def test_missing_or_malformed_open_weight_status_fails(self):
        for invalid in (None, 0, 1, "true"):
            with self.subTest(value=invalid), self.assertRaisesRegex(ValueError, "isOpenWeights"):
                rating.select_models([model("unknown-weights", 40, isOpenWeights=invalid)], min_score=35)

    def test_missing_or_malformed_input_modalities_fail(self):
        for _, field, _ in rating.INPUT_MODALITIES:
            for invalid in (None, 0, 1, "true"):
                with self.subTest(field=field, value=invalid), self.assertRaisesRegex(ValueError, field):
                    rating.select_models([model("bad-modality", 40, **{field: invalid})], min_score=35)


class SourceTests(unittest.TestCase):
    def test_explicit_api_marker_parser_and_fetch_enrichment(self):
        identifier = "909ed0ba-bcc5-4f38-8162-08a4e187a772"
        script = ('let unrelated=new Set(["not-an-api-id"]);'
                  'let s=new Set(["' + identifier + '"]),p="checkered",l={[p]:t.I.notPubliclyAvailable};')
        self.assertEqual(rating.parse_unavailable_api_ids(script), [identifier])
        self.assertIsNone(rating.parse_unavailable_api_ids('let unrelated=new Set(["anything"]);'))
        self.assertEqual(rating.parse_unavailable_api_ids(script.replace('"' + identifier + '"', '')), [])
        with self.assertRaisesRegex(ValueError, "Invalid"):
            rating.parse_unavailable_api_ids(script.replace(identifier, "bad-id"))
        with self.assertRaisesRegex(ValueError, "Ambiguous"):
            rating.parse_unavailable_api_ids(script + script)

        manifest = {"path": "/data/catalog.txt", "key": "ab" * 32}
        page = ('Intelligence Index v5.0 2 of 2 models<script src="/_next/static/chunks/availability.js"></script>'
                '<script>self.__next_f.push(' + json.dumps([1, json.dumps({"manifest": manifest})]) + ')</script>')
        models = [model("unavailable", 60, id=identifier, hostModelCount=1), model("available", 40, id="other-id")]
        payloads = {rating.SOURCE: page.encode(), "https://artificialanalysis.ai/data/catalog.txt": b"encrypted",
                    "https://artificialanalysis.ai/_next/static/chunks/availability.js": script.encode()}
        with patch.object(rating, "download", side_effect=lambda url: payloads[url]), patch.object(
                rating, "decode_catalog", return_value={"models": models}):
            snapshot = rating.fetch_snapshot()
        self.assertTrue(snapshot["models"][0]["aa_public_api_unavailable"])
        self.assertFalse(snapshot["models"][1]["aa_public_api_unavailable"])
        self.assertEqual(snapshot["public_api_markers"]["unavailable_model_ids"], [identifier])
        self.assertEqual([r["slug"] for r in rating.select_models(snapshot["models"], min_score=35)], ["available"])
        with patch.object(rating, "download", return_value=b"client schema changed"), self.assertRaisesRegex(ValueError, "marker catalog"):
            rating.fetch_api_markers(page)

    def test_agent_full_catalog_references_not_highlights(self):
        first = agent("one", "first", .5)
        second = agent("two", "second", .4)
        flight = 'b:' + json.dumps(["$", "div", None, {"rows": [first]}]) + '\n'
        flight += 'a:' + json.dumps(["$", "div", None, {"benchmarkRows": ["$b:props:rows:0", second]}]) + '\n'
        page = ('Coding Agent Index v2.0 1 of 2 models<script>self.__next_f.push('
                + json.dumps([1, flight]) + ')</script>')
        rows, version = rating.parse_agents_page(page)
        self.assertEqual(([r["id"] for r in rows], version), (["one", "two"], "2.0"))
        for bad_page in (agent_page([first], declared=2), agent_page([first, first], declared=2),
                         agent_page(["$ff:props:rows:0"], declared=1), 'Coding Agent Index v2.0 1 of 1 models'):
            with self.subTest(page=bad_page[:80]), self.assertRaises(ValueError):
                rating.parse_agents_page(bad_page)

    def test_public_payload_decoding(self):
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        key = bytes(range(32))
        expected = {"models": [model("full-catalog", 40)]}
        compressed = gzip.compress(json.dumps(expected).encode())
        encrypted = AESGCM(key).encrypt(hashlib.sha256(key).digest()[:12], compressed, None)
        self.assertEqual(rating.decode_catalog(encrypted, key.hex()), expected)

    def test_manifest_and_catalog_size(self):
        manifest = {"path": "/data/catalog.txt", "key": "ab" * 32}
        flight = json.dumps({"initialModels": [model("initial", 1)], "manifest": manifest})
        page = ('Artificial Analysis Intelligence Index v4.3.2 27 of 706 models'
                '<script>self.__next_f.push(' + json.dumps([1, flight]) + ')</script>')
        manifests, version, count = rating.parse_page(page)
        self.assertEqual(manifests, [manifest])
        self.assertEqual((version, count), ("4.3.2", 706))
        with self.assertRaisesRegex(ValueError, "manifest"):
            rating.parse_page('<script>initialModels=[]</script>')


class AgentSelectionTests(unittest.TestCase):
    def test_no_api_marker_wins_over_provider_count_in_coding_results(self):
        models = [model("best", None, hostModelCount=1, aa_public_api_unavailable=True), model("available", None)]
        rows, excluded = rating.select_agents([agent("best", "best", .9), agent("available", "available", .4)], models)
        self.assertEqual([r["slug"] for r in rows], ["available"])
        self.assertEqual(excluded[0]["reason"], "no_public_api")

    def test_measured_api_best_by_model_developer_without_score_threshold(self):
        models = [model("first", None, estimated=True), model("second", None),
                  model("offline", None, hostModelCount=0), model("threshold", None, "another"),
                  model("below", None, "third"), model("zero", None, "fourth")]
        rows, excluded = rating.select_agents([
            agent("one", "first", .500000001), agent("two", "second", .5),
            agent("offline", "offline", .9), agent("estimated", "second", .95, indexScoreIsEstimated=True),
            agent("unavailable", "second", .96, isUnavailable=True),
            agent("router", "not-in-model-catalog", .99, isRouter=True),
            agent("partial", "second", .97, indexComponentCount=2),
            agent("missing", "second", None), agent("edge", "threshold", .35, "another"),
            agent("below", "below", .349999999, "third"),
            agent("zero", "zero", 0, "fourth"),
        ], models)
        self.assertEqual([r["slug"] for r in rows], ["first", "threshold", "below", "zero"])
        self.assertEqual(rows[0]["agent_id"], "one")
        self.assertEqual(rows[0]["company"], "example")
        self.assertEqual(rows[0]["score"], .500000001 * 100)
        self.assertTrue({"no_public_api", "estimated_score", "unavailable_configuration", "mixed_model_router",
                         "incomplete_benchmarks", "missing_score"}.issubset({r["reason"] for r in excluded}))

    def test_catalog_matching_preserves_release_and_effort(self):
        models = [model("old", 40, name="Model Max", shortName="Model Max"),
                  model("new", 45, name="Model Max (0902)", shortName="Model Max (0902)")]
        rows, _ = rating.select_agents([agent("one", "Model Max", .5)], models)
        self.assertEqual(rows[0]["slug"], "old")
        for bad_models in ([], models + [model("duplicate", 50, name="Model Max")]):
            with self.assertRaisesRegex(ValueError, "uniquely match"):
                rating.select_agents([agent("one", "Model Max", .5)], bad_models)

    def test_schema_and_measurement_failures(self):
        a = agent("one", "first", .5)
        for changed in ({"indexScore": 50}, {"isUnavailable": None},
                        {"indexScore": .7}, {"modelCreators": []}):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                rating.select_agents([{**a, **changed}], [model("first", 40)])
        a["evals"][0]["safety"]["attemptCount"] = 0
        self.assertEqual(rating.select_agents([a], [model("first", 40)])[0], [])


class OutputTests(unittest.TestCase):
    def test_coding_only_renders_zero_without_a_reference_or_score_cutoff(self):
        models = {"source_url": rating.SOURCE, "fetched_at": "2026-10-28T21:00:00+00:00",
                  "index_version": "5.0", "models": [model("zero", None, inputModalityImage=True,
                  inputModalitySpeech=True, inputModalityVideo=True)]}
        agents = {"source_url": rating.AGENT_SOURCE, "fetched_at": "2026-10-28T21:00:00+00:00",
                  "index_version": "2.0", "agents": [agent("one", "zero", 0)]}
        with tempfile.TemporaryDirectory() as directory, patch.object(rating, "fetch_snapshot", return_value=models), patch.object(
                rating, "fetch_agents_snapshot", return_value=agents):
            rating.main(["--only", "coding-agents", "--output", directory])
            result = Path(directory) / "coding-agents"
            metadata = json.loads((result / "metadata.json").read_text())
            self.assertIsNone(metadata["minimum_score_inclusive"])
            self.assertEqual(metadata["developers_shown"], 1)
            self.assertEqual(metadata["layout"]["input_icons_above_short_bars"], 4)
            self.assertGreaterEqual(metadata["layout"]["minimum_flag_value_gap_points"], 6)
            self.assertTrue((result / "rating.png").exists())

    def test_snapshot_replay_and_flag_clearance(self):
        from PIL import Image

        snapshot = {"source_url": rating.SOURCE, "fetched_at": "2026-10-15T20:00:00+00:00",
                    "index_version": "4.3.2", "models": [model("first", 41.123456, inputModalityImage=True,
                    inputModalitySpeech=True, inputModalityVideo=True), model("second", 35, "second", isOpenWeights=True,
                    release={"slug": rating.REFERENCE_RELEASE})]}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.json"
            source.write_text(json.dumps(snapshot), encoding="utf-8")
            output = root / "result"
            rating.main(["--only", "models", "--snapshot", str(source), "--output", str(output)])
            metadata = json.loads((output / "metadata.json").read_text())
            self.assertEqual(metadata["fetched_at"], snapshot["fetched_at"])
            self.assertEqual(metadata["developers_shown"], 2)
            self.assertEqual(metadata["minimum_score_inclusive"], 35)
            self.assertEqual(metadata["reference_model"]["slug"], "second")
            self.assertTrue(metadata["public_api_required"])
            self.assertEqual(metadata["restricted_effort"], {})
            self.assertGreaterEqual(metadata["layout"]["minimum_flag_value_gap_points"], 6)
            self.assertGreaterEqual(metadata["layout"]["minimum_label_footer_gap_points"], 8)
            self.assertEqual(metadata["layout"]["input_icons_shown"], 5)
            self.assertEqual(metadata["layout"]["open_weight_bars_hatched"], 1)
            self.assertGreaterEqual(metadata["layout"]["minimum_input_icon_bar_clearance_points"], 0)
            self.assertIn("41.123456", (output / "rating.csv").read_text(encoding="utf-8-sig"))
            self.assertIn("text;image;audio;video", (output / "rating.csv").read_text(encoding="utf-8-sig"))
            self.assertIn("https://t.me/warlocksu", (output / "rating.svg").read_text(encoding="utf-8"))
            self.assertIn("<pattern", (output / "rating.svg").read_text(encoding="utf-8"))
            with Image.open(output / "rating.png") as image:
                self.assertGreater(image.width, 2000)
                image.verify()

    def test_default_builds_both_and_replays_separate_snapshots(self):
        snapshot = {"source_url": rating.SOURCE, "fetched_at": "2026-10-28T21:00:00+00:00",
                    "index_version": "5.0", "models": [model("first", 41, release={"slug": rating.REFERENCE_RELEASE})]}
        agents_snapshot = {"source_url": rating.AGENT_SOURCE, "fetched_at": "2026-10-28T22:00:00+00:00",
                           "index_version": "2.0", "agents": [agent("one", "first", .51)]}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(rating, "fetch_snapshot", return_value=snapshot), patch.object(
                    rating, "fetch_agents_snapshot", return_value=agents_snapshot):
                rating.main(["--output", str(root / "fresh")])
            rating.main(["--snapshot", str(root / "fresh/snapshot.json"), "--agents-snapshot",
                         str(root / "fresh/coding-agents/snapshot.json"), "--output", str(root / "replay")])
            for folder, date in (("", snapshot["fetched_at"]), ("coding-agents", agents_snapshot["fetched_at"])):
                result = root / "replay" / folder
                self.assertTrue((result / "rating.png").exists())
                metadata = json.loads((result / "metadata.json").read_text())
                self.assertEqual(metadata["fetched_at"], date)
                self.assertGreaterEqual(metadata["layout"]["minimum_flag_value_gap_points"], 6)
                self.assertGreaterEqual(metadata["layout"]["minimum_label_footer_gap_points"], 8)
            self.assertEqual(metadata["model_catalog_fetched_at"], snapshot["fetched_at"])
            self.assertFalse(metadata["routers_included"])
            self.assertIsNone(metadata["minimum_score_inclusive"])
            self.assertEqual(metadata["score_filter"], "none")
            self.assertIn("Harness", (root / "replay/coding-agents/rating.csv").read_text(encoding="utf-8-sig"))
            preserved = root / "replay/rating.png"
            before = preserved.read_bytes()
            with patch.object(rating, "fetch_snapshot", return_value=snapshot), patch.object(
                    rating, "fetch_agents_snapshot", side_effect=ValueError("source changed")):
                with self.assertRaisesRegex(ValueError, "source changed"):
                    rating.main(["--output", str(root / "replay")])
            self.assertEqual(preserved.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
