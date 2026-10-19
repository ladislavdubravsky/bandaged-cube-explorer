"""Legal regrips reuse one body while keeping independent native witnesses."""

from copy import deepcopy
from dataclasses import replace
from itertools import product
import shutil
import unittest
from unittest.mock import patch

import bce_v2 as c
from bce_v2.algorithm_palette import (AlgorithmPalette, AlgorithmPaletteBody,
                                     AlgorithmPaletteRegrip, AlgorithmPaletteSetup)
from bce_v2.loop_rotations import bandage_symmetries, rotate_moves, rotate_permutation
from bce_v2.palette_policies import recipe_taught_ids
from bce_v2.palette_render import execution_vocabulary, recipe_structure


def fused(*members):
    labels = [0] * 27
    for member in members:
        labels[member] = 91
    return c.Shape(labels)


def algorithm(loops, identifier, word):
    return replace(c.AlgorithmLibrary(loops, (), (), ()).build_algorithm(
        loops.certified_root_turns(word), max_expanded_moves=max(1, len(word.split()))),
        id=identifier)


class PaletteRegripTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reference = fused(c.U, c.C)
        cls.loops = c.isotropy_loops(cls.reference)
        cls.body = algorithm(cls.loops, "known", "R")
        cls.palette = AlgorithmPalette.from_algorithms((cls.body,), allow_inverse=False)

    def test_exact_and_nonexact_shape_regrips_share_one_teaching_dependency(self):
        palette = self.palette.with_rotated_bodies(rotations=("y", "z2", "z"))
        self.assertIn("y", bandage_symmetries(self.reference))
        self.assertNotIn("z2", bandage_symmetries(self.reference))
        # z maps R onto the blocked U face. z2 maps it onto legal L,
        # although z2 changes the exact reference bandage partition.
        self.assertEqual({value.rotation for value in palette.regrips}, {"y", "z2"})
        self.assertEqual({value.algorithm.turn_sequence for value in palette.regrips}, {"B", "L"})
        self.assertEqual(palette.metadata["body_count"], 1)
        self.assertEqual({record["exponent"] for record in palette.recipe_records}, {1})
        for recipe in palette.recipes:
            self.assertEqual(recipe_taught_ids(palette)[recipe.id], frozenset(("known",)))
            self.assertEqual(palette.recipe_body_ids[recipe.id], ("known",))
            replay = c.State(self.reference).apply(recipe.turn_sequence)
            self.assertEqual(replay.shape, self.reference)
            self.assertEqual(replay.sticker_permutation, recipe.permutation)
            self.assertEqual(recipe.expression.evaluate(palette.generators), recipe.permutation)
        with patch("subprocess.run", side_effect=AssertionError("validation is offline")):
            palette.validate()

    def test_all_grips_deduplicate_identical_words_and_are_idempotent(self):
        palette = self.palette.with_rotated_bodies()
        self.assertEqual({self.body.turn_sequence, *(value.algorithm.turn_sequence
                                                    for value in palette.regrips)},
                         {"R", "F", "D", "L", "B"})
        self.assertEqual(len(palette.regrips), 4)
        repeated = palette.with_rotated_bodies(self.loops)
        self.assertEqual(palette.regrips, repeated.regrips)
        self.assertEqual(palette.recipe_records, repeated.recipe_records)
        for value in palette.regrips:
            self.assertEqual(value.algorithm.turn_sequence,
                             rotate_moves(self.body.turn_sequence, value.rotation))
            self.assertEqual(value.algorithm.permutation,
                             rotate_permutation(self.body.permutation, value.rotation))

    def test_legal_transferred_word_must_close_at_exact_reference_shape(self):
        reference = fused(c.UFR, c.UR)
        loops = c.isotropy_loops(reference)
        body = algorithm(loops, "down", "D")
        self.assertEqual(rotate_moves("D", "x2"), "U")
        self.assertNotEqual(c.State(reference).apply("U").shape, reference)
        palette = AlgorithmPalette.from_algorithms((body,)).with_rotated_bodies(
            rotations=("x2",))
        self.assertEqual(palette.regrips, ())
        self.assertEqual(len(palette.recipes), 2)

    def test_setups_inverses_and_derived_actions_keep_original_permissions(self):
        loops = c.isotropy_loops(c.Shape())
        body = algorithm(loops, "right", "R")
        setup = algorithm(loops, "up", "U")
        palette = AlgorithmPalette((AlgorithmPaletteBody("right", body, True),),
            setups=(AlgorithmPaletteSetup("up", setup),)).with_rotated_bodies(
                rotations=("y",)).with_derived_actions(max_derived_recipes=32)
        records = {record["id"]: record for record in palette.recipe_records}
        self.assertEqual(len(palette._base_compiled[0]), 8)
        self.assertTrue(any(record.get("rotation") == "y" and record["setup_id"] == "up"
                            and record["exponent"] == -1 for record in records.values()))
        self.assertTrue(any(record["derived"] for record in records.values()))
        for recipe in palette.recipes:
            record = records[recipe.id]
            self.assertEqual(recipe_taught_ids(palette)[recipe.id], frozenset(("right",)))
            self.assertEqual(c.State().apply(recipe.turn_sequence).sticker_permutation,
                             recipe.permutation)
            self.assertEqual(record["adjustment_ids"], [])
            if not record["derived"]:
                self.assertEqual(record["additive_htm"], 3 if record["setup_id"] else 1)

    def test_regrip_declarations_reject_unrelated_words_and_permissions(self):
        rotated = self.palette.with_rotated_bodies(rotations=("z2",)).regrips[0]
        with self.assertRaisesRegex(ValueError, "rotated body"):
            replace(self.palette, regrips=(replace(rotated, algorithm=self.body),))
        with self.assertRaisesRegex(ValueError, "declared body ID"):
            replace(self.palette, regrips=(replace(rotated, body_id="unknown"),))
        with self.assertRaisesRegex(ValueError, "unique"):
            replace(self.palette, regrips=(rotated, rotated))
        with self.assertRaisesRegex(ValueError, "nonidentity"):
            AlgorithmPaletteRegrip("known", "x x'", self.body)
        with self.assertRaises(TypeError):
            AlgorithmPaletteRegrip("known", "x", "R")
        with self.assertRaises(TypeError):
            self.palette.with_rotated_bodies(rotations="x")
        with self.assertRaisesRegex(ValueError, "max_proof_moves"):
            self.palette.with_rotated_bodies(rotations=("z2",), max_proof_moves=0)
        with self.assertRaisesRegex(ValueError, "original-loop alphabet"):
            self.palette.with_rotated_bodies(c.isotropy_loops(c.Shape()), rotations=("x",))

    def test_renderer_names_the_original_body_inside_regrips_setups_and_powers(self):
        loops = c.isotropy_loops(c.Shape())
        body = algorithm(loops, "right", "R")
        setup = algorithm(loops, "up", "U")
        palette = AlgorithmPalette((AlgorithmPaletteBody("right", body, True),),
            setups=(AlgorithmPaletteSetup("up", setup),)).with_rotated_bodies(rotations=("y",))
        inverse = next(record["id"] for record in palette.recipe_records
                       if record["rotation"] == "y" and record["exponent"] == -1
                       and record["setup_id"] is None)
        conjugate = next(record["id"] for record in palette.recipe_records
                         if record["rotation"] == "y" and record["exponent"] == -1
                         and record["setup_id"] == "up")
        path = (inverse, inverse, conjugate, conjugate)
        declarations, aliases = execution_vocabulary(palette, (path,))
        self.assertEqual([(kind, name) for kind, name, _ in declarations],
                         [("Body", "A"), ("Setup", "B")])
        self.assertEqual(recipe_structure(palette, path, aliases),
                         "(y (A⁻¹) y')² [B: y (A⁻¹) y']²")
        recipes = {value.id: value for value in palette.recipes}
        physical = " ".join(recipes[identifier].turn_sequence for identifier in path)
        self.assertEqual(c.State().apply(physical),
                         c.State().apply("B' B' U B' U' U B' U'"))


@unittest.skipUnless(shutil.which("gap"), "GAP prepares the 16-state ambient group")
class PortablePaletteRegripTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Three fused slabs permit the independent R and L turns only.
        cls.reference = c.Shape([1 + index % 3 for index in range(27)])
        cls.analysis = c.analyze_isotropy(cls.reference, timeout=30)
        cls.base = AlgorithmPalette.from_algorithms((
            algorithm(cls.analysis.loops, "right", "R"),))
        cls.palette = cls.base.with_rotated_bodies(rotations=("y2",))
        cls.method = c.compile_coarse_method(cls.analysis, palette=cls.palette,
            features=(c.BlockFeature("solve_blocks", tuple(range(27))),), timeout=30)

    def test_portable_method_roundtrips_and_solves_all_states_without_native_certification(self):
        record = self.method.to_dict()
        with patch("subprocess.run", side_effect=AssertionError("portable execution is offline")), \
                patch("bce_v2.isotropy.LoopGenerators.certified_root_turns",
                      side_effect=AssertionError("saved original-loop witnesses suffice")):
            loaded = c.CoarseMethod.from_dict(record)
            self.assertEqual(loaded.to_dict(), record)
            self.assertEqual(loaded.taught_body_ids, ("right",))
            self.assertEqual(loaded.group_order, 16)
            for right, left in product(("", "R", "R2", "R'"),
                                       ("", "L", "L2", "L'")):
                observed = c.State(self.reference).apply((right + " " + left).strip())
                state = c.State.from_cubies(observed.specification,
                    corners=observed.corners, twists=observed.twists,
                    edges=observed.edges, flips=observed.flips)
                result = loaded.apply(state)
                self.assertTrue(result.state.is_solved)
                self.assertEqual(state.apply(result.turn_sequence), result.state)
            guide = loaded.write_guide()
            self.assertIn("y2 (A", guide)
            self.assertIn("same learned body", guide)

    def test_saved_regrip_permissions_and_words_cannot_be_relabelled(self):
        from bce_v2.human_method_io import _fingerprint

        record = self.method.to_dict()
        for field, value in (("rotation", "y"), ("body_id", "unknown")):
            with self.subTest(field=field):
                broken = deepcopy(record)
                broken["palette"]["regrips"][0][field] = value
                broken["fingerprint"] = _fingerprint(broken)
                with self.assertRaises(ValueError):
                    c.CoarseMethod.from_dict(broken)
        broken = deepcopy(record)
        broken["palette"]["regrips"][0]["algorithm"]["turn_sequence"] = "R"
        broken["fingerprint"] = _fingerprint(broken)
        with self.assertRaisesRegex(ValueError, "physical witness"):
            c.CoarseMethod.from_dict(broken)
        broken = deepcopy(record)
        del broken["palette"]["regrips"]
        broken["fingerprint"] = _fingerprint(broken)
        with self.assertRaises(ValueError):
            c.CoarseMethod.from_dict(broken)

    def test_notebook_cache_identity_includes_regrip_execution_permissions(self):
        from bce_v2.notebook_methods import _cache_identity, _search_settings

        settings = _search_settings(dict(max_taught_bodies=1, max_expansions=1, timeout=30))
        base_key, base_record = _cache_identity(self.analysis, self.base, settings)
        regrip_key, regrip_record = _cache_identity(self.analysis, self.palette, settings)
        self.assertNotEqual(base_key, regrip_key)
        self.assertEqual(base_record["palette"]["bodies"], regrip_record["palette"]["bodies"])
        self.assertNotIn("regrips", base_record["palette"])
        self.assertEqual(regrip_record["palette"]["regrips"][0]["rotation"], "y2")


if __name__ == "__main__":
    unittest.main()
