"""Code values shared by a generator and the rule that checks it: one home each."""


def abstandsflaeche(height: int) -> int:
    """MBO § 6 Abs. 5 Satz 1: depth 0,4 H, at least 3 m, in whole mm rounded up (never below the stated depth)."""
    return max(3000, -(-2 * height // 5))
