"""Keep presentation code current while reviewing examples in a live kernel."""

from importlib import import_module, invalidate_caches, reload


_RENDERERS = (
    "graphics",
    "graph_render",
    "human_move_notation",
    "human_instruction_render",
    "human_diagram_stripes",
    "human_diagram_render",
    "human_render",
    "human_repertoire_render",
)


def refresh_renderers():
    """Reload Python presentation modules without replacing puzzle objects.

    An editable installation exposes changed files immediately to a fresh
    process, but a live notebook retains imported modules. Refresh these
    renderers in dependency order before displaying a regenerated guide.
    State, Shape, method classes, the diagram-mode enum, and the native engine
    retain their identities, so existing analyses and methods remain usable.
    """
    invalidate_caches()
    for name in _RENDERERS:
        module = import_module(f"bce_v2.{name}")
        reload(module)
    # This formatter is imported directly into the package's public namespace.
    # Other public drawing/guide entry points import their renderer on use.
    package = import_module("bce_v2")
    package.structured_move_notation = import_module(
        "bce_v2.human_move_notation").structured_move_notation


__all__ = ["refresh_renderers"]
