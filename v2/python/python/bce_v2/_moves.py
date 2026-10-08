"""Shared move-word presentation for witnessed algorithms and solutions."""


def _simplified_moves(moves):
    """Combine adjacent same-face turns in a validated word, preserving legality.

    Outer-face turns leave that face's block containment unchanged. Replacing
    a run by its net turn therefore preserves both its action and legal replay.
    """
    stack = []
    for move in moves:
        amount = 2 if move.endswith("2") else 3 if move.endswith("'") else 1
        if stack and stack[-1][0] == move[0]:
            amount = (stack.pop()[1] + amount) % 4
        if amount:
            stack.append((move[0], amount))
    return " ".join(face + ("2" if amount == 2 else "'" if amount == 3 else "")
                    for face, amount in stack)
