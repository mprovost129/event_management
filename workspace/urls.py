from django.urls import path

from . import views

app_name = "workspace"
urlpatterns = [
    path("sites/<uuid:site_id>/insights/", views.insights, name="insights"),
    path(
        "sites/<uuid:site_id>/insights/export/",
        views.insights_export,
        name="insights_export",
    ),
    path("sites/<uuid:site_id>/tasks/", views.task_list, name="task_list"),
    path("sites/<uuid:site_id>/tasks/new/", views.task_create, name="task_create"),
    path(
        "sites/<uuid:site_id>/tasks/<uuid:task_id>/",
        views.task_detail,
        name="task_detail",
    ),
    path(
        "sites/<uuid:site_id>/tasks/<uuid:task_id>/checklist/add/",
        views.checklist_add,
        name="checklist_add",
    ),
    path(
        "sites/<uuid:site_id>/tasks/<uuid:task_id>/checklist/<int:item_id>/toggle/",
        views.checklist_toggle,
        name="checklist_toggle",
    ),
    path(
        "sites/<uuid:site_id>/tasks/<uuid:task_id>/comments/add/",
        views.comment_add,
        name="comment_add",
    ),
    path("sites/<uuid:site_id>/documents/", views.document_list, name="document_list"),
    path(
        "sites/<uuid:site_id>/documents/upload/",
        views.document_upload,
        name="document_upload",
    ),
    path(
        "sites/<uuid:site_id>/documents/<uuid:document_id>/download/",
        views.document_download,
        name="document_download",
    ),
    path(
        "sites/<uuid:site_id>/documents/<uuid:document_id>/delete/",
        views.document_delete,
        name="document_delete",
    ),
    path("sites/<uuid:site_id>/activity/", views.activity_list, name="activity_list"),
    path(
        "sites/<uuid:site_id>/volunteers/", views.volunteer_list, name="volunteer_list"
    ),
    path(
        "sites/<uuid:site_id>/volunteers/new/",
        views.volunteer_create,
        name="volunteer_create",
    ),
    path(
        "sites/<uuid:site_id>/volunteers/<uuid:volunteer_id>/",
        views.volunteer_detail,
        name="volunteer_detail",
    ),
    path(
        "sites/<uuid:site_id>/volunteers/<uuid:volunteer_id>/hours/add/",
        views.volunteer_hour_add,
        name="volunteer_hour_add",
    ),
    path(
        "sites/<uuid:site_id>/volunteer-shifts/new/",
        views.shift_create,
        name="shift_create",
    ),
    path(
        "sites/<uuid:site_id>/volunteer-shifts/<uuid:shift_id>/",
        views.shift_detail,
        name="shift_detail",
    ),
    path(
        "sites/<uuid:site_id>/volunteer-shifts/<uuid:shift_id>/assign/",
        views.shift_assign,
        name="shift_assign",
    ),
    path("sites/<uuid:site_id>/sponsors/", views.sponsor_list, name="sponsor_list"),
    path(
        "sites/<uuid:site_id>/sponsors/new/",
        views.sponsor_create,
        name="sponsor_create",
    ),
    path(
        "sites/<uuid:site_id>/sponsors/<uuid:sponsor_id>/",
        views.sponsor_detail,
        name="sponsor_detail",
    ),
    path(
        "sites/<uuid:site_id>/sponsors/<uuid:sponsor_id>/sponsorships/add/",
        views.sponsorship_add,
        name="sponsorship_add",
    ),
    path(
        "sites/<uuid:site_id>/forms/", views.intake_form_list, name="intake_form_list"
    ),
    path(
        "sites/<uuid:site_id>/forms/new/",
        views.intake_form_create,
        name="intake_form_create",
    ),
    path(
        "sites/<uuid:site_id>/forms/<uuid:form_id>/",
        views.intake_form_detail,
        name="intake_form_detail",
    ),
    path(
        "sites/<uuid:site_id>/forms/<uuid:form_id>/responses/<uuid:submission_id>/",
        views.intake_submission_detail,
        name="intake_submission_detail",
    ),
    path(
        "forms/<uuid:form_id>/<slug:slug>/", views.intake_public, name="intake_public"
    ),
    path(
        "sites/<uuid:site_id>/automations/",
        views.automation_list,
        name="automation_list",
    ),
    path(
        "sites/<uuid:site_id>/automations/new/",
        views.automation_create,
        name="automation_create",
    ),
    path(
        "sites/<uuid:site_id>/automations/<uuid:rule_id>/",
        views.automation_detail,
        name="automation_detail",
    ),
    path(
        "sites/<uuid:site_id>/automations/<uuid:rule_id>/run/",
        views.automation_run,
        name="automation_run",
    ),
    path("sites/<uuid:site_id>/ai/", views.ai_draft_list, name="ai_draft_list"),
    path("sites/<uuid:site_id>/ai/new/", views.ai_draft_create, name="ai_draft_create"),
    path(
        "sites/<uuid:site_id>/ai/<uuid:draft_id>/",
        views.ai_draft_detail,
        name="ai_draft_detail",
    ),
]
