"""Items 5.08 to 5.11: certificates from versioned templates, the public check, and withdrawal."""

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from audit.models import AuditLog
from certificates import checking, markup
from certificates.models import Certificate, CertificateCheck, CertificateTemplate
from notifications.models import Notification
from staffdev import completion
from staffdev.models import CatalogueEntry

CHECK = "/api/v1/certificates/check/"


@pytest.fixture
def certificate(staff, course):
    entry = CatalogueEntry.objects.get(site=course)
    done = completion.record_completion(entry, staff, how="recorded")
    return Certificate.objects.get(completion=done)


def ask(reference, code, ip="203.0.113.5"):
    return APIClient().post(CHECK, {"reference": reference, "code": code}, format="json", REMOTE_ADDR=ip)


@pytest.mark.django_db
def test_a_certificate_is_a_pdf_with_its_reference_and_code(certificate, staff, client_for, make_person):
    year = timezone.localdate().year
    assert certificate.reference == f"GSA/LMS/{year}/0001"
    assert certificate.template.code == "completion" and certificate.values["course"] == "Farm safety"
    assert len(checking.plain(certificate.check_code)) == 12
    mine = client_for(staff.user).get("/api/v1/certificates/").json()
    assert mine["count"] == 1 and mine["results"][0]["status"] == "valid"
    pdf = client_for(staff.user).get(f"/api/v1/certificates/{certificate.pk}/download/")
    assert pdf.status_code == 200 and b"".join(pdf.streaming_content)[:4] == b"%PDF"
    assert AuditLog.objects.filter(action="download", entity="certificates.certificate").exists()
    stranger = make_person("staff", "E0299", "Some", "One")
    assert (
        client_for(stranger.user).get(f"/api/v1/certificates/{certificate.pk}/download/").status_code == 404
    )
    assert Notification.objects.filter(
        recipient=staff.user, title__startswith="Your certificate for"
    ).exists()


def test_the_page_escapes_everything_and_fetches_nothing():
    from types import SimpleNamespace

    from certificates import pdf

    template = SimpleNamespace(heading="<b>Hi</b>", signatory_name="", signatory_title="Principal")
    values = {"reference": "GSA/LMS/2026/0001", "full_name": "<script>", "today": "1 October 2026"}
    page = pdf.page(template=template, values=values, body_html="<p>x</p>", check_code="ABCD-EFGH-JKMN")
    assert "<script>" not in page and "&lt;script&gt;" in page and "ABCD-EFGH-JKMN" in page
    with pytest.raises(ValueError):
        pdf.page(template=template, values={**values, "reference": "bad ref"}, body_html="", check_code="x")
    with pytest.raises(ValueError):
        pdf._refuse("http://example.com/x.png")
    blocks = markup.merge(markup.parse("Hello **{{full_name}}**\n\n- one\n- two"), {"full_name": "<A>"})
    assert (
        markup.to_html(blocks) == "<p>Hello <strong>&lt;A&gt;</strong></p>\n<ul><li>one</li><li>two</li></ul>"
    )


@pytest.mark.django_db
def test_anyone_checks_a_certificate_and_the_holder_is_told(certificate, staff):
    typed = certificate.check_code.lower().replace("-", " ")
    good = ask(certificate.reference.lower(), typed)
    assert good.status_code == 200
    body = good.json()
    assert body["status"] == "genuine" and body["holder"] == "Joy Lall" and body["course"] == "Farm safety"
    assert Notification.objects.filter(recipient=staff.user, title__contains="was checked").exists()
    assert AuditLog.objects.filter(action="certificate_checked").exists()
    assert CertificateCheck.objects.filter(matched=True, certificate=certificate).count() == 1


@pytest.mark.django_db
def test_a_wrong_code_and_an_unknown_reference_get_the_same_answer(certificate):
    wrong = ask(certificate.reference, "AAAA-AAAA-AAAA").json()
    unknown = ask("GSA/LMS/1999/9999", certificate.check_code).json()
    assert wrong == unknown and wrong["status"] == "no_match" and wrong["holder"] is None
    assert CertificateCheck.objects.filter(matched=False).count() == 2


@pytest.mark.django_db
def test_checks_are_limited_by_address_and_by_reference(certificate, settings):
    settings.CERTIFICATE_CHECK_FAILURES = 3
    for _ in range(3):
        ask("GSA/LMS/1999/0001", "WRONG", ip="198.51.100.1")
    blocked = ask(certificate.reference, certificate.check_code, ip="198.51.100.1")
    assert blocked.status_code == 429 and blocked.json()["code"] == "too_many_attempts"
    # Many addresses trying one reference are held back too.
    for n in range(3):
        ask(certificate.reference, "WRONG", ip=f"192.0.2.{n + 1}")
    assert ask(certificate.reference, certificate.check_code, ip="192.0.2.99").status_code == 429


@pytest.mark.django_db
def test_a_withdrawn_certificate_checks_as_withdrawn(certificate, staff, course_admin, client_for):
    url = f"/api/v1/certificates/{certificate.pk}/withdraw/"
    assert client_for(staff.user).post(url, {"reason": "x"}, format="json").status_code == 403
    admin = client_for(course_admin)
    assert admin.post(url, {}, format="json").status_code == 400
    assert admin.post(url, {"reason": "  "}, format="json").status_code in (400, 409)
    done = admin.post(url, {"reason": "Issued to the wrong person"}, format="json")
    assert done.status_code == 200 and done.json()["status"] == "withdrawn"
    assert admin.post(url, {"reason": "again"}, format="json").json()["code"] == "already_withdrawn"
    checked = ask(certificate.reference, certificate.check_code).json()
    assert checked["status"] == "withdrawn" and checked["withdrawn_on"] == timezone.localdate().isoformat()
    assert AuditLog.objects.filter(action="certificate_withdrawn", entity_id=certificate.pk).exists()
    assert Notification.objects.filter(recipient=staff.user, title__endswith="was withdrawn").exists()


@pytest.mark.django_db
def test_an_expired_certificate_says_so(certificate):
    Certificate.objects.filter(pk=certificate.pk).update(expires_on=timezone.localdate().replace(year=2020))
    body = ask(certificate.reference, certificate.check_code).json()
    assert body["status"] == "genuine" and "past the date" in body["detail"]


@pytest.mark.django_db
def test_the_check_page_works_without_sign_in_or_script(certificate):
    client = APIClient()
    page = client.get("/api/check-certificate/")
    assert page.status_code == 200 and b"<form" in page.content and b"<script" not in page.content
    assert "default-src 'none'" in page["Content-Security-Policy"]
    answer = client.post(
        "/api/check-certificate/", {"reference": certificate.reference, "code": certificate.check_code}
    )
    assert b"This certificate is genuine" in answer.content and b"Joy Lall" in answer.content
    wrong = client.post("/api/check-certificate/", {"reference": "<b>x</b>", "code": "nope"})
    assert b"No certificate matches" in wrong.content and b"<b>x</b>" not in wrong.content
    assert client.put("/api/check-certificate/").status_code == 405


@pytest.mark.django_db
def test_check_page_says_when_too_many_were_tried(certificate, settings):
    settings.CERTIFICATE_CHECK_FAILURES = 1
    client = APIClient()
    client.post("/api/check-certificate/", {"reference": "X", "code": "Y"})
    held = client.post("/api/check-certificate/", {"reference": "X", "code": "Y"})
    assert b"Too many wrong codes" in held.content


@pytest.mark.django_db
def test_templates_are_versioned(course_admin, staff, course, client_for):
    admin = client_for(course_admin)
    url = "/api/v1/certificate-templates/"
    bad = admin.post(url, {"code": "safety", "name": "Safety", "body": "For {{shoe_size}}"}, format="json")
    assert bad.status_code == 400
    broken = admin.post(url, {"code": "safety", "name": "Safety", "body": "For {{full_name}"}, format="json")
    assert broken.status_code == 400
    made = admin.post(url, {"code": "safety", "name": "Safety", "body": "For **{{course}}**"}, format="json")
    assert made.status_code == 201 and made.json()["fields_used"] == ["course"]
    again = admin.post(url, {"code": "safety", "name": "Safety", "body": "x"}, format="json")
    assert again.status_code == 400
    second = admin.post(
        f"{url}{made.json()['id']}/new-version/", {"heading": "Safety Certificate"}, format="json"
    )
    assert second.status_code == 201 and second.json()["version"] == 2
    assert [t["version"] for t in admin.get(url).json()["results"]] == [2]
    assert len(admin.get(f"{url}?versions=all").json()["results"]) == 2
    assert (
        client_for(staff.user).post(url, {"code": "z", "name": "Z", "body": "z"}, format="json").status_code
        == 403
    )

    entry = CatalogueEntry.objects.get(site=course)
    entry.certificate_template = "safety"
    entry.save()
    done = completion.record_completion(entry, staff, how="recorded")
    issued = Certificate.objects.get(completion=done)
    assert issued.template.version == 2 and issued.template.heading == "Safety Certificate"

    CertificateTemplate.objects.filter(code="safety").update(is_active=False)
    from certificates.services import Refused, issue

    with pytest.raises(Refused):
        issue(None, done, template_code="safety")
