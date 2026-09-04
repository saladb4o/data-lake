"""
M5 TLS governance tests for tls_ssl_context() consumers.

Covers:
  - services.article_reader.ssl_context must be a verifying context
    (CERT_REQUIRED) by default, CERT_NONE only under VNSTOCK_INSECURE_TLS=1.
  - services.stock_service RSS context (ssl_ctx) follows the same policy via
    services.tls_config.tls_ssl_context().
  - The helper itself: cached, verifying by default, insecure only on opt-in.

Subprocess probes are used wherever the env flag matters, because
tls_config reads VNSTOCK_INSECURE_TLS once at import time.
No network access anywhere in this module.
"""

import os
import ssl
import sys
import subprocess

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------------------
# Default (no env flag): everything verifies
# ---------------------------------------------------------------------------

def test_article_reader_context_verifies_by_default(monkeypatch):
    from services import tls_config
    monkeypatch.setattr(tls_config, "_INSECURE_TLS", False)
    monkeypatch.setattr(tls_config, "TLS_VERIFY", True)
    monkeypatch.setattr(tls_config, "_ssl_context", None)
    import services.article_reader as ar
    monkeypatch.setattr(ar, "ssl_context", tls_config.tls_ssl_context())

    ctx = ar.ssl_context
    assert isinstance(ctx, ssl.SSLContext)
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname is True


def test_stock_service_rss_context_verifies_by_default(monkeypatch):
    from services import tls_config
    monkeypatch.setattr(tls_config, "_INSECURE_TLS", False)
    monkeypatch.setattr(tls_config, "TLS_VERIFY", True)
    monkeypatch.setattr(tls_config, "_ssl_context", None)
    import services.stock_service as ss

    ctx = ss.tls_ssl_context()
    assert isinstance(ctx, ssl.SSLContext)
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname is True


def test_tls_ssl_context_helper_is_cached_and_strict(monkeypatch):
    from services import tls_config
    monkeypatch.setattr(tls_config, "_INSECURE_TLS", False)
    monkeypatch.setattr(tls_config, "TLS_VERIFY", True)
    monkeypatch.setattr(tls_config, "_ssl_context", None)

    ctx1 = tls_config.tls_ssl_context()
    ctx2 = tls_config.tls_ssl_context()
    assert ctx1 is ctx2, "tls_ssl_context() must return the cached instance"
    assert ctx1.verify_mode == ssl.CERT_REQUIRED


def test_no_hardcoded_cert_none_left_in_services_sources():
    import inspect

    import services.article_reader as ar
    import services.stock_service as ss

    for mod in (ar, ss):
        src = inspect.getsource(mod)
        assert "CERT_NONE" not in src, (
            f"{mod.__name__} must not hardcode CERT_NONE; use "
            "services.tls_config.tls_ssl_context()"
        )
        assert "check_hostname = False" not in src


# ---------------------------------------------------------------------------
# Opt-in probe (VNSTOCK_INSECURE_TLS=1) in a fresh subprocess per consumer
# ---------------------------------------------------------------------------

_PROBE_BODY = (
    "import os, ssl\n"
    "if 'VNSTOCK_INSECURE_TLS' not in os.environ:\n"
    "    os.environ['VNSTOCK_INSECURE_TLS'] = '0'\n"
    "import {module} as m\n"
    "ctx = m.{attr}\n"
    "print('CTXMODE:', ctx.verify_mode)\n"
)


def _run_ctx_probe(module: str, attr: str, env_extra: dict) -> ssl.VerifyMode:
    env = {k: v for k, v in os.environ.items()}
    if "VNSTOCK_INSECURE_TLS" in env_extra:
        env["VNSTOCK_INSECURE_TLS"] = env_extra["VNSTOCK_INSECURE_TLS"]
    else:
        env["VNSTOCK_INSECURE_TLS"] = "0"
    env["PYTHONPATH"] = PROJECT_ROOT
    proc = subprocess.run(
        [sys.executable, "-c", _PROBE_BODY.format(module=module, attr=attr)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=PROJECT_ROOT, env=env, timeout=300,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    line = next(l for l in proc.stdout.splitlines() if l.startswith("CTXMODE:"))
    return line.split(":", 1)[1].strip()


def test_article_reader_insecure_optin_flips_to_cert_none():
    assert _run_ctx_probe(
        "services.article_reader", "ssl_context", {}
    ) == str(ssl.CERT_REQUIRED)
    assert _run_ctx_probe(
        "services.article_reader", "ssl_context", {"VNSTOCK_INSECURE_TLS": "1"}
    ) == str(ssl.CERT_NONE)


def test_stock_service_rss_context_insecure_optin_flips_to_cert_none():
    assert _run_ctx_probe(
        "services.stock_service", "tls_ssl_context()", {}
    ) == str(ssl.CERT_REQUIRED)
    assert _run_ctx_probe(
        "services.stock_service", "tls_ssl_context()",
        {"VNSTOCK_INSECURE_TLS": "1"},
    ) == str(ssl.CERT_NONE)
