import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "skills/ai-fair-rating/scripts/rating.py"
spec = importlib.util.spec_from_file_location("rating", SCRIPT)
rating = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rating)


def model(slug, score, creator="example", effort=None, estimated=False, **extra):
    return {"slug": slug, "name": slug, "shortName": slug, "intelligenceIndex": score,
            "intelligenceIndexIsEstimated": estimated,
            "creator": {"id": creator, "slug": creator, "name": creator, "country": "us", "color": "#123456"},
            "effort": {"slug": effort} if effort else None, **extra}


class SelectionTests(unittest.TestCase):
    def test_measured_winner_and_inclusive_threshold(self):
        rows = rating.select_models([
            model("estimate", 90, estimated=True), model("measured", 41.123456),
            model("duplicate", 40), model("at-threshold", 35, "threshold"),
            model("below", 34.99999, "below"), model("no-score", None, "missing"),
            model("nan", float("nan"), "nan"), model("boolean", True, "bool"),
            model("unknown-status", 80, "unknown", estimated=None),
        ])
        self.assertEqual([m["slug"] for m in rows], ["measured", "at-threshold"])
        self.assertEqual(rows[0]["score"], 41.123456)

    def test_effort_limits_and_creator_grouping(self):
        models = []
        for creator in ("openai", "anthropic"):
            models.extend([model(creator + "-max", 70, creator, "max"),
                           model(creator + "-high", 60, creator, "high"),
                           model(creator + "-xhigh", 45, creator, "xhigh"),
                           model(creator + "-old", 44, creator, "xhigh")])
        models += [model("other-max", 47, "other", "max"), model("other-low", 40, "other", "low")]
        rows = rating.select_models(models)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["slug"], "other-max")
        self.assertTrue(all(m["effort"] == "xhigh" for m in rows[1:]))
        self.assertEqual(len({m["creator_id"] for m in rows}), 3)

    def test_no_fallback_to_max(self):
        self.assertEqual(rating.select_models([model("only-max", 90, "openai", "max")]), [])

    def test_meta_uses_wonder_instead_of_full_or_its_effort_variants(self):
        rows = rating.select_models([
            model("muse-wonder-full", 56, "meta", "max"),
            model("muse-wonder-full-xhigh", 55, "meta", "xhigh", release={"slug": "muse-wonder-full"}),
            model("muse-wonder", 52.393894697293, "meta", "max"),
            model("muse-spark-1-3", 48, "meta", "max"),
        ])
        self.assertEqual([row["slug"] for row in rows], ["muse-wonder"])


class SourceTests(unittest.TestCase):
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


class OutputTests(unittest.TestCase):
    def test_snapshot_replay_and_flag_clearance(self):
        from PIL import Image

        snapshot = {"source_url": rating.SOURCE, "fetched_at": "2026-10-15T20:00:00+00:00",
                    "index_version": "4.3.2", "models": [model("first", 41.123456), model("second", 35, "second")]}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.json"
            source.write_text(json.dumps(snapshot), encoding="utf-8")
            output = root / "result"
            rating.main(["--snapshot", str(source), "--output", str(output)])
            metadata = json.loads((output / "metadata.json").read_text())
            self.assertEqual(metadata["fetched_at"], snapshot["fetched_at"])
            self.assertEqual(metadata["developers_shown"], 2)
            self.assertGreaterEqual(metadata["layout"]["minimum_flag_value_gap_points"], 6)
            self.assertIn("41.123456", (output / "rating.csv").read_text(encoding="utf-8-sig"))
            self.assertIn("https://t.me/warlocksu", (output / "rating.svg").read_text(encoding="utf-8"))
            with Image.open(output / "rating.png") as image:
                self.assertGreater(image.width, 2000)
                image.verify()


if __name__ == "__main__":
    unittest.main()
