# DESIGN.md format

`DESIGN.md` is the architect's intent and the first thing an agent reads. Plain Markdown, no YAML:

- `# Title` — the project name.
- `## Brief` — free text: who the building is for, what it should feel like.
- `## Site` — `- width: 40 m`, `- depth: 30 m`, `- jurisdiction: …`. Lengths need a unit (`m` or `mm`).
- `## Programme` — a table `| Room | Area m² | Count | Storey |`; Storey is a number (`0`), `any`, or `each`
  (once per storey, e.g. a stair core).
- `## Constraints` — `- max_storeys: 2`, `- storey_height: 3.2 m`, `- structure: masonry` (or `timber`); optional
  `- storeys: 3` fixes the storey count.
- `## Parameters` — the architect's first sketch: `corridor_width`, `door_width`, `door_height`, `room_depth`,
  `exterior_wall`, `interior_wall`, `slab_thickness`. The loop changes them only to meet a rule minimum.
- `## Ideas` — free text for the agent.
- `## Variants` — `### name` headings, each with `- key: value` overrides of constraints and parameters.

The model stores every length as integer millimetres. See `examples/clinic/DESIGN.md`.
