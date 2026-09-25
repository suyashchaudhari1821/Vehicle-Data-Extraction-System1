from unittest.mock import Mock, patch

import config
from api_client import APIClient


def _response(status=200, payload=None):
    response = Mock()
    response.status_code = status
    response.json.return_value = payload or {"ok": True}
    response.raise_for_status.return_value = None
    return response


@patch("api_client.time.sleep")
def test_get_does_not_refresh_token_for_every_request(_sleep):
    old_token = config.get_auth_token()
    config.set_auth_token("existing-token")
    try:
        with patch("config.refresh_auth_token") as refresh:
            client = APIClient("cookies")
            client.session.get = Mock(return_value=_response())

            client.get("https://example.test/one")
            client.get("https://example.test/two")

            refresh.assert_not_called()
            assert client.session.get.call_count == 2
    finally:
        config.set_auth_token(old_token)


@patch("api_client.time.sleep")
def test_get_refreshes_token_after_401(_sleep):
    old_token = config.get_auth_token()
    config.set_auth_token("old-token")
    try:
        with patch("config.refresh_auth_token", return_value=True) as refresh:
            client = APIClient("cookies")
            client.session.get = Mock(side_effect=[_response(401), _response()])

            assert client.get("https://example.test/data") == {"ok": True}
            refresh.assert_called_once_with()
            assert client.session.get.call_count == 2
    finally:
        config.set_auth_token(old_token)
