"""
TLS configuration — single source of truth for the whole project (M5).

Certificate verification is ON by default. The ONLY way to opt out is to set
VNSTOCK_INSECURE_TLS=1 in the environment BEFORE importing any module that
performs HTTP requests; in that opt-out mode the InsecureRequestWarning noise
is suppressed as well. Any other value (including unset) keeps verification
strict and leaves urllib3 warnings untouched.
"""

import os
import ssl
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

import urllib3

_INSECURE_TLS = os.environ.get("VNSTOCK_INSECURE_TLS", "").strip() == "1"

if _INSECURE_TLS:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    try:
        ssl._create_default_https_context = ssl._create_unverified_context
    except Exception:
        pass


def tls_verify() -> bool:
    """Whether outgoing HTTPS requests must verify TLS certificates."""
    return not _INSECURE_TLS


def insecure_tls_opted_out() -> bool:
    """True iff VNSTOCK_INSECURE_TLS=1 was set at import time."""
    return _INSECURE_TLS


def configure_urllib_warnings() -> None:
    """
    Apply the warning policy: suppress InsecureRequestWarning only in the
    explicit opt-out mode. Idempotent; safe to call repeatedly.
    """
    if _INSECURE_TLS:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


if _INSECURE_TLS:
    # Explicit opt-in mode ONLY: make requests skip certificate verification
    import requests
    import requests.adapters

    _original_adapter_send = requests.adapters.HTTPAdapter.send

    def _insecure_adapter_send(self, request, stream=False, timeout=None, verify=True, cert=None, proxies=None):  # type: ignore[no-untyped-def]
        return _original_adapter_send(self, request, stream=stream, timeout=timeout, verify=False, cert=cert, proxies=proxies)

    requests.adapters.HTTPAdapter.send = _insecure_adapter_send

    _original_session_send = requests.sessions.Session.send

    def _insecure_session_send(self, request, **kwargs):  # type: ignore[no-untyped-def]
        kwargs["verify"] = False
        return _original_session_send(self, request, **kwargs)

    requests.sessions.Session.send = _insecure_session_send
    requests.Session.send = _insecure_session_send

    # Also patch Session.__init__ so new instances report verify=False
    # (Session.__init__ normally hardcodes self.verify = True)
    _original_session_init = requests.sessions.Session.__init__

    def _insecure_session_init(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        _original_session_init(self, *args, **kwargs)
        self.verify = False

    requests.sessions.Session.__init__ = _insecure_session_init
    requests.Session.__init__ = _insecure_session_init


# Backwards-compatible constant used by unified_data_service and tests.
TLS_VERIFY = not _INSECURE_TLS


_ssl_context: Optional[ssl.SSLContext] = None


def tls_ssl_context() -> ssl.SSLContext:
    """
    Module-level cached SSL context for urllib.request calls, mirroring the
    tls_verify() policy: a strict verifying context by default; under the
    explicit VNSTOCK_INSECURE_TLS=1 opt-out, a non-verifying context.
    """
    global _ssl_context
    if _ssl_context is None:
        ctx = ssl.create_default_context()
        if _INSECURE_TLS:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        _ssl_context = ctx
    return _ssl_context
