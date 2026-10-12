"""Notebook caches retain exact execution permissions and portable coverage."""

from dataclasses import replace
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import bce_v2 as c
from bce_v2.notebook_methods import (cached_coarse_method, palette_from_turn_words,
                                    _cache_identity, _search_settings, _source_fingerprint)


@unittest.skipUnless(shutil.which("gap"), "GAP prepares the tiny exact ambient group")
class NotebookMethodTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shape = c.Shape([1] * 9 + [2] * 18)
        cls.analysis = c.analyze_isotropy(cls.shape, timeout=30)
        cls.palette = palette_from_turn_words(cls.analysis, {"turn": "U"},
                                             setup_words=(), adjustment_words=())
        cls.settings = dict(max_taught_bodies=1, beam_width=1, max_expansions=2,
                            max_stages=1, timeout=30)
        cls.search = c.discover_coarse_method(cls.analysis, palette=cls.palette, **cls.settings)

    def test_fused_bandage_word_gets_a_checked_original_loop_proof(self):
        body = self.palette.bodies[0]
        self.assertFalse(body.allow_inverse)
        self.assertEqual(body.algorithm.expression.kind, "turns")
        self.assertEqual(body.algorithm.turn_sequence, "U")
        self.assertEqual(body.algorithm.expression.evaluate(self.analysis.loops),
                         tuple(c.State(self.shape).apply("U").sticker_permutation))
        self.palette.validate()

    def test_palette_rejects_blocked_words_instead_of_assuming_face_loops(self):
        with self.assertRaisesRegex(ValueError, "blocked"):
            palette_from_turn_words(self.analysis, {"illegal": "R R'"},
                                    setup_words=(), adjustment_words=())
        with self.assertRaises(TypeError):
            palette_from_turn_words(self.analysis, {"turn": "U"}, setup_words="U")
        with self.assertRaises(ValueError):
            palette_from_turn_words(self.analysis, {"turn": "U"}, setup_words=(),
                                    adjustment_words=(), max_proof_moves=0)

    def test_cache_hit_loads_offline_and_executes_all_four_states(self):
        with tempfile.TemporaryDirectory() as cache:
            with patch("bce_v2.notebook_methods.discover_coarse_method", return_value=self.search) as discover:
                first = cached_coarse_method(self.analysis, self.palette, cache, **self.settings)
                discover.assert_called_once()
            self.assertFalse(first.metadata["cache_hit"])
            self.assertEqual(first.metadata["cache_status"], "cache_miss")
            self.assertTrue(Path(first.metadata["manifest_path"]).is_file())
            with patch("bce_v2.notebook_methods.discover_coarse_method",
                       side_effect=AssertionError("warm cache must not rediscover")), \
                    patch("subprocess.run", side_effect=AssertionError("warm load must be offline")):
                loaded = cached_coarse_method(self.analysis, self.palette, cache, **self.settings)
                self.assertTrue(loaded.metadata["cache_hit"])
                self.assertEqual(loaded.search_record, first.search_record)
                for word in ("", "U", "U2", "U'"):
                    observed = c.State(self.shape).apply(word)
                    state = c.State.from_cubies(observed.specification,
                        corners=observed.corners, twists=observed.twists,
                        edges=observed.edges, flips=observed.flips)
                    self.assertIsNone(state.scramble)
                    application = loaded.method.apply(state)
                    self.assertTrue(application.state.is_solved)
                    self.assertEqual(state.apply(application.turn_sequence), application.state)
            copy = loaded.search_record
            copy["selected_id"] = "bad"
            self.assertEqual(loaded.search_record["selected_id"], self.search.selected_id)

    def test_corrupt_method_is_reported_and_same_bounded_search_recomputes(self):
        with tempfile.TemporaryDirectory() as cache:
            with patch("bce_v2.notebook_methods.discover_coarse_method", return_value=self.search):
                first = cached_coarse_method(self.analysis, self.palette, cache, **self.settings)
            Path(first.metadata["method_path"]).write_text("{}", encoding="utf-8")
            with patch("bce_v2.notebook_methods.discover_coarse_method", return_value=self.search) as discover:
                second = cached_coarse_method(self.analysis, self.palette, cache, **self.settings)
                discover.assert_called_once()
            self.assertFalse(second.metadata["cache_hit"])
            self.assertEqual(second.metadata["cache_status"], "invalid_cache_recomputed")
            self.assertIn("checksum", second.metadata["invalid_cache_reason"])
            self.assertEqual(second.search_record, first.search_record)

    def test_manifest_cannot_relabel_a_different_palette_or_candidate(self):
        with tempfile.TemporaryDirectory() as cache:
            with patch("bce_v2.notebook_methods.discover_coarse_method", return_value=self.search):
                first = cached_coarse_method(self.analysis, self.palette, cache, **self.settings)
            manifest_path = Path(first.metadata["manifest_path"])
            record = json.loads(manifest_path.read_text(encoding="utf-8"))
            record["search_record"]["selected_id"] = "unknown"
            manifest_path.write_text(json.dumps(record), encoding="utf-8")
            with patch("bce_v2.notebook_methods.discover_coarse_method", return_value=self.search):
                regenerated = cached_coarse_method(self.analysis, self.palette, cache, **self.settings)
            self.assertEqual(regenerated.metadata["cache_status"], "invalid_cache_recomputed")
            self.assertIn("selected candidate", regenerated.metadata["invalid_cache_reason"])
            manifest_path.write_text("[]", encoding="utf-8")
            with patch("bce_v2.notebook_methods.discover_coarse_method", return_value=self.search):
                malformed = cached_coarse_method(self.analysis, self.palette, cache, **self.settings)
            self.assertEqual(malformed.metadata["cache_status"], "invalid_cache_recomputed")
            self.assertIn("manifest", malformed.metadata["invalid_cache_reason"])

    def test_key_binds_inverse_permissions_setups_settings_and_sources(self):
        settings = _search_settings(self.settings)
        baseline, _ = _cache_identity(self.analysis, self.palette, settings)
        inverse = replace(self.palette, bodies=(replace(self.palette.bodies[0], allow_inverse=True),))
        inverse_key, _ = _cache_identity(self.analysis, inverse, settings)
        self.assertNotEqual(baseline, inverse_key)
        setups = palette_from_turn_words(self.analysis, {"turn": "U"}, setup_words=("U",),
                                         adjustment_words=())
        setup_key, _ = _cache_identity(self.analysis, setups, settings)
        self.assertNotEqual(baseline, setup_key)
        adjusted = dict(settings, preference="execution")
        adjusted_key, _ = _cache_identity(self.analysis, self.palette, adjusted)
        self.assertNotEqual(baseline, adjusted_key)
        source = _source_fingerprint()
        source["coarse_search.py"] = "changed"
        with patch("bce_v2.notebook_methods._source_fingerprint", return_value=source):
            source_key, _ = _cache_identity(self.analysis, self.palette, settings)
        self.assertNotEqual(baseline, source_key)

    def test_force_refresh_and_invalid_options_are_explicit(self):
        with tempfile.TemporaryDirectory() as cache:
            with patch("bce_v2.notebook_methods.discover_coarse_method", return_value=self.search):
                cached_coarse_method(self.analysis, self.palette, cache, **self.settings)
            with patch("bce_v2.notebook_methods.discover_coarse_method", return_value=self.search) as discover:
                forced = cached_coarse_method(self.analysis, self.palette, cache, force=True, **self.settings)
                discover.assert_called_once()
            self.assertEqual(forced.metadata["cache_status"], "forced_refresh")
            with self.assertRaisesRegex(TypeError, "unknown"):
                cached_coarse_method(self.analysis, self.palette, cache, imaginary_setting=3)
            with self.assertRaises(TypeError):
                cached_coarse_method(self.analysis, self.palette, cache, force=1)

    def test_unsuccessful_bounded_search_stays_unsuccessful_on_cache_hit(self):
        settings = dict(self.settings, max_taught_bodies=0)
        unsuccessful = c.discover_coarse_method(self.analysis, palette=self.palette, **settings)
        self.assertIsNone(unsuccessful.method)
        with tempfile.TemporaryDirectory() as cache:
            with patch("bce_v2.notebook_methods.discover_coarse_method", return_value=unsuccessful):
                first = cached_coarse_method(self.analysis, self.palette, cache, **settings)
            with patch("bce_v2.notebook_methods.discover_coarse_method",
                       side_effect=AssertionError("no solver fallback is authorized")):
                cached = cached_coarse_method(self.analysis, self.palette, cache, **settings)
            self.assertIsNone(first.method)
            self.assertIsNone(cached.method)
            self.assertTrue(cached.metadata["cache_hit"])
            self.assertEqual(cached.search_record["status"], "no_method_found")

    def test_source_change_during_discovery_cannot_relabel_old_runtime_results(self):
        source = _source_fingerprint()
        original_search_hash = source["coarse_search.py"]

        def discover(*args, **kwargs):
            source["coarse_search.py"] = "changed-during-search"
            return self.search

        with tempfile.TemporaryDirectory() as cache, \
                patch("bce_v2.notebook_methods._source_fingerprint", return_value=source):
            with patch("bce_v2.notebook_methods.discover_coarse_method", side_effect=discover):
                first = cached_coarse_method(self.analysis, self.palette, cache, **self.settings)
            manifest = json.loads(Path(first.metadata["manifest_path"]).read_text(encoding="utf-8"))
            self.assertEqual(manifest["identity"]["sources"]["coarse_search.py"], original_search_hash)
            with patch("bce_v2.notebook_methods.discover_coarse_method", return_value=self.search) as rerun:
                second = cached_coarse_method(self.analysis, self.palette, cache, **self.settings)
                rerun.assert_called_once()
            self.assertFalse(second.metadata["cache_hit"])
            self.assertNotEqual(first.metadata["cache_key"], second.metadata["cache_key"])


if __name__ == "__main__":
    unittest.main()
