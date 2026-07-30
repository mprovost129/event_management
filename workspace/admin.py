from django.contrib import admin

from .models import (
    Activity,
    AIContentDraft,
    AutomationRule,
    AutomationRun,
    Document,
    IntakeForm,
    IntakeSubmission,
    Sponsor,
    Sponsorship,
    TaskChecklistItem,
    TaskComment,
    VolunteerAssignment,
    VolunteerHourEntry,
    VolunteerProfile,
    VolunteerShift,
    WorkTask,
)

admin.site.register(Activity)
admin.site.register(Document)
admin.site.register(WorkTask)
admin.site.register(TaskChecklistItem)
admin.site.register(TaskComment)

for model in (
    VolunteerProfile,
    VolunteerShift,
    VolunteerAssignment,
    VolunteerHourEntry,
    Sponsor,
    Sponsorship,
):
    admin.site.register(model)

admin.site.register(IntakeForm)
admin.site.register(IntakeSubmission)
admin.site.register(AutomationRule)
admin.site.register(AutomationRun)
admin.site.register(AIContentDraft)
