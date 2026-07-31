import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("events", "0003_registration_payment_status"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="event",
            name="featured_image",
            field=models.ImageField(blank=True, upload_to="event-images/%Y/%m/"),
        ),
        migrations.CreateModel(
            name="EventAlbum",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("title", models.CharField(max_length=180)),
                ("slug", models.SlugField(max_length=180)),
                ("description", models.TextField(blank=True)),
                (
                    "status",
                    models.CharField(
                        choices=[("draft", "Draft"), ("published", "Published")],
                        db_index=True,
                        default="draft",
                        max_length=20,
                    ),
                ),
                ("published_at", models.DateTimeField(blank=True, null=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="event_albums_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "occurrence",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="albums",
                        to="events.eventoccurrence",
                    ),
                ),
                (
                    "site",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="sites.site",
                    ),
                ),
            ],
            options={"ordering": ("-occurrence__starts_at", "title")},
        ),
        migrations.CreateModel(
            name="EventPhoto",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("image", models.ImageField(upload_to="event-albums/%Y/%m/")),
                ("caption", models.CharField(blank=True, max_length=240)),
                (
                    "alt_text",
                    models.CharField(
                        help_text=(
                            "Briefly describe what is visible for people using "
                            "screen readers."
                        ),
                        max_length=180,
                    ),
                ),
                ("position", models.PositiveIntegerField(default=0)),
                (
                    "album",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="photos",
                        to="events.eventalbum",
                    ),
                ),
                (
                    "site",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="sites.site",
                    ),
                ),
                (
                    "uploaded_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="event_photos_uploaded",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ("position", "created_at"),
                "indexes": [
                    models.Index(
                        fields=["album", "position"],
                        name="events_photo_album_pos_idx",
                    )
                ],
            },
        ),
        migrations.AddField(
            model_name="eventalbum",
            name="cover_photo",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="events.eventphoto",
            ),
        ),
        migrations.AddConstraint(
            model_name="eventalbum",
            constraint=models.UniqueConstraint(
                fields=("site", "slug"),
                name="events_unique_album_slug_per_site",
            ),
        ),
    ]
