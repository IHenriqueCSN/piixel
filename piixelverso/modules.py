"""Modules offered by Piixel; only implemented modules belong in this registry."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ModuleDefinition:
    id: str
    title: str
    description: str
    icon_name: str


MODULES = (
    ModuleDefinition(
        id="atelier",
        title="Ateliê",
        description="Crie pixel arts, visualize em hama beads e acompanhe as peças por cor.",
        icon_name="pencil",
    ),
)
