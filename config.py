"""
Configuration module for API access and headers.
FCA credentials are normally updated from the app sidebar at runtime.
"""

import os
import time
from typing import Dict, Optional


def _setting(*names: str, default: str = "") -> str:
    """Read an optional startup prefill from environment variables or Streamlit secrets."""
    for name in names:
        value = os.environ.get(name)
        if value:
            return value

    try:
        import streamlit as st

        for name in names:
            value = st.secrets.get(name, "")
            if value:
                return str(value)
    except Exception:
        pass

    return default


# Base API URL
BASE_URL = "https://library.fcaservices.com"

# Headers template with User-Agent
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36 Edg/147.0.0.0",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Content-Type": "application/json",
    "Referer": "https://library.fcaservices.com/web/secure/dashboard/user",
    "X-Auth-Token": _setting("FCA_X_AUTH_TOKEN", "X_AUTH_TOKEN", "AUTH_TOKEN"),
    "X-Requested-With": "XMLHttpRequest",
}

# API Endpoints
MODELS_ENDPOINT = f"{BASE_URL}/connect/api/vehicle/models/categorized"
ENGINES_ENDPOINT = f"{BASE_URL}/connect/api/vehicle/engines"
MODEL_LOCALE = "en_US"


def get_model_request_params(brand_code: str) -> Dict[str, str]:
    """Return the same model-list params used by the website UI."""
    cache_buster = str(int(time.time() * 1000))
    return {
        "nocache": cache_buster,
        "locale": MODEL_LOCALE,
        "brandCode": brand_code,
        "_": cache_buster,
    }

# Brand codes for API - ALL brands (current, legacy, international)
BRAND_CODES = {
    # Current Brands
    'ABARTH': 'ABARTH',
    'ALFA ROMEO': 'ALFA',
    'CHRYSLER': 'CHRYSLER',
    'CITROËN': 'CITROEN',
    'DS': 'DS',
    'DODGE': 'DODGE',
    'FIAT': 'FIAT',
    'FIAT PROFESSIONAL': 'FIAT_PROFESSIONAL',
    'JEEP': 'JEEP',
    'LANCIA': 'LANCIA',
    'OPEL': 'OPEL',
    'PEUGEOT': 'PEUGEOT',
    'RAM': 'RAM',
    # Legacy Brands
    'EAGLE': 'EAGLE',
    'PLYMOUTH': 'PLYMOUTH',
    'VOLKSWAGEN': 'VW',
    # Regional/International Brands
    'GA': 'GA',
    'GU': 'GU',
    'WD': 'WD',
}

# Some API model names differ from the public website name in specific markets.
# Keep these mappings keyed by API brand code so they only affect the right brand.
MODEL_NAME_ALIASES = {
    ('CITROEN', 'JUMPER'): 'RELAY',
    ('CITROEN', 'JUMPY'): 'DISPATCH',
    ('CITROEN', 'JUMPY COMBI'): 'DISPATCH COMBI',
}


def get_model_display_name(brand_code: str, model_name: str) -> str:
    """Return the website-facing model name for an API model name."""
    if not model_name:
        return model_name

    alias_key = (brand_code.upper(), model_name.strip().upper())
    return MODEL_NAME_ALIASES.get(alias_key, model_name)


def get_version_display_name(brand_code: str, source_model_name: str, version_name: str) -> str:
    """Return version name with market-facing model names."""
    if not version_name:
        return version_name

    display_model_name = get_model_display_name(brand_code, source_model_name)
    if not source_model_name or display_model_name == source_model_name:
        return version_name

    return version_name.replace(source_model_name, display_model_name)


# Request delays and retries
REQUEST_DELAY = 0.3  # seconds between requests
MAX_RETRIES = 3
RETRY_DELAY = 1  # seconds between retries

# Optional startup cookies. The app sidebar overrides this at runtime.
# Format: Copy from browser DevTools > Application > Cookies.
COOKIES = _setting("FCA_COOKIES", "FCA_COOKIE", "COOKIES")


def get_headers(additional_headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """
    Get headers with optional additional fields.
    
    Args:
        additional_headers: Additional headers to merge
        
    Returns:
        Dictionary of headers
    """
    headers = DEFAULT_HEADERS.copy()
    if additional_headers:
        headers.update(additional_headers)
    return headers


def set_cookies(cookie_string: str) -> None:
    """
    Update authentication cookies (for session refresh).
    
    Args:
        cookie_string: Cookie string from browser DevTools
    """
    global COOKIES
    COOKIES = cookie_string


def get_cookies() -> str:
    """Get current authentication cookies."""
    return COOKIES


def set_auth_token(token: str) -> None:
    """
    Update authentication token.
    
    Args:
        token: New X-Auth-Token value from browser DevTools
    """
    global DEFAULT_HEADERS
    DEFAULT_HEADERS["X-Auth-Token"] = token


def get_auth_token() -> str:
    """Get current X-Auth-Token."""
    return DEFAULT_HEADERS.get("X-Auth-Token", "")


def refresh_auth_token() -> bool:
    """
    Fetch a fresh X-Auth-Token from the API using existing cookies.
    Updates DEFAULT_HEADERS with the new token.
    
    Returns:
        True if token was refreshed successfully, False otherwise
    """
    import requests
    import json
    
    try:
        # Fetch fresh token using cookies
        token_url = f"{BASE_URL}/web/service/auth/token"
        headers = {
            "User-Agent": DEFAULT_HEADERS["User-Agent"],
            "Cookie": COOKIES,
        }
        
        response = requests.get(token_url, headers=headers, timeout=10)
        
        if response.status_code == 401:
            print(f"[TOKEN REFRESH] Cookies are EXPIRED or INVALID (401 error)")
            print(f"[TOKEN REFRESH] Please update your cookies in the Streamlit sidebar")
            return False
        
        response.raise_for_status()
        
        # Parse token from response
        token_data = response.json()
        new_token = token_data.get("token") or token_data
        
        if new_token and isinstance(new_token, str):
            set_auth_token(new_token)
            print(f"[TOKEN REFRESH] New token obtained: {new_token[:20]}...")
            return True
        else:
            print(f"[TOKEN REFRESH] Failed: Invalid token format - {token_data}")
            return False
            
    except Exception as e:
        print(f"[TOKEN REFRESH] Failed to refresh token: {str(e)}")
        return False
