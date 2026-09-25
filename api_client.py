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
        self._auth_initialized = False
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
                # A database refresh can make thousands of API calls. Refreshing
                # the token before every call doubles the network traffic and can
                # make long builds time out. Use the supplied token when present,
                # then refresh only when it is missing or the server returns 401.
                if not self._auth_initialized:
                    self._auth_initialized = True
                    if not config.get_auth_token():
                        config.refresh_auth_token()
                
                headers = self._prepare_headers()
                time.sleep(config.REQUEST_DELAY)
                response = self.session.get(
                    endpoint,
                    headers=headers,
                    params=params,
                    timeout=30
                )

                if response.status_code == 401:
                    if not config.refresh_auth_token():
                        raise Exception("401 Unauthorized: cookies are expired or invalid")
                    retries += 1
                    if retries >= config.MAX_RETRIES:
                        raise Exception("401 Unauthorized after refreshing authentication")
                    continue

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
