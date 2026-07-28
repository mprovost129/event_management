from django.urls import path

from . import views
from .models import SitePage

app_name = "content"

urlpatterns = [
    path("sites/<uuid:site_id>/content/", views.manage_content, name="manage"),
    path(
        "sites/<uuid:site_id>/content/presentation/",
        views.presentation,
        name="presentation",
    ),
    path(
        "sites/<uuid:site_id>/content/pages/<str:page_type>/",
        views.page_edit,
        name="page_edit",
    ),
    path(
        "sites/<uuid:site_id>/content/blog/new/", views.blog_create, name="blog_create"
    ),
    path(
        "sites/<uuid:site_id>/content/blog/<uuid:post_id>/",
        views.blog_edit,
        name="blog_edit",
    ),
    path(
        "about/",
        views.page_detail,
        {"page_type": SitePage.PageType.ABOUT},
        name="about",
    ),
    path(
        "contact/",
        views.page_detail,
        {"page_type": SitePage.PageType.CONTACT},
        name="contact",
    ),
    path("blog/", views.blog_index, name="blog_index"),
    path("blog/<slug:slug>/", views.blog_detail, name="blog_detail"),
    path("newsletter/", views.newsletter_signup, name="newsletter"),
]
