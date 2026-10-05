"""Home, To do and Search: the frame every page sits in (items 2.07 to 2.09)."""

from django.urls import path

from core.home import home
from core.search import search
from core.todo import to_do

urlpatterns = [
    path("home/", home, name="home"),
    path("to-do/", to_do, name="to-do"),
    path("search/", search, name="search"),
]
