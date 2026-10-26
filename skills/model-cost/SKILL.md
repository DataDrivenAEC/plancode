---
name: model-cost
description: Produce a material cost (and embodied-carbon) estimate for a design variant from its IFC render and a data source of unit prices. Use when the architect asks what a variant costs, for a cost breakdown or quantity takeoff, or to compare variants by cost. Rolls costs up by trade group (Structure / Envelope / Openings / Finishes / MEP), derives quantities from geometry, and reports an honest basis with exclusions.
license: Apache-2.0
---
<!-- Ported from aec-ai-workshop-2026 (same author), released here under Apache-2.0. -->

# Model cost estimate

Generates an order-of-magnitude **material** cost estimate from an IFC model and a unit-price data source. Built for
design-stage models that carry no quantity sets: it derives volumes and areas from the geometry.

## How to run

Through the MCP server: call `estimate_cost` with the project directory (it exports the IFC render first). Or on any
IFC from the repository root:

```bash
.conda-ah/bin/python -m arch_harness.evaluate.cost_estimate --model model/model.ifc --outdir model/cost
```

It writes `cost-breakdown.csv` (one row per element-material: GUID, type, material, quantity, unit, unit price, line
total, trade group, kg CO2e, note) and `cost-summary.md` (totals by trade, grand total, €/m², carbon, unpriced
materials, skipped elements, the basis). After running, give the architect the trade totals, the grand total, the
biggest cost driver and the headline caveats.

## The method (so you can defend or adapt the numbers)

This is **not** "quantity × rate." A professional estimate has a stated basis:

1. **Measurability audit first.** If the model has no quantity sets, don't fail: **derive quantities from the
   geometry** (IfcOpenShell's engine, in metres); layered elements are split by layer-thickness fraction.
2. **Match the rate's unit.** m³ → volume, m² → face/footprint area, kg → volume × density, unit → count. Never assume.
3. **Cost by layers, not a single "primary" material.** A stud partition's thickest layer is the stud cavity, which
   has no bulk price: cost the board faces and **flag the missing stud line** rather than hiding it.
4. **Unpriced ≠ free.** List every model material with no price-book match as an explicit exclusion, not a silent zero.
   The same for carbon: a material with no factor carries no carbon line, which is not zero carbon.
5. **Classify into trade groups** from the price book's `trade_group` column.
6. **Sanity-check** with a €/m² benchmark. If it's an order of magnitude off, the takeoff is wrong, not the building.
7. **State the basis.** An order-of-magnitude *design* estimate, not a tender bill of quantities. Materials only.
   The demo data source (`illustrative-materials`) holds made-up illustrative values: say so whenever you quote it.

## Watch out for

- **Doors**: priced per unit; exterior vs interior by the host wall's `IsExternal`.
- **Windows**: priced on glazing area (`OverallWidth × OverallHeight`, converted to m²); wide assemblies inflate area.
- **Material name mismatch**: authoring-tool names won't match price-book keys; the script carries a mapping — extend it
  for a new price book or data source.
