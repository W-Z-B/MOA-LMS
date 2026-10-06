"""Finding the colleague to name as a stand-in (the delegations screen, item 5.02's approvals)."""

import pytest

URL = "/api/v1/approvals/colleagues/"


@pytest.mark.django_db
def test_staff_find_colleagues_who_can_sign_in_by_name_or_number(
    staff, supervisor, make_person, course_admin, client_for
):
    gone = make_person("staff", "E0206", "Joyce", "Gone")
    gone.is_active = False
    gone.save()
    make_person("student", "S0207", "Joy", "Student")
    client = client_for(supervisor.user)
    assert client.get(URL, {"q": "J"}).json() == []  # two letters at least
    found = client.get(URL, {"q": "joy"}).json()
    assert found == [{"id": staff.pk, "name": "Joy Lall", "employee_no": "E0201"}]
    assert [p["name"] for p in client.get(URL, {"q": "E020"}).json()] == ["Mark Boss", "Joy Lall"]
    assert client.get(URL, {"q": "Joy Lall"}).json()[0]["id"] == staff.pk
    assert client_for(course_admin).get(URL, {"q": "boss"}).json()[0]["employee_no"] == "E0202"


@pytest.mark.django_db
def test_students_and_people_without_a_staff_record_find_nobody(make_person, make_user, client_for, staff):
    student = make_person("student", "S0301", "Ravi", "Learner")
    refused = client_for(student.user).get(URL, {"q": "joy"})
    assert refused.status_code == 403 and refused.json()["code"] == "permission_denied"
    assert client_for(make_user("no.record")).get(URL, {"q": "joy"}).status_code == 403
