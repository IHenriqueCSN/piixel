"""Modules offered by Piixel; only implemented modules belong in this registry."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from .module_api import ModulePage


ModuleFactory = Callable[..., "ModulePage"]


@dataclass(frozen=True)
class ModuleDefinition:
    id: str
    title: str
    description: str
    icon_name: str
    factory: ModuleFactory | None = None


def _create_atelier(*, parent=None, preferences=None) -> ModulePage:
    from .atelier import AtelierModule
    return AtelierModule(parent=parent, preferences=preferences)


def _create_settings(*, parent=None, preferences=None) -> ModulePage:
    from .settings import SettingsModule
    return SettingsModule(parent=parent, preferences=preferences)


MODULES = (
    ModuleDefinition(
        id="atelier",
        title="Ateliê",
        description="Crie pixel arts, visualize em hama beads e acompanhe as peças por cor.",
        icon_name="pencil",
        factory=_create_atelier,
    ),
    ModuleDefinition(
        id="settings",
        title="Configurações",
        description="Defina o tamanho de cada peça para as medidas das imagens exportadas.",
        icon_name="settings",
        factory=_create_settings,
    ),
)
