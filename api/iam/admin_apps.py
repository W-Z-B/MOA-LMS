"""Installs LmsAdminSite as the default admin site. Kept apart from admin_site.py because this module is
imported while INSTALLED_APPS is read, before any model can be imported."""

from django.contrib.admin.apps import AdminConfig


class LmsAdminConfig(AdminConfig):
    default_site = "iam.admin_site.LmsAdminSite"
