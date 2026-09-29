"""Issue or rotate a service key for a sibling system. The key is printed once and cannot be recovered."""

from django.core.management.base import BaseCommand

from integration.models import ServiceClient

KNOWN_SCOPES = {"sites:read", "marks:read"}


class Command(BaseCommand):
    help = "Create or rotate a service client key, e.g. --name srms --scopes staff:read org:read"

    def add_arguments(self, parser):
        parser.add_argument("--name", required=True)
        parser.add_argument("--scopes", nargs="+", required=True)
        parser.add_argument("--quiet", action="store_true", help="Print only the key (for scripts)")

    def handle(self, *args, **options):
        unknown = set(options["scopes"]) - KNOWN_SCOPES
        if unknown:
            self.stderr.write(f"Unknown scopes: {sorted(unknown)}. Known: {sorted(KNOWN_SCOPES)}")
            return
        client, key = ServiceClient.issue(options["name"], options["scopes"])
        if options["quiet"]:
            self.stdout.write(key)
            return
        self.stdout.write(self.style.SUCCESS(f"Service client '{client.name}' scopes={client.scopes}"))
        self.stdout.write("Key (shown once; put it in the caller's .env, never in version control):")
        self.stdout.write(key)
