"""Make a VAPID key pair for push notices (item 4.04).

    python manage.py vapid_keys

Prints the two settings to add to the server's secrets. The private key signs every push notice: keep it
with the other secrets, never in the repository. Changing it means everyone turns push on again.
"""

import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from django.core.management.base import BaseCommand


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def make_keys() -> tuple[str, str]:
    """(public, private) as base64url: the browser's applicationServerKey, and the raw private number."""
    key = ec.generate_private_key(ec.SECP256R1())
    private = key.private_numbers().private_value.to_bytes(32, "big")
    public = key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    return _b64(public), _b64(private)


class Command(BaseCommand):
    help = "Print a new VAPID key pair for push notices, as the two settings to keep as server secrets."

    def handle(self, *args, **options):
        public, private = make_keys()
        self.stdout.write(f"VAPID_PUBLIC_KEY={public}\nVAPID_PRIVATE_KEY={private}\n")
