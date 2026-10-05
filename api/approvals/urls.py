from django.urls import path

from approvals import views

urlpatterns = [path("waiting/", views.waiting, name="approvals-waiting"), *views.router.urls]
