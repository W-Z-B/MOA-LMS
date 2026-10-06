"""Accounts for lecturers, staff and students, opened from the synced person records (item 1.22).

Ported from the HRMS (iam/accounts.py, its items 1.25 and 1.29), with employees read as person references.
Nobody chooses or sees another person's password. An account is opened for a person with no usable password,
and the person chooses their own through a one-use link sent to their email address. The same kind of link
resets a forgotten password. A link stops working once a password is chosen (it is signed over the password
hash and the last sign-in) and after its time limit: INVITATION_DAYS for invitations, PASSWORD_RESET_MINUTES
for resets.

The username is the person's own number: the student number from the SRMS, the employee number from the
HRMS. When the person record goes inactive the account is closed at once (people.signals). One sign-on for
the GSA systems waits for decision D7 (ADR 0016); until then each system keeps its own sign-in.
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import base36_to_int, urlsafe_base64_decode, urlsafe_base64_encode

from audit.services import record
from courses.models import Membership
from iam.models import Role, RoleScope
from iam.sessions import close_sessions
from people.models import PersonRef

# The two kinds of emailed link that choose a password.
LINK_KINDS = (("invitation", "Invitation to a new account"), ("reset", "Reset of a forgotten password"))


class LinkTokens(PasswordResetTokenGenerator):
    """One-use tokens with their own time limit. Django's PASSWORD_RESET_TIMEOUT is set to the longest
    limit in settings, so the stricter limit here is the one that decides."""

    def __init__(self, salt: str, seconds: int):
        super().__init__()
        self.key_salt = salt
        self.seconds = seconds

    def check_token(self, user, token) -> bool:
        if not (user and token) or token.count("-") != 1:
            return False
        try:
            issued = base36_to_int(token.split("-")[0])
        except ValueError:
            return False
        if self._num_seconds(self._now()) - issued > self.seconds:
            return False
        return super().check_token(user, token)


def invitation_tokens() -> LinkTokens:
    return LinkTokens("gsa-lms.invitation", settings.INVITATION_DAYS * 24 * 3600)


def reset_tokens() -> LinkTokens:
    return LinkTokens("gsa-lms.password-reset", settings.PASSWORD_RESET_MINUTES * 60)


def password_link(user, tokens: LinkTokens) -> str:
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    return f"{settings.PUBLIC_URL}/#/set-password/{uid}/{tokens.make_token(user)}"


def user_from_link(uid: str):
    try:
        pk = int(urlsafe_base64_decode(uid).decode())
    except (ValueError, TypeError, UnicodeDecodeError):
        return None
    return get_user_model().objects.filter(pk=pk, is_active=True).first()


def link_kind(user, token: str) -> str | None:
    """ "invitation" or "reset" when the token opens that account, None when it has expired or been used."""
    if user is None:
        return None
    if invitation_tokens().check_token(user, token):
        return "invitation"
    if reset_tokens().check_token(user, token):
        return "reset"
    return None


def accounts_for(login: str) -> list:
    """Active accounts that a username, or an email address, names and that have an address to write to."""
    text = login.strip()
    if not text:
        return []
    users = get_user_model().objects.filter(is_active=True).exclude(email="")
    found = list(users.filter(username__iexact=text))
    if not found and "@" in text:
        found = list(users.filter(email__iexact=text))
    return found[:5]


def never_used(user) -> bool:
    """Opened but never signed in to and no password chosen: the invitation is still outstanding."""
    return not user.has_usable_password() and user.last_login is None


def _username(person: PersonRef) -> str:
    """The person's own number, numbered on if an account outside the records already has it."""
    users = get_user_model().objects
    base = person.external_id
    candidate, number = base, 1
    while users.filter(username__iexact=candidate).exists():
        number += 1
        candidate = f"{base}-{number}"
    return candidate


def _send(user, subject: str, lines: list[str]) -> bool:
    try:
        return (
            send_mail(f"[GSA LMS] {subject}", "\n\n".join(lines), settings.DEFAULT_FROM_EMAIL, [user.email])
            == 1
        )
    except Exception:  # noqa: BLE001 - mail failure is reported to the caller, never raised into the request
        return False


def send_invitation(user) -> bool:
    return _send(
        user,
        "Your account",
        [
            f"Hello {user.first_name or user.get_username()},",
            f"An account has been opened for you on the GSA LMS. Your username is {user.get_username()}.",
            f"Choose your password here. The link works once, for {settings.INVITATION_DAYS} days:\n"
            f"{password_link(user, invitation_tokens())}",
            "If you were not expecting this, tell the course administrator.",
        ],
    )


def send_reset(user) -> bool:
    return _send(
        user,
        "Choose a new password",
        [
            f"Hello {user.first_name or user.get_username()},",
            f"Someone asked for a new password for your GSA LMS account ({user.get_username()}).",
            f"Choose it here. The link works once, for {settings.PASSWORD_RESET_MINUTES} minutes:\n"
            f"{password_link(user, reset_tokens())}",
            "If it was not you, ignore this email: your password has not changed.",
        ],
    )


def role_for(person: PersonRef) -> str | None:
    """The system role an account opened from the record starts with: student for students, lecturer for
    staff who teach a site, and none for other staff, whose access comes from the sites they join."""
    if person.kind == PersonRef.Kind.STUDENT:
        return Role.STUDENT
    teaching = (Membership.SiteRole.LECTURER, Membership.SiteRole.ASSISTANT)
    if person.memberships.filter(is_active=True, role__in=teaching).exists():
        return Role.LECTURER
    return None


@transaction.atomic
def open_account(person: PersonRef):
    """An account for the person, with no usable password until they choose one through the invitation."""
    user = get_user_model().objects.create_user(
        username=_username(person),
        email=person.email,
        first_name=person.first_name,
        last_name=person.last_name,
        password=None,
    )
    person.user = user
    person.save(update_fields=["user", "updated_at"])
    code = role_for(person)
    if code is not None:
        RoleScope.objects.create(user=user, role=Role.objects.get(code=code), campus_code=person.campus_code)
    return user


def uninvited(*, campus_code: str = "", term_code: str = ""):
    """Active people with an email address who have not been sent an invitation, by campus and/or by the
    term of the sites they belong to."""
    qs = PersonRef.objects.filter(is_active=True, invited_at__isnull=True).exclude(email="")
    if campus_code:
        qs = qs.filter(campus_code=campus_code)
    if term_code:
        qs = qs.filter(memberships__site__term_code=term_code, memberships__is_active=True)
    return qs.distinct().select_related("user")


def invite(request, person: PersonRef) -> dict:
    """Open the person's account if they have none, and email the link to choose a password. A person whose
    account is already in use is left alone: they ask for a reset from the sign-in page."""
    user = person.user
    if user is not None and not never_used(user):
        return {"person": person.pk, "outcome": "in_use", "emailed": False}
    if not person.email:
        return {"person": person.pk, "outcome": "no_email", "emailed": False}
    opened = user is None
    if opened:
        user = open_account(person)
    elif not user.is_active:
        user.is_active = True
        user.save(update_fields=["is_active"])
    emailed = send_invitation(user)
    person.invited_at = timezone.now()
    person.save(update_fields=["invited_at", "updated_at"])
    record(
        request,
        "account_invited",
        user,
        after={"person": person.pk, "username": user.get_username(), "opened": opened, "emailed": emailed},
    )
    return {"person": person.pk, "outcome": "invited", "emailed": emailed}


def invite_all(request, *, campus_code: str = "", term_code: str = "") -> dict:
    """Invite every un-invited person of a campus or a term. Returns the counts."""
    counts = {"invited": 0, "emailed": 0, "in_use": 0}
    for person in uninvited(campus_code=campus_code, term_code=term_code):
        result = invite(request, person)
        counts[result["outcome"]] = counts.get(result["outcome"], 0) + 1
        counts["emailed"] += int(result["emailed"])
    return counts


def close_account(person: PersonRef, *, reason: str) -> bool:
    """Switch off the person's account and end every session it has. True when there was one to close."""
    user = person.user
    if user is None or not user.is_active:
        return False
    user.is_active = False
    user.save(update_fields=["is_active"])
    ended = close_sessions(user)
    record(None, "account_closed", user, after={"person": person.pk, "sessions_ended": ended}, reason=reason)
    return True
