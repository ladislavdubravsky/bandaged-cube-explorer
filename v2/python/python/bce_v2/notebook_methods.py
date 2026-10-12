"""Witnessed palettes and revalidated discovery caches for example notebooks.

The cache stores the selected portable method, never a solver fallback. Its
key binds the reference, the entire original-loop alphabet, exact execution
permissions, search settings and the implementation used to make the method.
Different checked proofs of the same physical declaration are equivalent.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from hashlib import sha256
from inspect import signature
import json
import os
from pathlib import Path
import tempfile
from time import perf_counter

from .algorithm_palette import AlgorithmPalette, _signatures
from .coarse_methods import CoarseMethod
from .coarse_search import discover_coarse_method
from .human_chains import BlockFeature
from .loop_algorithms import AlgorithmLibrary
from .palette_policies import recipe_taught_ids
from .preparation import prepare_analysis


_CACHE_FORMAT = "bce-v2-notebook-coarse-cache"
_CACHE_VERSION = 1
_DISCOVERY_PARAMETERS = signature(discover_coarse_method).parameters
_CORE_SOURCES = (
    "_moves.py", "algorithm_palette.py", "algorithm_profiles.py", "block_actions.py",
    "coarse_methods.py", "coarse_search.py", "gap_backend.py", "human_chains.py",
    "human_method_io.py", "human_methods.py", "isotropy.py", "loop_algorithms.py",
    "notebook_methods.py", "palette_policies.py", "preparation.py",
    "symbolic_chains.py", "symbolic_groups.py",
)


def palette_from_turn_words(analysis, bodies, *, setup_words=("U", "U2", "U'"),
                            adjustment_words=("U", "U2", "U'"), allow_inverse=False,
                            max_proof_moves=1_000_000):
    """Build named bodies from physically checked original-loop witnesses.

    ``bodies`` maps stable teaching IDs to face-turn strings. Each complete
    word must be legal and return to this analysis's exact reference shape;
    native graph paths certify it in the retained original-loop alphabet.
    The same check applies to setups and standalone adjustments. No ordinary
    piece names, symmetry permissions or inverse body calls are inferred.
    """
    if not isinstance(bodies, Mapping):
        raise TypeError("bodies must map stable IDs to face-turn strings")
    analysis = prepare_analysis(analysis)
    builder = AlgorithmLibrary(analysis.loops, (), (), ())

    def algorithm(identifier, word):
        if not isinstance(word, str):
            raise TypeError("palette words must be face-turn strings")
        expression = analysis.loops.certified_root_turns(word,
                                                        max_proof_moves=max_proof_moves)
        return replace(builder.build_algorithm(expression,
                       max_expanded_moves=max(1, len(word.split()))), id=identifier)

    def adjustments(words, name):
        if isinstance(words, str):
            raise TypeError(name + " must be a sequence of face-turn strings")
        return tuple(algorithm(word, word) for word in words)

    return AlgorithmPalette.from_algorithms(
        tuple(algorithm(identifier, word) for identifier, word in bodies.items()),
        setups=adjustments(setup_words, "setup_words"),
        adjustments=adjustments(adjustment_words, "adjustment_words"),
        allow_inverse=allow_inverse)


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _json_settings(value):
    if isinstance(value, BlockFeature):
        return value.to_dict()
    if isinstance(value, (tuple, list)):
        return [_json_settings(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_settings(item) for key, item in value.items()}
    return value


def _search_settings(settings):
    parameters = _DISCOVERY_PARAMETERS
    unknown = set(settings) - (set(parameters) - {"initial", "palette"})
    if unknown:
        raise TypeError("unknown coarse discovery setting: " + ", ".join(sorted(unknown)))
    normalized = {name: settings.get(name, parameter.default)
                  for name, parameter in parameters.items() if name not in ("initial", "palette")}
    if normalized["domain_features"] is not None:
        normalized["domain_features"] = tuple(normalized["domain_features"])
    # Reject nonportable/NaN settings before reading or writing any cache.
    _json(_json_settings(normalized))
    return normalized


def _execution_palette(palette):
    def algorithm(value):
        return {"id": value.id, "turn_sequence": value.turn_sequence,
                "permutation": list(value.permutation), "htm_length": value.htm_length,
                "qtm_length": value.qtm_length}
    return {"bodies": [{"id": body.id, "allow_inverse": body.allow_inverse,
                         "algorithm": algorithm(body.algorithm)} for body in palette.bodies],
            "setups": [{"id": item.id, "algorithm": algorithm(item.algorithm)}
                       for item in palette.setups],
            "adjustments": [{"id": item.id, "algorithm": algorithm(item.algorithm)}
                            for item in palette.adjustments],
            "derivation": palette.derivation_settings}


def _source_fingerprint():
    from . import _native
    directory = Path(__file__).parent
    records = {name: sha256((directory / name).read_bytes()).hexdigest()
               for name in _CORE_SOURCES}
    records["native_engine"] = sha256(Path(_native.__file__).read_bytes()).hexdigest()
    return records


def _cache_identity(analysis, palette, settings):
    palette.validate(inventory=analysis.block_inventory, generators=analysis.loops.generators)
    payload = {"format": _CACHE_FORMAT, "version": _CACHE_VERSION,
               "reference": {"labels": analysis.loops.root_shape.labels,
                             "root_vertex": analysis.loops.root_vertex,
                             "shape_count": analysis.loops.shape_count,
                             "group_order": str(analysis.group_order),
                             "original_generators": _signatures(analysis.loops.generators)},
               "palette": _execution_palette(palette),
               "settings": _json_settings(settings), "sources": _source_fingerprint()}
    # Convert tuples to lists so the in-memory payload equals its JSON reload.
    payload = json.loads(_json(payload))
    return sha256(_json(payload).encode("utf-8")).hexdigest(), payload


def _paths(cache_dir, key):
    directory = Path(cache_dir).expanduser().resolve()
    return directory / ("coarse-" + key + ".manifest.json"), directory / ("coarse-" + key + ".method.json")


def _validate_selected(method, search_record, analysis, palette, settings):
    if (not isinstance(search_record, dict) or
            search_record.get("format") != "bce-v2-coarse-method-search" or
            search_record.get("version") != 1):
        raise ValueError("cache contains an unsupported search record")
    metadata = search_record.get("metadata", {})
    if (not isinstance(metadata, dict) or metadata.get("goals_seeded") is not False or
            metadata.get("workspace_seeded") != (settings["domain_features"] is not None) or
            metadata.get("reference_shape_count") != analysis.loops.shape_count):
        raise ValueError("cached search provenance disagrees with its discovery inputs")
    recorded_settings = metadata.get("settings", {})
    if not isinstance(recorded_settings, dict):
        raise ValueError("cached search settings are malformed")
    for name, value in recorded_settings.items():
        if name not in settings or _json_settings(settings[name]) != value:
            raise ValueError("cached search settings disagree with the cache identity")
    if set(recorded_settings) != (set(settings) - {"domain_features", "gap_executable", "timeout"}):
        raise ValueError("cached search record omits a search setting")
    if method is None:
        if search_record.get("selected_id") is not None or search_record.get("status") != "no_method_found":
            raise ValueError("cached unsuccessful search has a selected method")
        return
    if not isinstance(method, CoarseMethod):
        raise TypeError("cache method must be a CoarseMethod")
    if search_record.get("status") != "completed":
        raise ValueError("cached selected method has an unsuccessful search status")
    if (method.reference_shape != analysis.loops.root_shape or
            method.ambient_group_order != analysis.group_order or
            _signatures(method.ambient_method.generators) != _signatures(analysis.loops.generators)):
        raise ValueError("cached method belongs to a different reference or original-loop alphabet")
    if _execution_palette(method.palette) != _execution_palette(palette):
        raise ValueError("cached method has different palette execution permissions")
    candidates = search_record.get("candidates", ())
    if not isinstance(candidates, (tuple, list)) or any(not isinstance(row, dict) for row in candidates):
        raise ValueError("cached search candidates are malformed")
    selected = next((candidate for candidate in candidates
                     if candidate.get("id") == search_record.get("selected_id")), None)
    if selected is None:
        raise ValueError("cached search has no matching selected candidate")
    if (selected.get("domain_features") != [feature.to_dict() for feature in method.domain_features] or
            selected.get("features") != [stage.feature.to_dict() for stage in method.stages] or
            selected.get("case_counts") != [stage.case_count for stage in method.stages] or
            int(selected.get("domain_order", -1)) != method.group_order):
        raise ValueError("cached method differs from the selected search candidate")
    taught = recipe_taught_ids(palette, settings["max_short_setup_htm"])
    actual = {identifier for _, _, path in method.case_recipes
              for recipe in path for identifier in taught[recipe]}
    if (actual != set(selected.get("taught_definition_ids", ())) or
            len(actual) > settings["max_taught_bodies"]):
        raise ValueError("cached method violates its global teaching commitment")


def _atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                     prefix="." + path.name + ".", delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _store_cached_result(analysis, palette, cache_dir, method, search_record, settings, *, _identity=None):
    """Write a checked discovery result; also used to migrate verified artifacts."""
    settings = _search_settings(settings)
    key, payload = (_cache_identity(analysis, palette, settings)
                    if _identity is None else _identity)
    _validate_selected(method, search_record, analysis, palette, settings)
    manifest_path, method_path = _paths(cache_dir, key)
    method_digest = None
    if method is not None:
        text = method.to_json()
        method_digest = sha256(text.encode("utf-8")).hexdigest()
        _atomic_write(method_path, text)
    manifest = {"format": _CACHE_FORMAT, "version": _CACHE_VERSION, "cache_key": key,
                "identity": payload, "method_sha256": method_digest,
                "search_record": search_record}
    # The manifest is the commit point; readers verify the method digest.
    _atomic_write(manifest_path, json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return key, manifest_path, method_path


@dataclass(frozen=True)
class CachedCoarseMethod:
    """A selected portable method and its discovery/cache provenance."""

    method: CoarseMethod | None
    _search_json: str = field(repr=False)
    _metadata_json: str = field(repr=False)

    @property
    def search_record(self):
        return json.loads(self._search_json)

    @property
    def metadata(self):
        return json.loads(self._metadata_json)


def cached_coarse_method(analysis, palette, cache_dir, *, force=False, **search_settings):
    """Discover once, then load and fully revalidate the selected portable method.

    ``force=True`` reruns discovery. A corrupt or incompatible record is
    reported in ``metadata`` and replaced by a fresh bounded discovery with
    the same declared palette and settings. A search finding no method stays
    unsuccessful; the helper never invokes an unrestricted solver.
    """
    if type(force) is not bool:
        raise TypeError("force must be a boolean")
    if not isinstance(palette, AlgorithmPalette):
        raise TypeError("palette must be an AlgorithmPalette")
    if palette.max_derived_recipes == 0:
        palette = palette.with_derived_actions()
    settings = _search_settings(search_settings)
    analysis = prepare_analysis(analysis, gap_executable=settings["gap_executable"],
                                timeout=settings["timeout"])
    key, payload = _cache_identity(analysis, palette, settings)
    manifest_path, method_path = _paths(cache_dir, key)
    started = perf_counter()
    status, reason = ("forced_refresh" if force else "cache_miss"), None
    if not force and manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if (not isinstance(manifest, dict) or manifest.get("format") != _CACHE_FORMAT or
                    manifest.get("version") != _CACHE_VERSION or
                    manifest.get("cache_key") != key or manifest.get("identity") != payload):
                raise ValueError("cache manifest does not match its exact identity")
            if manifest["method_sha256"] is None:
                method = None
            else:
                raw = method_path.read_bytes()
                if sha256(raw).hexdigest() != manifest["method_sha256"]:
                    raise ValueError("cached method checksum disagrees with its manifest")
                method = CoarseMethod.from_dict(json.loads(raw))
            search_record = manifest["search_record"]
            _validate_selected(method, search_record, analysis, palette, settings)
            metadata = {"cache_hit": True, "cache_status": "validated_cache_hit", "cache_key": key,
                        "manifest_path": str(manifest_path), "method_path": str(method_path),
                        "load_seconds": perf_counter() - started, "discovery_seconds": 0.0}
            return CachedCoarseMethod(method, _json(search_record), _json(metadata))
        except (ValueError, TypeError, KeyError, OSError) as error:
            status, reason = "invalid_cache_recomputed", str(error)
    discovery_started = perf_counter()
    search = discover_coarse_method(analysis, palette=palette, **settings)
    discovery_seconds = perf_counter() - discovery_started
    search_record = search.to_dict(include_method=False)
    # Preserve the identity captured before a potentially long discovery. If
    # sources change meanwhile, a later reader gets a miss under the new key.
    _store_cached_result(analysis, palette, cache_dir, search.method, search_record, settings,
                         _identity=(key, payload))
    metadata = {"cache_hit": False, "cache_status": status, "cache_key": key,
                "manifest_path": str(manifest_path), "method_path": str(method_path),
                "discovery_seconds": discovery_seconds, "load_seconds": 0.0}
    if reason is not None:
        metadata["invalid_cache_reason"] = reason
    return CachedCoarseMethod(search.method, _json(search_record), _json(metadata))


__all__ = ["CachedCoarseMethod", "palette_from_turn_words", "cached_coarse_method"]
