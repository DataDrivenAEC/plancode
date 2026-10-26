---
name: design-loop
description: Develop a building design from DESIGN.md with the arch-harness tools - generate a massing, read the rule results and the plan, revise, compare variants by rules and cost. Use when the architect asks to design, generate, check, revise or compare a building or a variant from a brief.
license: Apache-2.0
---

# Design loop

The architect's intent is `DESIGN.md` (brief, programme, site, constraints, parameters, ideas, variants). It is already
in your context. The model (`model/model.json`, mm) is the truth; USD, IFC and the plan SVG are renders of it.

1. **Generate.** Call `generate_massing` (optionally with a `variant` and `overrides`). The harness runs the rules after
   every generator call and appends the failures to the result.
2. **Read the failures.** Three kinds: `code` (German building law: DIN 18040-1, MBO § 6, each citing its source),
   `geometry` (openings fit walls, rooms do not overlap), `brief` (every programme room at its area). A kind with no
   checks is *unconfirmed*: never say it passed.
3. **Fix parameters deterministically.** `revise_parameters` proposes the fixes that are a single value at its stated
   minimum (door width, corridor width, storey height). Apply them as `overrides` and generate again. Never shrink an
   element below its code minimum to make it fit: raise or widen its container.
4. **Layout is your creative job.** When a failure has no parameter fix (a room does not fit, the site is too small),
   read the plan (`plan_svg`) and the generator notes, then change a layout parameter the architect left open
   (`room_depth`, `storeys`) or tell the architect which idea in DESIGN.md conflicts with the site. Do not invent rules
   or relax one.
5. **Stop honestly.** Done means all three kinds pass. If they cannot within the round limit, say why (which rule, which
   element, what the site allows) instead of claiming success.
6. **Variants.** Each variant lives on its own git branch (`fork_variant`). Compare variants with `estimate_cost` and
   the rule results; quote the cost basis (illustrative data, materials only).
