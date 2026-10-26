"""Minimal standard-library client for the documented Nebius chat API."""
import json
import os
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

DEFAULT_ENDPOINT = 'https://api.tokenfactory.nebius.com/v1'
ALLOWED_HOSTS = {'api.tokenfactory.nebius.com', 'api.tokenfactory.us-central1.nebius.com'}


def validate_endpoint(endpoint):
    endpoint = endpoint.rstrip('/')
    parts = urlsplit(endpoint)
    if (parts.scheme != 'https' or parts.netloc not in ALLOWED_HOSTS
            or parts.path != '/v1' or parts.query or parts.fragment):
        raise ValueError('Use an official HTTPS Nebius Token Factory /v1 endpoint')
    return endpoint


def sanitized(value, api_key):
    text = json.dumps(value)
    if api_key:
        text = text.replace(api_key, '[REDACTED]')
    return json.loads(text)


def request_json(path, payload=None):
    key = os.environ.get('NEBIUS_API_KEY', '').strip()
    if not key:
        raise RuntimeError('NEBIUS_API_KEY is not configured; no request sent')
    endpoint = validate_endpoint(os.environ.get('NEBIUS_BASE_URL', DEFAULT_ENDPOINT))
    if path not in {'models', 'chat/completions'}:
        raise ValueError('Unsupported API route')
    data = None if payload is None else json.dumps(payload).encode()
    request = Request(endpoint + '/' + path, data=data, headers={
        'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json',
    })
    # No automatic retry: one call is one recorded model attempt.
    try:
        with urlopen(request, timeout=120) as response:
            body = json.load(response)
            metadata = {'endpoint': endpoint, 'http_status': response.status,
                        'request_id': response.headers.get('x-request-id')}
    except HTTPError as error:
        detail = error.read(8192).decode(errors='replace').replace(key, '[REDACTED]')
        raise RuntimeError(f'Nebius HTTP {error.code}: {detail}') from None
    return sanitized(body, key), metadata
