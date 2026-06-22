import ssl
from pathlib import Path

from tender_tracker.certs import (
    THAWTE_INTERMEDIATE_PEM,
    combined_ca_bundle_contents,
    combined_ca_bundle_path,
)
from tender_tracker.config import load_settings
from tender_tracker.logging_utils import build_logger
from tender_tracker.tender_client import TenderPortalClient


def test_embedded_intermediate_is_valid_pem():
    # Loads fully offline; raises if the embedded PEM is malformed.
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.load_verify_locations(cadata=THAWTE_INTERMEDIATE_PEM)
    assert any(
        ("Thawte EV RSA CA G2") in str(cert.get("subject", ()))
        for cert in ctx.get_ca_certs()
    )


def test_combined_bundle_contains_roots_and_intermediate():
    contents = combined_ca_bundle_contents()
    # The bundled intermediate must be present...
    assert THAWTE_INTERMEDIATE_PEM.strip() in contents
    # ...alongside certifi's roots (more than one certificate total).
    assert contents.count("BEGIN CERTIFICATE") > 1


def test_bundle_path_writes_readable_file():
    path = Path(combined_ca_bundle_path())
    assert path.exists()
    assert THAWTE_INTERMEDIATE_PEM.strip() in path.read_text(encoding="utf-8")


def test_client_session_verifies_against_combined_bundle(tmp_path: Path):
    settings = load_settings("config/settings.yaml")
    logger = build_logger(tmp_path / "test.log", "INFO")
    client = TenderPortalClient(settings, logger=logger)
    assert client.session.verify == combined_ca_bundle_path()
