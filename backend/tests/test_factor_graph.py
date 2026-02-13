from __future__ import annotations

import unittest

from backend.app.factor.graph import FactorGraph, FactorGraphError, FactorSpec


class FactorGraphTests(unittest.TestCase):
    def test_topo_order_is_deterministic(self) -> None:
        g = FactorGraph(
            [
                FactorSpec("pen", ("pivot",)),
                FactorSpec("pivot", ()),
                FactorSpec("zhongshu", ("pen",)),
            ]
        )
        self.assertEqual(g.topo_order, ("pivot", "pen", "zhongshu"))

    def test_cycle_is_rejected_with_path(self) -> None:
        with self.assertRaises(FactorGraphError) as ctx:
            FactorGraph(
                [
                    FactorSpec("a", ("b",)),
                    FactorSpec("b", ("c",)),
                    FactorSpec("c", ("a",)),
                ]
            )
        self.assertIn("cycle:", str(ctx.exception))
        self.assertIn("a", str(ctx.exception))

    def test_missing_dep_is_rejected(self) -> None:
        with self.assertRaises(FactorGraphError) as ctx:
            FactorGraph([FactorSpec("pen", ("pivot",))])
        self.assertIn("missing_deps", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()

