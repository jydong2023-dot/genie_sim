"""Standalone scene-bundle augmentation APIs."""

from .contact_sheet import build_contact_sheet
from .scenario_augmentation import (
    AugmentationProfile,
    GenericScenarioSpec,
    build_generic_scenario_specs,
    describe_scene,
    discover_object_ids,
    generate_augmented_scenarios,
    load_profile,
    load_scene_info,
    numeric_instance_ids,
)

__all__ = [
    "AugmentationProfile",
    "GenericScenarioSpec",
    "build_contact_sheet",
    "build_generic_scenario_specs",
    "describe_scene",
    "discover_object_ids",
    "generate_augmented_scenarios",
    "load_profile",
    "load_scene_info",
    "numeric_instance_ids",
]
