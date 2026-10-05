from django.urls import path

from approvals import views

urlpatterns = [
    path("waiting/", views.waiting, name="approvals-waiting"),
    path("colleagues/", views.colleagues, name="approvals-colleagues"),
    *views.router.urls,
]
