"""Service Library torque verification helpers."""

import re
import time
from difflib import SequenceMatcher
from io import StringIO
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd
import requests

import config
import parser


CONFIG_LEVEL = "YEAR_MODEL_ENGINE"
REQUEST_TIMEOUT = 30


def _headers(accept: str = "application/json, text/javascript, */*; q=0.01") -> Dict[str, str]:
    headers = config.get_headers({"Accept": accept})
    cookies = config.get_cookies()
    if cookies:
        headers["Cookie"] = cookies
    return headers


def _get_json(path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    response = requests.get(
        f"{config.BASE_URL}{path}",
        headers=_headers(),
        params=params,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def _get_text(path: str, params: Optional[Dict[str, Any]] = None) -> str:
    response = requests.get(
        f"{config.BASE_URL}{path}",
        headers=_headers("*/*"),
        params=params,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.text


def _walk(value: Any) -> Iterable[Any]:
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _match_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _compact_code(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).upper()


def _model_code_from_name(model_name: str) -> str:
    match = re.match(r"\s*([A-Z0-9/]+)\s*-", model_name or "", re.IGNORECASE)
    return _compact_code(match.group(1)) if match else ""


def _text_score(needle: str, haystack: str) -> float:
    needle_key = _match_key(needle)
    haystack_key = _match_key(haystack)
    if not needle_key or not haystack_key:
        return 0.0
    if needle_key == haystack_key:
        return 1.0
    if needle_key in haystack_key or haystack_key in needle_key:
        return 0.92
    needle_terms = set(needle_key.split())
    haystack_terms = set(haystack_key.split())
    overlap = len(needle_terms & haystack_terms) / max(len(needle_terms), 1)
    ratio = SequenceMatcher(None, needle_key, haystack_key).ratio()
    return max(ratio, overlap)


def _numbers(value: Any) -> List[float]:
    numbers = []
    for raw in re.findall(r"\d+(?:\.\d+)?", str(value or "")):
        try:
            numbers.append(float(raw))
        except ValueError:
            pass
    return numbers


def _torque_match(target: str, found: str) -> bool:
    target_numbers = _numbers(target)
    found_numbers = _numbers(found)
    if target_numbers:
        return any(
            abs(target_number - found_number) < 0.01
            for target_number in target_numbers
            for found_number in found_numbers
        )

    target_key = _match_key(target)
    return bool(target_key and target_key in _match_key(found))


def _find_vehicle_versions(model_year: int, vehicle_family: str) -> List[Dict[str, Any]]:
    family_code = _compact_code(vehicle_family)
    matches = []
    priority_brand_codes = {
        "JL": ["JEEP"],
        "JT": ["JEEP"],
        "WL": ["JEEP"],
        "DJ": ["RAM"],
        "DT": ["RAM"],
        "DS": ["RAM", "DODGE"],
        "LB": ["DODGE"],
    }
    preferred_codes = priority_brand_codes.get(family_code, [])
    brand_items = list(config.BRAND_CODES.items())
    brand_items.sort(key=lambda item: (item[1] not in preferred_codes, item[0]))

    for brand_name, brand_code in brand_items:
        response = _get_json(
            "/connect/api/vehicle/models/categorized",
            params=config.get_model_request_params(brand_code),
        )
        for model in parser.extract_models(response):
            model_name = parser.get_model_name(model)
            model_code = _model_code_from_name(model_name)
            for version in parser.extract_versions(model):
                version_name = parser.get_version_name(version)
                version_model_code = _compact_code(version.get("modelCode") or model_code)
                if str(version_name).strip() != str(model_year):
                    continue
                if version_model_code != family_code and model_code != family_code:
                    continue
                matches.append(
                    {
                        "brand": brand_name,
                        "brand_code": brand_code,
                        "model": config.get_model_display_name(brand_code, model_name),
                        "model_code": version_model_code or model_code,
                        "version": version_name,
                        "model_version_id": parser.get_version_id(version),
                    }
                )
        if matches and brand_code in preferred_codes:
            break

    return matches


def _extract_engine_options(response: Dict[str, Any]) -> List[Dict[str, str]]:
    engines = []
    seen = set()
    for item in _walk(response):
        if not isinstance(item, dict):
            continue
        engine_name = _clean_text(
            item.get("engine")
            or item.get("engineName")
            or item.get("engineDescription")
            or item.get("motor")
            or item.get("powertrain")
        )
        engine_code = _clean_text(item.get("salesCode") or item.get("engineCode") or item.get("code"))
        engine_id = _clean_text(item.get("modelVersionEngineId"))
        if not engine_name:
            continue
        marker = (engine_name, engine_code, engine_id)
        if marker in seen:
            continue
        seen.add(marker)
        engines.append({"engine": engine_name, "engine_code": engine_code, "model_version_engine_id": engine_id})
    return engines


def _find_engine(vehicle: Dict[str, Any], engine_code: str) -> Optional[Dict[str, str]]:
    response = _get_json("/connect/api/vehicle/engines", params={"modelVersionId": vehicle["model_version_id"]})
    wanted_code = _compact_code(engine_code)
    for engine in _extract_engine_options(response):
        if _compact_code(engine["engine_code"]) == wanted_code:
            return engine
    return None


def _get_service_book(model_version_engine_id: str) -> Optional[Dict[str, Any]]:
    response = _get_json(
        f"/connect/api/vehicle-tools/{CONFIG_LEVEL}/{model_version_engine_id}",
        params={"locale": config.MODEL_LOCALE, "nocache": str(int(time.time() * 1000))},
    )
    for book in response.get("books", []):
        if book.get("disciplineCode") == "service-info":
            return book
    return None


def _collect_torque_leaves(toc_response: Dict[str, Any]) -> List[Dict[str, str]]:
    leaves = []

    def visit(node: Dict[str, Any], path: List[str]) -> None:
        name = _clean_text(node.get("name"))
        current_path = path + ([name] if name else [])
        children = node.get("nodes") or []
        if children:
            for child in children:
                if isinstance(child, dict):
                    visit(child, current_path)
            return

        info_text = f"{name} {node.get('infoType', '')}"
        if "torque" not in info_text.lower():
            return
        content_link_id = node.get("contentLinkId")
        info_code = node.get("infoCode")
        if content_link_id and info_code:
            leaves.append(
                {
                    "path": " / ".join(current_path),
                    "name": name,
                    "info_type": _clean_text(node.get("infoType")),
                    "content_link_id": content_link_id,
                    "info_code": info_code,
                }
            )

    for root in toc_response.get("nodes", []):
        if isinstance(root, dict):
            visit(root, [])
    return leaves


def _rank_leaves(leaves: List[Dict[str, str]], vsc_name: str) -> List[Dict[str, str]]:
    ranked = []
    for leaf in leaves:
        score = _text_score(vsc_name, leaf["path"])
        item = leaf.copy()
        item["vsc_score"] = score
        ranked.append(item)
    return sorted(ranked, key=lambda item: item["vsc_score"], reverse=True)


def _extract_torque_rows(content_html: str, leaf: Dict[str, str]) -> List[Dict[str, str]]:
    rows = []
    try:
        tables = pd.read_html(StringIO(content_html))
    except ValueError:
        return rows

    for table in tables:
        normalized_columns = [_match_key(column).upper() for column in table.columns]
        if "DESCRIPTION" not in normalized_columns or "SPECIFICATION" not in normalized_columns:
            continue
        description_column = table.columns[normalized_columns.index("DESCRIPTION")]
        specification_column = table.columns[normalized_columns.index("SPECIFICATION")]
        comment_column = None
        if "COMMENT" in normalized_columns:
            comment_column = table.columns[normalized_columns.index("COMMENT")]

        for _, row in table.iterrows():
            description = _clean_text(row.get(description_column))
            specification = _clean_text(row.get(specification_column))
            if not description or description.lower() == "nan" or not specification or specification.lower() == "nan":
                continue
            rows.append(
                {
                    "page": leaf["path"],
                    "description": description,
                    "specification": specification,
                    "comment": _clean_text(row.get(comment_column)) if comment_column is not None else "",
                }
            )
    return rows


def verify_torque(
    model_year: int,
    vehicle_family: str,
    engine_code: str,
    vsc_name: str,
    description: str,
    target_torque: str,
) -> Dict[str, Any]:
    """Verify a torque row against Service Library for one vehicle/engine."""
    vehicles = _find_vehicle_versions(model_year, vehicle_family)
    if not vehicles:
        return {
            "vehicle_match": False,
            "engine_match": False,
            "vsc_match": False,
            "description_match": False,
            "torque_match": False,
            "message": "No vehicle found for this model year and VEH FAM.",
            "candidates": [],
        }

    checked_engines = []
    selected_vehicle = None
    selected_engine = None
    for vehicle in vehicles:
        engine = _find_engine(vehicle, engine_code)
        checked_engines.append({"vehicle": vehicle, "engine_found": bool(engine)})
        if engine:
            selected_vehicle = vehicle
            selected_engine = engine
            break

    if not selected_vehicle or not selected_engine:
        return {
            "vehicle_match": True,
            "engine_match": False,
            "vsc_match": False,
            "description_match": False,
            "torque_match": False,
            "message": "Vehicle found, but engine code was not found for that vehicle.",
            "vehicles": vehicles,
            "checked_engines": checked_engines,
            "candidates": [],
        }

    service_book = _get_service_book(selected_engine["model_version_engine_id"])
    if not service_book:
        return {
            "vehicle_match": True,
            "engine_match": True,
            "vsc_match": False,
            "description_match": False,
            "torque_match": False,
            "message": "Vehicle and engine found, but Service Information book was not available.",
            "vehicle": selected_vehicle,
            "engine": selected_engine,
            "candidates": [],
        }

    toc = _get_json(
        f"/connect/api/toc/{service_book['modelVersionBookId']}/{CONFIG_LEVEL}/{selected_engine['model_version_engine_id']}",
        params={"locale": config.MODEL_LOCALE, "nocache": str(int(time.time() * 1000))},
    )
    leaves = _rank_leaves(_collect_torque_leaves(toc), vsc_name)
    if not leaves:
        return {
            "vehicle_match": True,
            "engine_match": True,
            "vsc_match": False,
            "description_match": False,
            "torque_match": False,
            "message": "No torque specification pages were found.",
            "vehicle": selected_vehicle,
            "engine": selected_engine,
            "candidates": [],
        }

    rows = []
    # VSC name is a ranking hint. Search the best pages first, but keep enough
    # breadth for cases where Excel wording differs from Service Library TOC.
    strong_vsc_leaves = [leaf for leaf in leaves if leaf["vsc_score"] >= 0.35]
    leaves_to_check = strong_vsc_leaves[:12] if strong_vsc_leaves else leaves[:25]

    checked_pages = 0
    for leaf in leaves_to_check:
        checked_pages += 1
        html = _get_text(f"/connect/api/content/raw/{leaf['content_link_id']}")
        for row in _extract_torque_rows(html, leaf):
            row["vsc_score"] = leaf["vsc_score"]
            row["description_score"] = _text_score(description, row["description"])
            row["torque_match"] = _torque_match(target_torque, row["specification"])
            row["score"] = row["description_score"] + (0.35 if row["torque_match"] else 0) + (0.15 * leaf["vsc_score"])
            rows.append(row)
        if any(row["description_score"] >= 0.95 and row["torque_match"] for row in rows):
            break

    candidates = sorted(rows, key=lambda row: row["score"], reverse=True)[:10]
    best = candidates[0] if candidates else None
    return {
        "vehicle_match": True,
        "engine_match": True,
        "vsc_match": bool(leaves and leaves[0]["vsc_score"] >= 0.35),
        "description_match": bool(best and best["description_score"] >= 0.72),
        "torque_match": bool(best and best["torque_match"]),
        "message": "Verification completed.",
        "vehicle": selected_vehicle,
        "engine": selected_engine,
        "best": best,
        "candidates": candidates,
        "torque_pages_checked": checked_pages,
        "torque_pages_found": len(leaves),
    }
