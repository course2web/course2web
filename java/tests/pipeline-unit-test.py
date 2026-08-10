#!/usr/bin/env python3

import copy
import datetime as dt
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


JAVA_DIR = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("course2web_pipeline", JAVA_DIR / "pipeline.py")
PIPELINE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = PIPELINE
SPEC.loader.exec_module(PIPELINE)


class PipelineUnitTest(unittest.TestCase):
    def setUp(self):
        self.cutoff = dt.date(2026, 8, 4)
        self.series_data = {
            "normalized_name": "daily_homilies",
            "title": "Daily homilies",
            "reverse_order": "TRUE",
        }

    def test_cutoff_is_inclusive_and_updated_on_overrides_old_date(self):
        self.assertFalse(PIPELINE.is_eligible({"date": "08/03/2026"}, self.cutoff))
        self.assertTrue(PIPELINE.is_eligible({"date": "08/04/2026"}, self.cutoff))
        self.assertTrue(
            PIPELINE.is_eligible(
                {"date": "01/01/2020", "updated_on": "2026-08-05"}, self.cutoff
            )
        )

    def test_snapshot_merge_keeps_historical_row_byte_semantics(self):
        historical = {
            "id": "20260803",
            "date": "08/03/2026",
            "title": "Published title",
            "audio": "2026-08-03.m4a",
            "duration": "00:10:00.00",
            "length": "1234",
            "link2mp3": "/daily_homilies/audio/20260803-daily_homilies.mp3",
        }
        current_historical = copy.deepcopy(historical)
        current_historical["title"] = "Sheet title that cutoff must ignore"
        eligible = {
            "id": "20260804",
            "date": "08/04/2026",
            "title": "New title",
            "audio": "2026-08-04.m4a",
        }
        current = [{"seriesData": self.series_data, "classes": [current_historical, eligible]}]
        baseline = [{"seriesData": self.series_data, "classes": [historical]}]
        merged, warnings = PIPELINE.merge_snapshot(current, baseline, self.cutoff)
        self.assertEqual(merged[0]["classes"][0], historical)
        self.assertEqual(merged[0]["classes"][1]["title"], "New title")
        self.assertEqual(warnings, [])

    def test_generated_metadata_is_preserved_until_new_output_exists(self):
        old = {
            "id": "20260804",
            "date": "08/04/2026",
            "audio": "old.m4a",
            "duration": "00:01:02.03",
            "length": "42",
            "link2mp3": "/daily_homilies/audio/20260804-daily_homilies.mp3",
        }
        new = {"id": "20260804", "date": "08/04/2026", "audio": "new.m4a"}
        merged, _ = PIPELINE.merge_snapshot(
            [{"seriesData": self.series_data, "classes": [new]}],
            [{"seriesData": self.series_data, "classes": [old]}],
            self.cutoff,
        )
        for field in PIPELINE.GENERATED_FIELDS:
            self.assertEqual(merged[0]["classes"][0][field], old[field])

    def test_command_allowlist_rejects_remote_deletion_and_mirroring(self):
        for command in (
            ["aws", "s3", "sync", "a", "b"],
            ["aws", "s3", "cp", "a", "b", "--delete"],
            ["aws", "s3api", "delete-object", "--bucket", "x"],
            ["rclone", "sync", "remote:x", "local"],
            ["rclone", "move", "remote:x", "local"],
        ):
            with self.subTest(command=command):
                with self.assertRaises(PIPELINE.PipelineError):
                    PIPELINE.assert_safe_command(command)

    def test_publish_sets_public_read_for_legacy_website_origin(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "cp.json"
            output.write_text("cp = []\n", encoding="utf-8")
            digest = PIPELINE.sha256_file(output)
            args = SimpleNamespace(
                allow_publish=True,
                s3_bucket="www.catholicpatrimony.com",
                aws_region="us-east-1",
                cloudfront_distribution_id="",
            )
            plan = {
                "uploads": [
                    {
                        "changed": True,
                        "localPath": str(output),
                        "sha256": digest,
                        "key": "cp.json",
                        "contentType": "application/javascript",
                        "cacheControl": "max-age=300, must-revalidate",
                    }
                ],
                "cloudFrontInvalidationPaths": [],
            }
            commands = []
            with mock.patch.object(
                PIPELINE, "run_command", side_effect=lambda command: commands.append(command)
            ):
                PIPELINE.publish(args, plan)
            self.assertEqual(commands[0][commands[0].index("--acl") + 1], "public-read")

    def test_legacy_orig_path_id_matches_by_audio(self):
        legacy = {"id": "orig/daily_homilies/audio/2019-4-23.wav", "audio": "2019-4-23.wav"}
        current = {"audio": "2019-4-23.wav"}
        self.assertEqual(PIPELINE.stable_key(legacy), PIPELINE.stable_key(current))

    def test_podcast_is_valid_and_uses_https_guid(self):
        row = {
            "id": "20260804",
            "title": "Saint & Test",
            "date": "08/04/2026",
            "rssDate": "Tue, 4 Aug 2026 00:00:00 -0400",
            "audio": "test.m4a",
            "duration": "00:01:02.03",
            "length": "42",
            "link2mp3": "/daily_homilies/audio/20260804-daily_homilies.mp3",
        }
        xml = PIPELINE.podcast_xml({"seriesData": self.series_data, "classes": [row]})
        root = PIPELINE.ET.fromstring(xml)
        guid = root.find("./channel/item/guid")
        self.assertIsNotNone(guid)
        self.assertEqual(
            guid.text,
            "https://www.catholicpatrimony.com/daily_homilies/audio/20260804-daily_homilies.mp3",
        )

    def test_podcast_snapshot_preserves_old_item_and_prepends_new_item(self):
        baseline = """<?xml version=\"1.0\"?>
<rss xmlns:itunes=\"http://www.itunes.com/dtds/podcast-1.0.dtd\"><channel>
    <title>Existing formatting</title>
    <item>
      <title>old</title>
      <guid>http://www.catholicpatrimony.com/daily_homilies/audio/old.mp3</guid>
    </item>
</channel></rss>
"""
        row = {
            "id": "20260804",
            "title": "New",
            "date": "08/04/2026",
            "rssDate": "Tue, 4 Aug 2026 00:00:00 -0400",
            "audio": "new.m4a",
            "duration": "00:01:02.03",
            "length": "42",
            "link2mp3": "/daily_homilies/audio/new.mp3",
        }
        merged = PIPELINE.merge_podcast_snapshot(
            baseline, {"seriesData": self.series_data, "classes": [row]}, self.cutoff
        )
        self.assertIn("<title>Existing formatting</title>", merged)
        self.assertIn("<title>old</title>", merged)
        self.assertLess(merged.index("20260804-New"), merged.index("<title>old</title>"))
        PIPELINE.ET.fromstring(merged)

    def test_legacy_placeholder_guid_is_not_treated_as_new_duplicate(self):
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary)
            (work / "out" / "misc").mkdir(parents=True)
            (work / "out" / "cp.json").write_text("cp = []", encoding="utf-8")
            (work / "out" / "misc" / "podcast.xml").write_text(
                """<rss><channel>
<item><guid>http://www.catholicpatrimony.com$class.link2mp3</guid></item>
<item><guid>http://www.catholicpatrimony.com$class.link2mp3</guid></item>
</channel></rss>""",
                encoding="utf-8",
            )
            args = SimpleNamespace(work_dir=work, active_series=["misc"])
            self.assertEqual(PIPELINE.validate_outputs(args, []), [])


if __name__ == "__main__":
    unittest.main()
