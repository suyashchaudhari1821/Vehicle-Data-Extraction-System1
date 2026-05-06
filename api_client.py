"""
API client module for session-based authentication and API calls.
Handles retry logic, delays, and session management.
"""

import time
import requests
from typing import Dict, Optional, Any
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry as URLRetry

import config


class APIClient:
    """Session-based API client with retry logic and authentication."""
    
    def __init__(self, cookies: str):
        """
        Initialize API client with authentication cookies.
        
        Args:
            cookies: Cookie string from browser DevTools
        """
        self.session = requests.Session()
        self.cookies = cookies
        self._setup_session()
    
    def _setup_session(self) -> None:
        """Configure session with retry strategy."""
        retry_strategy = URLRetry(
            total=config.MAX_RETRIES,
            backoff_factor=config.RETRY_DELAY,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
    
    def _prepare_headers(self, additional: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """
        Prepare headers with authentication cookie.
        
        Args:
            additional: Additional headers to merge
            
        Returns:
            Dictionary of headers with Cookie
        """
        headers = config.get_headers(additional)
        if self.cookies:
            headers["Cookie"] = self.cookies
        return headers
    
    def get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Make GET request with retry and delay. Automatically refreshes token on 401 errors.
        
        Args:
            endpoint: Full API endpoint URL
            params: Query parameters
            
        Returns:
            JSON response as dictionary
            
        Raises:
            Exception: If request fails after retries
        """
        retries = 0
        while retries < config.MAX_RETRIES:
            try:
                # Refresh token before each request to ensure it's valid
                config.refresh_auth_token()
                
                headers = self._prepare_headers()
                token = headers.get("X-Auth-Token", "NOT SET")
                print(f"[DEBUG] Using Token: {token[:30]}...")
                
                time.sleep(config.REQUEST_DELAY)
                response = self.session.get(
                    endpoint,
                    headers=headers,
                    params=params,
                    timeout=30
                )
                response.raise_for_status()
                return response.json()
            
            except requests.exceptions.RequestException as e:
                retries += 1
                if retries >= config.MAX_RETRIES:
                    raise Exception(f"Failed after {config.MAX_RETRIES} retries: {str(e)}")
                print(f"Request failed (attempt {retries}), retrying in {config.RETRY_DELAY}s...")
                time.sleep(config.RETRY_DELAY)
    
    def update_cookies(self, cookie_string: str) -> None:
        """
        Update session cookies (for when cookies expire).
        
        Args:
            cookie_string: New cookie string from browser DevTools
        """
        self.cookies = cookie_string
    
    def close(self) -> None:
        """Close session."""
        self.session.close()
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


def get_api_client() -> APIClient:
    """
    Create and return API client with current cookies.
    
    Returns:
        APIClient instance
    """
    cookies = config.get_cookies()
    return APIClient(cookies)
