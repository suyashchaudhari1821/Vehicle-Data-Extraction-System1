"""
Configuration module for API access and headers.
Stores base URLs, headers, and authentication cookies.
"""

import os
from typing import Dict, Optional

# Base API URL
BASE_URL = "https://library.fcaservices.com"

# Headers template with User-Agent
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36 Edg/147.0.0.0",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Content-Type": "application/json",
    "Referer": "https://library.fcaservices.com/web/secure/dashboard/user",
    "X-Auth-Token": "971c5794446e43108d2f563360633d5a",
    "X-Requested-With": "XMLHttpRequest",
}

# API Endpoints
MODELS_ENDPOINT = f"{BASE_URL}/connect/api/vehicle/models/categorized"
ENGINES_ENDPOINT = f"{BASE_URL}/connect/api/vehicle/engines"

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
}

# Request delays and retries
REQUEST_DELAY = 0.3  # seconds between requests
MAX_RETRIES = 3
RETRY_DELAY = 1  # seconds between retries

# Cookies (to be injected from browser)
# Format: Copy from browser DevTools > Application > Cookies
COOKIES = "_gid=GA1.2.825328875.1777957635; __zlcmid=1NMmxaZDCZHSLgd; _gat_gtag_UA_73644834_2=1; _ga_ZHRD9EG2P0=GS2.1.s1777960379$o2$g1$t1777963165$j29$l0$h0; _ga=GA1.1.1157187678.1777957635; AWSALBTG=Zn6+8s5K8wRLDWcOPTh7bXLLrIfHxZDwKDcKcOWILWJiHXfhN8aP85sQ44yz6c0mN6PjeI1sZopRfY8xPI/BfWkiq0zVadXcX7WF99YP3g81/gS3QlUh/EQIH0BCXmtugWZsWM0h128EJ+Lf2AmKB2+M9bqpF9e4FqbFPjNywceAQ8bZCk6IMq8fIOL2LtAgk7lYkPBHyK/Ddy0LUep3D5tU0/GBbaYmWyc7uOp5+AX70seaeYOvv852WtM6A9viqeJrDinKB18N5rh3qRDVkPihtVrlvZC2XbyaGC3heJJ0hdjGfhPIDU9207TZiCimJ7YBQb5bvc+dnMh1zGauzCwk/hM=; AWSALBTGCORS=Zn6+8s5K8wRLDWcOPTh7bXLLrIfHxZDwKDcKcOWILWJiHXfhN8aP85sQ44yz6c0mN6PjeI1sZopRfY8xPI/BfWkiq0zVadXcX7WF99YP3g81/gS3QlUh/EQIH0BCXmtugWZsWM0h128EJ+Lf2AmKB2+M9bqpF9e4FqbFPjNywceAQ8bZCk6IMq8fIOL2LtAgk7lYkPBHyK/Ddy0LUep3D5tU0/GBbaYmWyc7uOp5+AX70seaeYOvv852WtM6A9viqeJrDinKB18N5rh3qRDVkPihtVrlvZC2XbyaGC3heJJ0hdjGfhPIDU9207TZiCimJ7YBQb5bvc+dnMh1zGauzCwk/hM=; AWSALB=6pWOyCtqJ+7CsPxCZ6epc8cFHtXVIcxj9dd+cpcfBfyTsBOjmIBiKw6sLZos1GMdNUnrJzbVHNzSIxkH2f4v+zj0VspcTnBvO2CXHwNOez+9LR6YVeHDlowi+LOh; AWSALBCORS=6pWOyCtqJ+7CsPxCZ6epc8cFHtXVIcxj9dd+cpcfBfyTsBOjmIBiKw6sLZos1GMdNUnrJzbVHNzSIxkH2f4v+zj0VspcTnBvO2CXHwNOez+9LR6YVeHDlowi+LOh"


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
