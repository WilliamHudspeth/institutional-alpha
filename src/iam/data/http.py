"""Shared HTTP helper that restricts outbound requests to https.

``urllib.request.urlopen`` happily opens ``file://``, ``ftp://`` and custom
schemes, which is a local-file-read / SSRF hazard if a URL is ever built from
untrusted input. All outbound calls in ``iam`` go through :func:`safe_urlopen`
instead, which refuses anything but ``https``.
"""

from __future__ import annotations

import urllib.request
from typing import Any
from urllib.parse import urlparse

ALLOWED_SCHEMES = frozenset({"https"})


def _scheme_of(url_or_request: str | urllib.request.Request) -> str:
    if isinstance(url_or_request, urllib.request.Request):
        url = url_or_request.full_url
    else:
        url = url_or_request
    return urlparse(url.strip()).scheme.lower()


def safe_urlopen(url_or_request: str | urllib.request.Request, timeout: float = 15.0) -> Any:
    """Open ``url_or_request`` with ``urlopen`` after validating it is https.

    Raises:
        ValueError: if the URL scheme is not https (e.g. ``file://``, ``ftp://``,
            ``http://`` or scheme-less strings).
    """
    scheme = _scheme_of(url_or_request)
    if scheme not in ALLOWED_SCHEMES:
        raise ValueError(f"Refusing to open URL with scheme {scheme!r}; only https is allowed")
    # Scheme is validated against the https allow-list immediately above.
    return urllib.request.urlopen(url_or_request, timeout=timeout)  # nosec B310
