"""Shared immutable owners for portable original-loop witness libraries."""

from types import MappingProxyType

from .isotropy import LoopGenerator


class _StoredLoopOwner:
    """Native-like owner used by existing expression replay and expansion.

    Loop IDs are local library names. The retained permutations are copied
    into tuples, so changing a caller's record cannot change a loaded library.
    """

    __slots__ = ("root_shape", "root_vertex", "shape_count", "arc_count", "candidate_count",
                 "nonidentity_count", "generators", "_moves")

    def __init__(self, inventory, root_vertex, records, complete_loops):
        object.__setattr__(self, "root_shape", tuple(inventory.root_shape.labels))
        object.__setattr__(self, "root_vertex", root_vertex)
        object.__setattr__(self, "shape_count", complete_loops.shape_count)
        object.__setattr__(self, "arc_count", complete_loops.arc_count)
        object.__setattr__(self, "candidate_count", complete_loops.candidate_count)
        object.__setattr__(self, "nonidentity_count", complete_loops.nonidentity_count)
        object.__setattr__(self, "generators", tuple(MappingProxyType({
            key: tuple(record[key]) if key == "permutation" else record[key]
            for key in ("id", "source", "target", "permutation", "qtm_length")
        }) for record in records))
        object.__setattr__(self, "_moves", MappingProxyType({record["id"]: record["moves"]
                                                            for record in records}))

    def __setattr__(self, name, value):
        raise AttributeError("portable loop owner is immutable")

    def __delattr__(self, name):
        raise AttributeError("portable loop owner is immutable")

    def generator_moves(self, identifier):
        return self._moves[identifier]


def stored_loop_generators(records, inventory, root_vertex, complete_loops):
    """Build leaves sharing one portable owner from already validated records.

    Required record fields are id, source, target, permutation, qtm_length,
    and moves. Callers establish unique IDs, legal root-loop witnesses, exact
    effects, and completeness; this utility does not grant those certificates.
    Descriptive source IDs need not match the regenerated native shape graph.
    """
    records = tuple(records)
    owner = _StoredLoopOwner(inventory, root_vertex, records, complete_loops)
    return tuple(LoopGenerator(record["id"], record["source"], record["target"],
                               tuple(record["permutation"]), record["qtm_length"],
                               owner, inventory) for record in records)
