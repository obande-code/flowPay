import hashlib
import secrets

from .models import ApiKey

KEY_PREFIX = 'fp_live_'


def hash_key(raw_key):
    return hashlib.sha256(raw_key.encode()).hexdigest()


def create_api_key(business, name):
    """Create a key and return the raw value. Only its hash is stored."""
    raw_key = KEY_PREFIX + secrets.token_urlsafe(32)
    ApiKey.objects.create(
        business=business,
        name=name,
        key_prefix=raw_key[:12],
        key_hash=hash_key(raw_key),
    )
    return raw_key
