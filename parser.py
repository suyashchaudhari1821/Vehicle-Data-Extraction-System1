"""Parsing helpers for FCA/Stellantis vehicle API responses."""

from typing import Any, Dict, Iterable, List


MODEL_NAME_FIELDS = (
    "displayName",
    "modelDisplayName",
    "modelLabel",
    "label",
    "name",
    "modelName",
)

VERSION_LIST_FIELDS = ("modelVersions", "versions", "modelVersionList")
VERSION_NAME_FIELDS = ("versionName", "displayName", "name", "label")
VERSION_ID_FIELDS = ("modelVersionId", "versionId", "id")
ENGINE_NAME_FIELDS = (
    "engine",
    "engineName",
    "engineDescription",
    "motor",
    "powertrain",
)


def _walk(value: Any) -> Iterable[Any]:
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _first_text(source: Dict[str, Any], fields: Iterable[str], default: str = "") -> str:
    for field in fields:
        value = source.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return default


def _first_list(source: Dict[str, Any], fields: Iterable[str]) -> List[Any]:
    for field in fields:
        value = source.get(field)
        if isinstance(value, list):
            return value
    return []


def extract_models(response: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Find model dictionaries in a response, even when nesting differs by brand."""
    models = []
    seen = set()

    for item in _walk(response):
        if not isinstance(item, dict):
            continue

        model_name = _first_text(item, MODEL_NAME_FIELDS)
        versions = _first_list(item, VERSION_LIST_FIELDS)
        if not model_name or not versions:
            continue

        marker = (model_name, tuple(str(v.get("modelVersionId") or v.get("id")) for v in versions if isinstance(v, dict)))
        if marker in seen:
            continue

        seen.add(marker)
        models.append(item)

    return models


def get_model_name(model: Dict[str, Any]) -> str:
    """Return the best model name available in the API model object."""
    return _first_text(model, MODEL_NAME_FIELDS)


def extract_versions(model: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return version dictionaries from a model object."""
    return [version for version in _first_list(model, VERSION_LIST_FIELDS) if isinstance(version, dict)]


def get_version_id(version: Dict[str, Any]) -> str:
    """Return the best API identifier for a version object."""
    return _first_text(version, VERSION_ID_FIELDS)


def get_version_name(version: Dict[str, Any]) -> str:
    """Return the best display name for a version object."""
    return _first_text(version, VERSION_NAME_FIELDS, "Unknown")


def extract_engine_names(response: Dict[str, Any]) -> List[str]:
    """Find engine names in a response without assuming a single JSON shape."""
    names = []
    seen = set()

    for item in _walk(response):
        if isinstance(item, dict):
            for field in ENGINE_NAME_FIELDS:
                value = item.get(field)
                if isinstance(value, str) and value.strip():
                    normalized = value.strip()
                    if normalized not in seen:
                        seen.add(normalized)
                        names.append(normalized)
    return names
