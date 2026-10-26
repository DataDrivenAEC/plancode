"""Example data source: a small local CSV of illustrative unit prices and carbon factors (no network).

These numbers are made up for the demo, rounded and plausible in order of magnitude only. They are not market
prices and not ÖKOBAUDAT values. A real data source (e.g. an ÖKOBAUDAT reader) implements the same contract.
"""
from __future__ import annotations

import csv
import pathlib

CSV = pathlib.Path(__file__).resolve().parents[2] / "data" / "illustrative-materials.csv"


class IllustrativeMaterials:
    name = "illustrative-materials"
    provides = ("unit_prices", "carbon_factors")

    def __init__(self, path=CSV):
        self.path = pathlib.Path(path)
        with self.path.open(encoding="utf-8", newline="") as fh:
            self._rows = list(csv.DictReader(fh))

    def basis(self) -> str:
        return (f"Illustrative values from {self.path.name} (arch-harness demo data): not market prices, "
                f"not ÖKOBAUDAT; material only, EUR and kg CO2e per unit, rounded.")

    def table(self, kind: str) -> list[dict]:
        if kind == "unit_prices":
            return [{"material": r["material"], "unit": r["unit"], "unit_price_eur": float(r["unit_price_eur"]),
                     "trade_group": r["trade_group"], "description": r["description"]} for r in self._rows]
        if kind == "carbon_factors":
            return [{"material": r["material"], "unit": r["unit"], "kgco2e_per_unit": float(r["kgco2e_per_unit"])}
                    for r in self._rows if r["kgco2e_per_unit"]]
        raise KeyError(f"{self.name} does not provide {kind!r} (provides {', '.join(self.provides)})")
