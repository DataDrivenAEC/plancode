# Plugin contract

Four plugin types. Each is extended by adding one entry to `arch_harness/plugins.py`; every harness reaches
them through the MCP server.

| Type | Contract | In this demo |
|------|----------|--------------|
| generator | `generate(design: dict, params: dict) -> model` (the JSON model, `arch_harness/schema/model.schema.json`) | `massing`: footprint from the site minus the Abstandsfläche, storeys from the programme |
| rules | a directory of pytest files `rule_*.py`; each test is one rule marked `@pytest.mark.rule(id=..., kind="code"\|"geometry"\|"brief")`, parametrized per element, citing its source in its docstring; it fails with `fail(message, **data)` | `arch_harness/rules`: DIN 18040-1 doors and corridors, MBO § 6 Abstandsfläche, geometry sanity, brief conformance |
| skill | a directory with `SKILL.md` (Agent Skills format) describing a design method for the agent | `skills/design-loop`, `skills/model-cost` |
| data source | an object with `name`, `provides` (table kinds), `basis()` (provenance in one sentence) and `table(kind) -> rows`; brings open evidence into the design: public building records, carbon data (e.g. ÖKOBAUDAT), local climate | `illustrative-materials`: a local CSV of made-up illustrative unit prices and carbon factors (no network), read by the cost and carbon evaluation |

A rule never states a number without its source. A data source always states its basis; the evaluation quotes it.
Geometry is a replaceable seam: `arch_harness.model.solids()` turns the model into boxes for every render; exact
B-rep solids (NVIDIA usd-brep, milestone 2) replace that function, not the model.
