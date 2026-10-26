"""The plugin contract: four types, each extended by adding an entry (see docs/plugin-contract.md).

- generator:   (design, params) -> model           turns intent into form
- rules:       a directory of pytest rule_*.py     checks a model; each rule cites its source
- skill:       a directory with SKILL.md           a design method for the agent (Agent Skills format)
- data_source: object with name, provides, basis(), table(kind) -> rows   brings open evidence into the design

Any harness reaches them through the MCP server (arch_harness.mcp_server); nothing here depends on one harness.
"""
from __future__ import annotations

import pathlib

from .checks import RULES_DIR
from .data_sources.illustrative_materials import IllustrativeMaterials
from .generators.massing import generate as massing

PLUGIN_TYPES = ("generator", "rules", "skill", "data_source")
SKILLS_DIR = pathlib.Path(__file__).resolve().parents[1] / "skills"

GENERATORS = {"massing": massing}
RULE_SETS = {"core": RULES_DIR}
DATA_SOURCES = {IllustrativeMaterials.name: IllustrativeMaterials}


def skills() -> dict[str, pathlib.Path]:
    return {p.parent.name: p.parent for p in sorted(SKILLS_DIR.glob("*/SKILL.md"))}


def registry() -> dict[str, dict]:
    return {"generator": dict(GENERATORS), "rules": dict(RULE_SETS), "skill": skills(),
            "data_source": dict(DATA_SOURCES)}


def data_source(name: str):
    return DATA_SOURCES[name]()
