import hashlib
import hmac

import pytest

from app.core import webhook_delivery as wd
from app.core.exceptions import ValidationError


def test_signature_matches_documented_format():
    sig = wd.sign("whsec_x", b'{"a":1}', ts=1700000000)
    mac = hmac.new(b"whsec_x", b'1700000000.{"a":1}', hashlib.sha256).hexdigest()
    assert sig == f"t=1700000000,v1={mac}"


@pytest.mark.parametrize("url", [
    "http://example.com/hook",          # not https
    "https://127.0.0.1/hook",           # loopback
    "https://10.0.0.5/hook",            # private
    "https://169.254.169.254/latest",   # cloud metadata
    "https://localhost/hook",
    "not a url",
])
def test_unsafe_urls_rejected(url):
    with pytest.raises(ValidationError):
        wd.assert_public_https_url(url)
