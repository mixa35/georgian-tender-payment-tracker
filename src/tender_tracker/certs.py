"""TLS trust material for the tender portal.

The State Procurement Agency's server (tenders.procurement.gov.ge) serves an
*incomplete* certificate chain: it presents only its leaf certificate and omits
the "Thawte EV RSA CA G2" intermediate that links it to the trusted DigiCert
Global Root G2. Browsers paper over this by fetching the missing intermediate
themselves, but ``requests``/OpenSSL does not, so verification fails with
"unable to get local issuer certificate".

We fix this the safe way: bundle the missing intermediate ourselves and verify
against certifi's roots PLUS this intermediate. Full certificate verification
stays enabled. The intermediate below is the genuine public DigiCert/Thawte
intermediate (subject "Thawte EV RSA CA G2", valid until 2030), fetched from
https://cacerts.digicert.com/ThawteEVRSACAG2.crt.pem
sha256: 30a4dabacc0be9d275448915e4df646a8fda548c61b3c4cfc6be826b2ad9a60f

It is embedded as a string constant (rather than a data file) so it always
ships with the installed package, matching how CI runs the tracker.
"""

from __future__ import annotations

import hashlib
import tempfile
from functools import lru_cache
from pathlib import Path

import certifi

# Subject string of the bundled intermediate; used by tests and for clarity.
THAWTE_INTERMEDIATE_SUBJECT = "Thawte EV RSA CA G2"

# The missing intermediate that tenders.procurement.gov.ge fails to serve.
THAWTE_INTERMEDIATE_PEM = """\
-----BEGIN CERTIFICATE-----
MIIFOjCCBCKgAwIBAgIQB8LG0yxvDgqrrA3Q+fzVszANBgkqhkiG9w0BAQsFADBh
MQswCQYDVQQGEwJVUzEVMBMGA1UEChMMRGlnaUNlcnQgSW5jMRkwFwYDVQQLExB3
d3cuZGlnaWNlcnQuY29tMSAwHgYDVQQDExdEaWdpQ2VydCBHbG9iYWwgUm9vdCBH
MjAeFw0yMDA3MDIxMjQzMDJaFw0zMDA3MDIxMjQzMDJaMEIxCzAJBgNVBAYTAlVT
MRUwEwYDVQQKEwxEaWdpQ2VydCBJbmMxHDAaBgNVBAMTE1RoYXd0ZSBFViBSU0Eg
Q0EgRzIwggEiMA0GCSqGSIb3DQEBAQUAA4IBDwAwggEKAoIBAQDZ6jsIHs3bmIoe
7DvnuSvGX375jpWKv25Gf7uz8GZQT3DFVHeRS0NKn5WosqMVNYJKKEImR1Gb2dxl
90/GDypngguJeBVxdTtgGWPpGnuKPXfc6Qy8yKS1SRQsEs2q2EHl0tEU+/vyNro0
DDZcox947My8htb1dLx0Q/y9KjEuagQ5AXeLidtiaiAyKnThZRslD8EK/EcHRvkP
AVMSfGyCVmho3VLBP7LAlLA/RyrAX282OfK8lPZqsASNsOQhmsZPT3IuQhXz7RXc
nCpBM+GfZoFSP6+uO5j8TZMkqLTAuVAsSyGY8zNbzYupA7QmPcIfAwqG1oD9dGah
2GgKoeTnAgMBAAGjggILMIICBzAdBgNVHQ4EFgQUbC7kYbTDub3wyq2mwWh6uNTM
HaAwHwYDVR0jBBgwFoAUTiJUIBiV5uNu5g/6+rkS7QYXjzkwDgYDVR0PAQH/BAQD
AgGGMB0GA1UdJQQWMBQGCCsGAQUFBwMBBggrBgEFBQcDAjASBgNVHRMBAf8ECDAG
AQH/AgEAMDQGCCsGAQUFBwEBBCgwJjAkBggrBgEFBQcwAYYYaHR0cDovL29jc3Au
ZGlnaWNlcnQuY29tMHsGA1UdHwR0MHIwN6A1oDOGMWh0dHA6Ly9jcmwzLmRpZ2lj
ZXJ0LmNvbS9EaWdpQ2VydEdsb2JhbFJvb3RHMi5jcmwwN6A1oDOGMWh0dHA6Ly9j
cmw0LmRpZ2ljZXJ0LmNvbS9EaWdpQ2VydEdsb2JhbFJvb3RHMi5jcmwwgc4GA1Ud
IASBxjCBwzCBwAYEVR0gADCBtzAoBggrBgEFBQcCARYcaHR0cHM6Ly93d3cuZGln
aWNlcnQuY29tL0NQUzCBigYIKwYBBQUHAgIwfgx8QW55IHVzZSBvZiB0aGlzIENl
cnRpZmljYXRlIGNvbnN0aXR1dGVzIGFjY2VwdGFuY2Ugb2YgdGhlIFJlbHlpbmcg
UGFydHkgQWdyZWVtZW50IGxvY2F0ZWQgYXQgaHR0cHM6Ly93d3cuZGlnaWNlcnQu
Y29tL3JwYS11YTANBgkqhkiG9w0BAQsFAAOCAQEADf6H4Rxu128yUZjIR/vkWEv0
PnYKWUQkGXwbqaioq/zjVC/+LrIwBKwEH2aBQyBO/uvMwF+4PSThZKinw51Pfp8w
PcaBMeuQR1PEIYjQN3+NjRpMIFb2CUtbnMsHybKqKSW3rsTT2r2EIBtDrZ3EfeEg
5bfneV6PKvGqcQRZq5BBNTH11tedhcLJB+7F7GRVz8cKCTz0INpQk8gthjBND1+7
CR+ZHTWPqdXGRqiFJ09NTVmohj4dgL3VyOIArpmPbigODbp80fxzoQJepkHFef6q
mniWnIl7HApTrTIV/UN22gbCcL5dosGv69wnOVQomQsalcOkujetA5BruTiB9A==
-----END CERTIFICATE-----
"""


def combined_ca_bundle_contents() -> str:
    """certifi's trusted roots plus the bundled tender-portal intermediate."""
    roots = certifi.contents()
    if not roots.endswith("\n"):
        roots += "\n"
    return roots + THAWTE_INTERMEDIATE_PEM


@lru_cache(maxsize=1)
def combined_ca_bundle_path() -> str:
    """Path to a CA bundle usable as ``requests`` ``verify=``.

    Written once to a stable temp-dir file keyed by content hash, so repeated
    runs reuse it and concurrent processes don't clobber each other.
    """
    contents = combined_ca_bundle_contents()
    digest = hashlib.sha256(contents.encode("utf-8")).hexdigest()[:16]
    path = Path(tempfile.gettempdir()) / f"tender_tracker_ca_{digest}.pem"
    if not path.exists():
        # Write atomically to avoid a partial file under concurrency.
        tmp = path.with_suffix(f".{digest}.tmp")
        tmp.write_text(contents, encoding="utf-8")
        tmp.replace(path)
    return str(path)
