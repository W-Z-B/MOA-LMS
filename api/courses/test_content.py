"""Teaching content: rich pages and the accessibility check, ordering, release conditions, templates,
copying and dates, licences and takedown, and the storage allowance (items 2.12 to 2.20)."""

from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from assessments.models import Assignment
from audit.models import AuditLog
from courses.models import (
    Announcement,
    ContentItem,
    CourseSite,
    ItemCompletion,
    Membership,
    Module,
    SiteGroup,
    SiteTemplate,
    TakedownRequest,
)
from courses.richtext import text_to_html


def pdf(name="handout.pdf", size=0):
    return SimpleUploadedFile(name, b"%PDF-1.7 " + b"x" * size)


@pytest.fixture
def module(site):
    return Module.objects.create(site=site, title="Week 1", position=1)


@pytest.fixture
def teacher(lecturer, client_for):
    return client_for(lecturer.user)


@pytest.fixture
def learner(student, client_for):
    return client_for(student.user)


def page(client, module, body, **extra):
    return client.post(
        "/api/v1/content/",
        {"module": module.id, "kind": "page", "title": "Notes", "body": body, **extra},
        format="json",
    )


def upload(client, module, title="Handout", file=None, **extra):
    data = {"module": module.id, "kind": "file", "title": title, "file": file or pdf(), "licence": "gsa_own"}
    return client.post("/api/v1/content/", {**data, **extra}, format="multipart")


def seen(client, site) -> list[str]:
    modules = client.get(f"/api/v1/sites/{site.id}/contents/").json()["modules"]
    return [i["title"] for m in modules for i in m["items"]]


# 2.12 Rich pages, cleaned on the server


@pytest.mark.django_db
def test_page_html_is_cleaned_against_the_allow_list(teacher, module):
    body = (
        '<h2 onclick="steal()">Soil</h2><script>steal()</script><p style="color:red">A '
        '<a href="javascript:steal()">trap</a> and <a href="https://moa.gov.gy/guide">the planting guide</a>'
        '</p><span data-math="NH_4^+">NH4</span><iframe src="https://x.example"></iframe><h1>Big</h1>'
    )
    created = page(teacher, module, body)
    assert created.status_code == 201, created.content
    saved = ContentItem.objects.get(pk=created.json()["id"]).body
    assert "script" not in saved and "onclick" not in saved and "style" not in saved
    assert "javascript" not in saved and "iframe" not in saved and "<h1>" not in saved
    assert '<a href="https://moa.gov.gy/guide" rel="noopener noreferrer">the planting guide</a>' in saved
    assert '<span data-math="NH_4^+">' in saved
    assert created.json()["body"] == saved


@pytest.mark.django_db
def test_plain_text_becomes_paragraphs(teacher, module):
    created = page(teacher, module, "Line one\nline two\n\n<b>not bold</b>", body_format="text")
    assert created.json()["body"] == "<p>Line one<br>line two</p><p>&lt;b&gt;not bold&lt;/b&gt;</p>"
    assert text_to_html("") == ""


@pytest.mark.django_db
def test_an_image_without_alternative_text_is_refused(teacher, module):
    picture = upload(teacher, module, "Seedling", pdf("seedling.pdf")).json()
    src = picture["download_url"]
    refused = page(teacher, module, f'<p>Look:</p><img src="{src}">')
    assert refused.status_code == 400
    assert "no alternative text" in refused.json()["body"][0]
    assert page(teacher, module, f'<img src="{src}" alt="  ">').status_code == 400
    accepted = page(teacher, module, f'<img src="{src}" alt="A maize seedling at ten days">')
    assert accepted.status_code == 201
    assert ContentItem.objects.filter(kind="page").count() == 1


@pytest.mark.django_db
def test_images_must_be_files_on_the_same_course(teacher, module, lecturer):
    elsewhere = page(teacher, module, '<img src="https://example.com/a.png" alt="A field">')
    assert elsewhere.status_code == 400 and "not a file on this course" in elsewhere.json()["body"][0]
    other = CourseSite.objects.create(code="LIV110-X", title="Poultry", is_published=True)
    Membership.objects.create(site=other, person=lecturer, role="lecturer")
    theirs = upload(teacher, Module.objects.create(site=other, title="W1")).json()
    refused = page(teacher, module, f'<img src="{theirs["download_url"]}" alt="A hen">')
    assert refused.status_code == 400 and "not a file on this course" in refused.json()["body"][0]


# 2.13 Accessibility check


@pytest.mark.django_db
def test_the_accessibility_check_reports_problems_without_saving(teacher, learner, module):
    body = (
        "<h2>Week 1</h2><h4>Too deep</h4><p><a href='https://moa.gov.gy'>click here</a> "
        "<a href='https://moa.gov.gy'> </a></p><table><tr><td>Maize</td><td>90 days</td></tr></table>"
    )
    checked = teacher.post("/api/v1/content/check-page/", {"body": body}, format="json")
    assert checked.status_code == 200
    codes = [i["code"] for i in checked.json()["issues"]]
    assert codes == ["heading_skipped", "vague_link", "empty_link", "table_without_headers"]
    assert {i["severity"] for i in checked.json()["issues"]} == {"warning"}
    assert not ContentItem.objects.exists()
    missing = teacher.post("/api/v1/content/check-page/", {"body": "<img src='x'>"}, format="json")
    assert {"missing_alt", "image_not_on_lms"} <= {i["code"] for i in missing.json()["issues"]}
    assert learner.post("/api/v1/content/check-page/", {"body": body}, format="json").status_code == 403


@pytest.mark.django_db
def test_warnings_are_returned_on_save_and_do_not_refuse(teacher, module):
    good = page(teacher, module, "<h2>Aims</h2><table><thead><tr><th>Crop</th></tr></thead></table>")
    assert good.json()["accessibility_issues"] == []
    vague = page(teacher, module, '<p><a href="https://moa.gov.gy">Read more</a></p>')
    assert vague.status_code == 201 and vague.json()["accessibility_issues"][0]["code"] == "vague_link"
    assert teacher.get(f"/api/v1/content/{vague.json()['id']}/").json()["accessibility_issues"] is None


# 2.15 Reorder, duplicate and move


@pytest.mark.django_db
def test_modules_are_reordered_with_every_id_once(teacher, learner, site, module):
    week2 = Module.objects.create(site=site, title="Week 2", position=2)
    url = f"/api/v1/sites/{site.id}/reorder-modules/"
    assert teacher.post(url, {"order": [week2.id, module.id]}, format="json").status_code == 200
    assert list(site.modules.values_list("title", flat=True)) == ["Week 2", "Week 1"]
    assert AuditLog.objects.filter(entity="courses.coursesite", action="reorder").exists()
    for wrong in ([week2.id], [week2.id, week2.id], [week2.id, module.id, 999999]):
        refused = teacher.post(url, {"order": wrong}, format="json")
        assert refused.status_code == 400 and "every module id once" in refused.json()["order"][0]
    assert learner.post(url, {"order": [module.id, week2.id]}, format="json").status_code == 403


@pytest.mark.django_db
def test_items_are_reordered_within_their_module_only(teacher, site, module):
    a = ContentItem.objects.create(module=module, title="A", position=1)
    b = ContentItem.objects.create(module=module, title="B", position=2)
    other = ContentItem.objects.create(module=Module.objects.create(site=site, title="W2"), title="C")
    url = f"/api/v1/modules/{module.id}/reorder-items/"
    assert teacher.post(url, {"order": [a.id, other.id]}, format="json").status_code == 400
    assert teacher.post(url, {"order": [b.id, a.id]}, format="json").status_code == 200
    assert list(module.items.values_list("title", flat=True)) == ["B", "A"]


@pytest.mark.django_db
def test_an_item_is_duplicated_as_a_draft_with_its_own_file(teacher, learner, module):
    original = upload(teacher, module).json()
    after = ContentItem.objects.create(module=module, title="Later", position=2)
    copied = teacher.post(f"/api/v1/content/{original['id']}/duplicate/")
    assert copied.status_code == 201, copied.content
    body = copied.json()
    assert body["title"] == "Copy of Handout" and body["is_published"] is False and body["position"] == 2
    one, two = ContentItem.objects.get(pk=original["id"]), ContentItem.objects.get(pk=body["id"])
    assert one.file.name != two.file.name and two.file.read() == one.file.read()
    assert ContentItem.objects.get(pk=after.pk).position == 3
    assert learner.post(f"/api/v1/content/{original['id']}/duplicate/").status_code == 403


@pytest.mark.django_db
def test_an_item_moves_between_modules_of_the_same_course_only(teacher, site, module, lecturer):
    week2 = Module.objects.create(site=site, title="Week 2", position=2)
    ContentItem.objects.create(module=week2, title="First", position=1)
    item = ContentItem.objects.create(module=module, title="Mover")
    moved = teacher.post(
        f"/api/v1/content/{item.id}/move/", {"module": week2.id, "position": 1}, format="json"
    )
    assert moved.status_code == 200 and moved.json()["module"] == week2.id
    assert list(week2.items.values_list("title", "position")) == [("Mover", 1), ("First", 2)]

    other = CourseSite.objects.create(code="LIV110-X", title="Poultry", is_published=True)
    Membership.objects.create(site=other, person=lecturer, role="lecturer")
    there = Module.objects.create(site=other, title="W1")
    refused = teacher.post(f"/api/v1/content/{item.id}/move/", {"module": there.id}, format="json")
    assert refused.status_code == 400 and "same course" in refused.json()["module"][0]
    patched = teacher.patch(f"/api/v1/content/{item.id}/", {"module": there.id}, format="json")
    assert patched.status_code == 400
    assert ContentItem.objects.get(pk=item.pk).module_id == week2.id


# 2.16 Release conditions and completion


@pytest.mark.django_db
def test_an_item_with_a_future_date_is_unknown_to_students_until_then(teacher, learner, module, site):
    later = timezone.now() + timedelta(days=3)
    item = upload(teacher, module, available_from=later.isoformat()).json()
    assert seen(learner, site) == []
    assert learner.get(f"/api/v1/content/{item['id']}/").status_code == 404
    assert learner.get(item["download_url"]).status_code == 404
    shown = teacher.get(f"/api/v1/sites/{site.id}/contents/").json()["modules"][0]["items"][0]
    assert shown["conditions"].startswith("Shown from ")
    ContentItem.objects.filter(pk=item["id"]).update(available_from=timezone.now() - timedelta(minutes=1))
    assert seen(learner, site) == ["Handout"]
    assert (
        learner.get(f"/api/v1/sites/{site.id}/contents/").json()["modules"][0]["items"][0]["conditions"]
        is None
    )


@pytest.mark.django_db
def test_an_item_waits_for_another_to_be_completed(teacher, learner, module, site, student):
    safety = page(teacher, module, "<p>Wear boots.</p>", title="Safety induction").json()
    field = page(teacher, module, "<p>Meet at the gate.</p>", title="Field work", requires_item=safety["id"])
    assert field.status_code == 201, field.content
    assert seen(learner, site) == ["Safety induction"]
    conditions = teacher.get(f"/api/v1/content/{field.json()['id']}/").json()["conditions"]
    assert conditions == "Once “Safety induction” is complete."

    opened = learner.get(f"/api/v1/content/{safety['id']}/")  # opening a page completes it
    assert opened.status_code == 200
    assert ItemCompletion.objects.get(person=student).how == "viewed"
    assert seen(learner, site) == ["Safety induction", "Field work"]
    assert learner.get(f"/api/v1/content/{safety['id']}/").json()["completed"] is True


@pytest.mark.django_db
def test_downloading_a_file_or_marking_it_completes_it(teacher, learner, module, student, lecturer):
    handout = upload(teacher, module).json()
    learner.get(handout["download_url"])
    assert ItemCompletion.objects.get(person=student, item_id=handout["id"]).how == "downloaded"
    link = teacher.post(
        "/api/v1/content/",
        {
            "module": module.id,
            "kind": "link",
            "title": "Guide",
            "url": "https://moa.gov.gy",
            "licence": "gsa_own",
        },
        format="json",
    ).json()
    marked = learner.post(f"/api/v1/content/{link['id']}/complete/")
    assert marked.status_code == 200 and marked.json()["completed"] is True
    assert ItemCompletion.objects.get(person=student, item_id=link["id"]).how == "marked"
    assert teacher.post(f"/api/v1/content/{link['id']}/complete/").status_code == 403
    teacher.get(f"/api/v1/content/{link['id']}/")
    assert not ItemCompletion.objects.filter(person=lecturer).exists()
    assert AuditLog.objects.filter(entity="courses.itemcompletion", action="create").count() == 2


@pytest.mark.django_db
def test_an_item_for_one_group_is_shown_to_its_members_only(
    teacher, learner, module, site, student, other_student, client_for
):
    ravi = Membership.objects.get(site=site, person=student)
    group = teacher.post(
        "/api/v1/groups/", {"site": site.id, "name": "Group A", "members": [ravi.id]}, format="json"
    )
    assert group.status_code == 201, group.content
    created = page(teacher, module, "<p>Plot A</p>", title="Plot A rota", groups=[group.json()["id"]])
    assert created.status_code == 201, created.content
    assert seen(learner, site) == ["Plot A rota"]
    assert seen(client_for(other_student.user), site) == []
    assert created.json()["conditions"] == "To Group A only."
    assert learner.get("/api/v1/groups/").json()["count"] == 0


@pytest.mark.django_db
def test_a_held_back_module_hides_its_items(teacher, learner, module, site):
    ContentItem.objects.create(module=module, title="Notes")
    patched = teacher.patch(
        f"/api/v1/modules/{module.id}/",
        {"available_from": (timezone.now() + timedelta(days=1)).isoformat()},
        format="json",
    )
    assert patched.status_code == 200 and patched.json()["conditions"].startswith("Shown from")
    assert learner.get(f"/api/v1/sites/{site.id}/contents/").json()["modules"] == []
    assert learner.get("/api/v1/modules/").json()["count"] == 0
    assert learner.get("/api/v1/content/").json()["count"] == 0
    assert seen(teacher, site) == ["Notes"]


@pytest.mark.django_db
def test_conditions_must_name_items_and_groups_of_the_same_course(teacher, module, site, lecturer, student):
    item = ContentItem.objects.create(module=module, title="Self")
    looped = teacher.patch(f"/api/v1/content/{item.id}/", {"requires_item": item.id}, format="json")
    assert looped.status_code == 400 and "ever open" in looped.json()["requires_item"][0]
    other = ContentItem.objects.create(module=module, title="Other", requires_item=item)
    loop = teacher.patch(f"/api/v1/content/{item.id}/", {"requires_item": other.id}, format="json")
    assert loop.status_code == 400
    own = teacher.patch(f"/api/v1/modules/{module.id}/", {"requires_item": item.id}, format="json")
    assert own.status_code == 400

    elsewhere = CourseSite.objects.create(code="LIV110-X", title="Poultry", is_published=True)
    Membership.objects.create(site=elsewhere, person=lecturer, role="lecturer")
    far = ContentItem.objects.create(module=Module.objects.create(site=elsewhere, title="W1"), title="Far")
    group = SiteGroup.objects.create(site=elsewhere, name="Far group")
    assert (
        teacher.patch(f"/api/v1/content/{item.id}/", {"requires_item": far.id}, format="json").status_code
        == 400
    )
    assert (
        teacher.patch(f"/api/v1/content/{item.id}/", {"groups": [group.id]}, format="json").status_code == 400
    )
    stranger = Membership.objects.create(site=elsewhere, person=student, role="student")
    refused = teacher.post(
        "/api/v1/groups/", {"site": site.id, "name": "X", "members": [stranger.id]}, format="json"
    )
    assert refused.status_code == 400 and "members of this course" in refused.json()["members"][0]


# 2.17 Course templates


@pytest.mark.django_db
def test_a_new_site_starts_from_the_gsa_standard_layout(course_admin, client_for, make_person):
    admin = client_for(course_admin)
    created = admin.post("/api/v1/sites/", {"code": "AGR201-X", "title": "Crop protection"}, format="json")
    assert created.status_code == 201, created.content
    site = CourseSite.objects.get(code="AGR201-X")
    titles = list(site.modules.values_list("title", flat=True))
    assert titles == ["Course overview", "Course outline", *[f"Week {n}" for n in range(1, 13)], "Assessment"]
    assert not ContentItem.objects.filter(module__site=site, is_published=True).exists()
    assert ContentItem.objects.filter(module__site=site, title="Course outline").exists()

    again = admin.post(f"/api/v1/sites/{site.id}/apply-template/", {}, format="json")
    assert again.status_code == 409 and again.json()["code"] == "not_empty"
    site.modules.all().delete()
    applied = admin.post(f"/api/v1/sites/{site.id}/apply-template/", {}, format="json")
    assert applied.status_code == 200 and applied.json() == {"modules": 15}


@pytest.mark.django_db
def test_templates_are_managed_by_course_administrators(course_admin, client_for, teacher):
    structure = {
        "modules": [{"title": "Unit 1", "items": [{"kind": "page", "title": "Read me", "body": "<p>x</p>"}]}]
    }
    assert (
        teacher.post(
            "/api/v1/site-templates/", {"name": "Short", "structure": structure}, format="json"
        ).status_code
        == 403
    )
    assert teacher.get("/api/v1/site-templates/").json()["count"] == 1
    admin = client_for(course_admin)
    bad = admin.post("/api/v1/site-templates/", {"name": "Bad", "structure": {"modules": []}}, format="json")
    assert bad.status_code == 400
    made = admin.post(
        "/api/v1/site-templates/",
        {"name": "Short", "structure": structure, "is_default": True},
        format="json",
    )
    assert made.status_code == 201
    assert list(SiteTemplate.objects.filter(is_default=True).values_list("name", flat=True)) == ["Short"]
    assert AuditLog.objects.filter(entity="courses.sitetemplate", action="create").exists()


# 2.18 Copy from an earlier term, and the date manager


@pytest.fixture
def last_term(site, module, teacher, assignment):
    """Last term's course, taught by the same lecturer, with content to copy and things not to copy."""
    handout = upload(teacher, module).json()
    picture = ContentItem.objects.get(pk=handout["id"])
    body = f'<p>See</p><img src="/api/v1/content/{picture.id}/download/" alt="The handout">'
    notes = ContentItem.objects.create(
        module=module, title="Notes", body=body, available_from=timezone.now() - timedelta(days=100)
    )
    ContentItem.objects.create(module=module, title="After notes", requires_item=notes, position=3)
    Announcement.objects.create(site=site, title="Old news", body="x")
    group = SiteGroup.objects.create(site=site, name="Group A")
    notes.groups.add(group)
    ContentItem.objects.create(module=module, title="Disputed", under_review=True, position=4)
    return site


@pytest.fixture
def new_term(lecturer, site):
    target = CourseSite.objects.create(code="AGR101-2027-28-S1-MRP", title="AGR101 again", is_published=True)
    Membership.objects.create(site=target, person=lecturer, role="lecturer")
    return target


@pytest.mark.django_db
def test_content_is_copied_without_people_and_with_dates_moved(teacher, last_term, new_term, assignment):
    url = f"/api/v1/sites/{new_term.id}/copy-from/"
    copied = teacher.post(url, {"source": last_term.id, "offset_days": 364}, format="json")
    assert copied.status_code == 200, copied.content
    assert copied.json() == {
        "modules": 1,
        "items": 3,
        "assignments": 1,
        "offset_days": 364,
        "missing_files": [],
        "left_out": ["Disputed"],
    }
    items = {i.title: i for i in ContentItem.objects.filter(module__site=new_term)}
    old = {i.title: i for i in ContentItem.objects.filter(module__site=last_term)}
    assert items["Handout"].file.name != old["Handout"].file.name
    assert items["Handout"].file.read() == old["Handout"].file.read()
    assert items["After notes"].requires_item_id == items["Notes"].id
    assert f"/api/v1/content/{items['Handout'].id}/download/" in items["Notes"].body
    assert items["Notes"].available_from == old["Notes"].available_from + timedelta(days=364)
    assert not items["Notes"].groups.exists()
    work = Assignment.objects.get(site=new_term)
    assert work.due_at == assignment.due_at + timedelta(days=364)
    assert not new_term.announcements.exists() and not new_term.groups.exists()
    assert not work.submissions.exists()
    assert AuditLog.objects.filter(entity="courses.coursesite", entity_id=new_term.id, action="copy").exists()


@pytest.mark.django_db
def test_a_copy_can_start_on_a_new_date(teacher, last_term, new_term):
    start = (timezone.localtime(timezone.now()) + timedelta(days=200)).date()
    copied = teacher.post(
        f"/api/v1/sites/{new_term.id}/copy-from/",
        {"source": last_term.id, "start_date": start},
        format="json",
    )
    assert copied.status_code == 200
    first = min(
        row["value"] for row in teacher.get(f"/api/v1/sites/{new_term.id}/dates/").json() if row["value"]
    )
    assert first.startswith(start.isoformat())


@pytest.mark.django_db
def test_copying_is_refused_over_existing_content_and_from_a_course_not_taught(
    teacher, last_term, new_term, make_person, client_for, student
):
    Module.objects.create(site=new_term, title="Already here")
    url = f"/api/v1/sites/{new_term.id}/copy-from/"
    refused = teacher.post(url, {"source": last_term.id}, format="json")
    assert refused.status_code == 409 and refused.json()["code"] == "copy_refused"
    item = ContentItem.objects.create(module=new_term.modules.get(), title="Used")
    Membership.objects.create(site=new_term, person=student, role="student")
    ItemCompletion.objects.create(person=student, item=item, completed_at=timezone.now(), how="viewed")
    used = teacher.post(url, {"source": last_term.id, "replace_existing": True}, format="json")
    assert used.status_code == 409 and "already worked through" in used.json()["detail"]
    ItemCompletion.objects.all().delete()
    replaced = teacher.post(url, {"source": last_term.id, "replace_existing": True}, format="json")
    assert replaced.status_code == 200
    assert not new_term.modules.filter(title="Already here").exists()

    stranger = make_person("staff", "E0009", "Bibi", "Khan", "lecturer")
    theirs = CourseSite.objects.create(code="SOIL-9", title="Soils", is_published=True)
    Membership.objects.create(site=theirs, person=stranger, role="lecturer")
    unknown = client_for(stranger.user).post(
        f"/api/v1/sites/{theirs.id}/copy-from/", {"source": last_term.id}, format="json"
    )
    assert unknown.status_code == 400 and "does not exist" in unknown.json()["source"][0]


@pytest.mark.django_db
def test_the_date_manager_lists_and_changes_dates_all_or_nothing(teacher, learner, site, module, assignment):
    item = ContentItem.objects.create(module=module, title="Notes")
    dates = teacher.get(f"/api/v1/sites/{site.id}/dates/").json()
    assert {(r["kind"], r["field"]) for r in dates} == {
        ("module", "available_from"),
        ("item", "available_from"),
        ("assignment", "opens_at"),
        ("assignment", "due_at"),
    }
    when = timezone.now() + timedelta(days=30)
    changes = [
        {"kind": "item", "id": item.id, "field": "available_from", "value": when.isoformat()},
        {
            "kind": "assignment",
            "id": assignment.id,
            "field": "due_at",
            "value": (when + timedelta(days=7)).isoformat(),
        },
    ]
    done = teacher.patch(f"/api/v1/sites/{site.id}/dates/", {"changes": changes}, format="json")
    assert done.status_code == 200, done.content
    assert ContentItem.objects.get(pk=item.pk).available_from == when
    assert AuditLog.objects.filter(entity="assessments.assignment", action="update").exists()

    wrong = [
        {"kind": "item", "id": item.id, "field": "available_from", "value": None},
        {
            "kind": "assignment",
            "id": assignment.id,
            "field": "opens_at",
            "value": (when + timedelta(days=8)).isoformat(),
        },
    ]
    refused = teacher.patch(f"/api/v1/sites/{site.id}/dates/", {"changes": wrong}, format="json")
    assert refused.status_code == 400 and "open after it is due" in refused.json()["detail"]
    assert ContentItem.objects.get(pk=item.pk).available_from == when  # nothing was changed
    foreign = [{"kind": "item", "id": 999999, "field": "available_from", "value": None}]
    assert (
        teacher.patch(f"/api/v1/sites/{site.id}/dates/", {"changes": foreign}, format="json").status_code
        == 400
    )
    assert learner.get(f"/api/v1/sites/{site.id}/dates/").status_code == 403


@pytest.mark.django_db
def test_every_date_moves_at_once(teacher, site, assignment):
    due = assignment.due_at
    moved = teacher.post(f"/api/v1/sites/{site.id}/shift-dates/", {"offset_days": -7}, format="json")
    assert moved.status_code == 200
    assert Assignment.objects.get(pk=assignment.pk).due_at == due - timedelta(days=7)
    both = teacher.post(f"/api/v1/sites/{site.id}/shift-dates/", {}, format="json")
    assert both.status_code == 400


# 2.19 Licence, source and takedown


@pytest.mark.django_db
def test_files_and_links_must_say_whose_material_they_are(teacher, module):
    data = {"module": module.id, "kind": "file", "title": "Handout", "file": pdf()}
    refused = teacher.post("/api/v1/content/", data, format="multipart")
    assert refused.status_code == 400 and "whose material" in refused.json()["licence"][0]
    link = {"module": module.id, "kind": "link", "title": "FAO", "url": "https://fao.org"}
    assert teacher.post("/api/v1/content/", link, format="json").status_code == 400
    which = teacher.post("/api/v1/content/", {**link, "licence": "open_licence"}, format="json")
    assert which.status_code == 400 and "which open licence" in which.json()["open_licence"][0]
    credit = teacher.post(
        "/api/v1/content/", {**link, "licence": "open_licence", "open_licence": "cc_by"}, format="json"
    )
    assert credit.status_code == 400 and "credit" in credit.json()["source"][0]
    fair = teacher.post("/api/v1/content/", {**link, "licence": "fair_dealing"}, format="json")
    assert fair.status_code == 400
    done = teacher.post(
        "/api/v1/content/",
        {**link, "licence": "open_licence", "open_licence": "cc_by", "source": "FAO, CC BY 4.0"},
        format="json",
    )
    assert done.status_code == 201 and done.json()["open_licence"] == "cc_by"
    assert page(teacher, module, "<p>Mine</p>").json()["licence"] == "gsa_own"


@pytest.mark.django_db
def test_a_reported_item_is_hidden_until_a_course_administrator_decides(
    teacher, learner, module, site, course_admin, client_for, student
):
    item = page(teacher, module, "<p>Scanned chapter</p>", title="Chapter 3").json()
    reported = learner.post(
        f"/api/v1/content/{item['id']}/report/", {"reason": "Copied from a textbook"}, format="json"
    )
    assert reported.status_code == 201
    # A student's report does not hide the lecturer's material from the class; it waits for review.
    assert seen(learner, site) == ["Chapter 3"]
    assert teacher.get(f"/api/v1/content/{item['id']}/").json()["under_review"] is False
    # The course's own lecturer reporting it does hide it at once.
    own = teacher.post(
        f"/api/v1/content/{item['id']}/report/", {"reason": "Checking the source"}, format="json"
    ).json()
    assert seen(learner, site) == []
    shown = teacher.get(f"/api/v1/content/{item['id']}/").json()
    assert shown["under_review"] is True and "takedown" in shown["conditions"]
    assert learner.get("/api/v1/takedowns/").json()["count"] == 1
    assert teacher.get("/api/v1/takedowns/").json()["count"] == 1  # their own report only

    request_id = reported.json()["id"]
    assert (
        teacher.post(
            f"/api/v1/takedowns/{request_id}/review/", {"decision": "restore"}, format="json"
        ).status_code
        == 403
    )
    admin = client_for(course_admin)
    restored = admin.post(f"/api/v1/takedowns/{request_id}/review/", {"decision": "restore"}, format="json")
    assert restored.status_code == 200 and restored.json()["status"] == "restored"
    assert seen(learner, site) == []  # the lecturer's own request is still open
    admin.post(f"/api/v1/takedowns/{own['id']}/review/", {"decision": "restore"}, format="json")
    assert seen(learner, site) == ["Chapter 3"]
    again = admin.post(f"/api/v1/takedowns/{request_id}/review/", {"decision": "withdraw"}, format="json")
    assert again.status_code == 409

    second = learner.post(
        f"/api/v1/content/{item['id']}/report/", {"reason": "Still copied"}, format="json"
    ).json()
    withdrawn = admin.post(
        f"/api/v1/takedowns/{second['id']}/review/",
        {"decision": "withdraw", "note": "No permission"},
        format="json",
    )
    assert withdrawn.json()["status"] == "withdrawn"
    stored = ContentItem.objects.get(pk=item["id"])
    assert stored.is_published is False and stored.under_review is False
    assert TakedownRequest.objects.filter(status="open").count() == 0
    assert AuditLog.objects.filter(entity="courses.takedownrequest", action="review").count() == 3
    # Teaching staff cannot bring withdrawn material back, nor copy it.
    republish = teacher.patch(f"/api/v1/content/{item['id']}/", {"is_published": True}, format="json")
    assert republish.status_code == 400 and "course administrator" in republish.json()["is_published"][0]
    copied = teacher.post(f"/api/v1/content/{item['id']}/duplicate/")
    assert copied.status_code == 409 and copied.json()["code"] == "taken_down"
    assert (
        admin.patch(f"/api/v1/content/{item['id']}/", {"is_published": True}, format="json").status_code
        == 200
    )


# 2.20 Storage allowance


@pytest.mark.django_db
def test_storage_warns_at_80_per_cent_and_refuses_at_the_allowance(teacher, module, site, settings):
    settings.SITE_STORAGE_ALLOWANCE_MB = 1
    first = upload(teacher, module, "Big", pdf("big.pdf", 850 * 1024))
    assert first.status_code == 201
    storage = first.json()["storage"]
    assert storage["percent"] >= 80 and "storage allowance" in storage["warning"]
    refused = upload(teacher, module, "More", pdf("more.pdf", 300 * 1024))
    assert refused.status_code == 400
    assert "1 GB" not in refused.json()["file"][0] and "larger allowance" in refused.json()["file"][0]
    duplicate = teacher.post(f"/api/v1/content/{first.json()['id']}/duplicate/")
    assert duplicate.status_code == 400 and duplicate.json()["code"] == "storage_full"
    usage = teacher.get(f"/api/v1/sites/{site.id}/storage/").json()
    assert usage["largest_files"][0]["title"] == "Big" and usage["allowance_bytes"] == 1024 * 1024


@pytest.mark.django_db
def test_only_a_course_administrator_changes_a_sites_allowance(
    teacher, site, module, course_admin, client_for, settings
):
    settings.SITE_STORAGE_ALLOWANCE_MB = 1
    refused = teacher.patch(f"/api/v1/sites/{site.id}/", {"storage_allowance_mb": 5000}, format="json")
    assert refused.status_code == 403
    allowed = client_for(course_admin).patch(
        f"/api/v1/sites/{site.id}/", {"storage_allowance_mb": 3}, format="json"
    )
    assert allowed.status_code == 200 and allowed.json()["storage_allowance_mb"] == 3
    assert upload(teacher, module, "Big", pdf("big.pdf", 2 * 1024 * 1024)).status_code == 201


@pytest.mark.django_db
def test_the_auditor_reads_material_but_does_not_report_it(teacher, module, make_user, client_for):
    """Found by the permission table (item 1.16): the auditor, who only reads, could ask for a takedown."""
    item = page(teacher, module, "<p>Notes</p>").json()
    auditor = client_for(make_user("auditor.content", "auditor"))
    assert auditor.get(f"/api/v1/content/{item['id']}/").status_code == 200
    refused = auditor.post(f"/api/v1/content/{item['id']}/report/", {"reason": "Copied"}, format="json")
    assert refused.status_code == 403 and refused.json()["code"] == "permission_denied"
    assert not TakedownRequest.objects.exists()
