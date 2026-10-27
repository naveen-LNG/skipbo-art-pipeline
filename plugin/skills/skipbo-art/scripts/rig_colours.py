"""rig_colours.py - tell master pixels apart by the generated parts' painted colours (legacy colour paths).

The cut-from-master path splits the master's arms, hands, legs and feet by which part's mean colour a pixel is
nearest to; the generated path uses the same test to measure the master's hand. Parts are named as placed (after
left/right renames); src() maps a placed name back to its painted part.
"""
from __future__ import annotations

import numpy as np


class Palette:
    """Mean painted colours of the generated parts (name -> (path, RGBA 0..1)), against the master's rgb."""

    def __init__(self, rgb: np.ndarray, parts: dict, renames: dict):
        self.rgb, self.parts, self.renames = rgb, parts, renames

    def mean(self, part: str):
        """Mean colour of a painted part's opaque pixels."""
        arr = self.parts[part][1]
        return arr[..., :3][arr[..., 3] > 0.5].mean(0)

    def src(self, n: str) -> str:
        """The painted part a placed name came from (left/right renames undone)."""
        return next((o for o, nw in self.renames.items() if nw == n), n)

    def keep_classes(self, region: np.ndarray, keep: list[str], against: list[str]) -> np.ndarray:
        """Drop pixels of `region` whose colour is closer to a neighbouring part than to any kept part."""
        if not against:
            return region
        dk = np.min([np.linalg.norm(self.rgb - self.mean(p_), axis=2) for p_ in keep], axis=0)
        da = np.min([np.linalg.norm(self.rgb - self.mean(p_), axis=2) for p_ in against], axis=0)
        return region & (dk <= da)

    def split(self, region: np.ndarray, near: np.ndarray, part_a: str, part_b: str) -> np.ndarray:
        """Pixels of `region` inside `near` that look more like part_a than part_b (mean painted colours)."""
        da = np.linalg.norm(self.rgb - self.mean(part_a), axis=2)
        db = np.linalg.norm(self.rgb - self.mean(part_b), axis=2)
        return region & near & (da < db)
