from function_app import sanitize_partition_key, normalize_url, is_valid_url, perform_check
from unittest.mock import patch, MagicMock
import requests

def test_normalize_url_adds_https_when_missing():
    assert normalize_url("example.com") == "https://example.com"

def test_normalize_url_keeps_https_if_present():
    assert normalize_url("https://example.com") == "https://example.com"

def test_normalize_url_keeps_http_if_present():
    assert normalize_url("http://example.com") == "http://example.com"

def test_sanitize_partition_key_removes_protocol_and_replaces_slashes():
    assert sanitize_partition_key("https://example.com/path/to/resource") == "example.com_path_to_resource"

def test_sanitize_partition_key_no_protocol():
    assert sanitize_partition_key("example.com/path/to/resource") == "example.com_path_to_resource"

def test_is_valid_url_valid():
    assert is_valid_url("https://example.com") == True
    assert is_valid_url("http://example.com") == True
    assert is_valid_url("https://example.com/path/to/resource") == True

def test_is_valid_url_invalid():
    assert is_valid_url("example.com") == False
    assert is_valid_url("ftp://example.com") == False
    assert is_valid_url("https://example") == False

@patch("function_app.requests.get")
def test_perform_check_operational(mock_get):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_get.return_value = mock_response

    result = perform_check("https://example.com")

    assert result["status"] == "OPERATIONAL"
    assert result["web_status_code"] == 200

@patch("function_app.requests.get")
def test_perform_check_invalid_url(mock_get):
    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_get.return_value = mock_response

    result = perform_check("https://httpstat.us/404")

    assert result["status"] == "DOWN"
    assert result["web_status_code"] == 404

@patch("function_app.requests.get")
def test_perform_check_connection_error(mock_get):
    mock_get.side_effect = requests.exceptions.ConnectionError("Failed to establish a new connection")

    result = perform_check("https://thissitedoesnotexist12345.com")

    assert result["status"] == "DOWN"
    assert result["web_status_code"] is None