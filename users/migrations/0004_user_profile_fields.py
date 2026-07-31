from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0003_user_users_email_ci_unique"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="avatar",
            field=models.ImageField(blank=True, upload_to="user-avatars/%Y/%m/"),
        ),
        migrations.AddField(
            model_name="user",
            name="mailing_address_line1",
            field=models.CharField(blank=True, max_length=180),
        ),
        migrations.AddField(
            model_name="user",
            name="mailing_address_line2",
            field=models.CharField(blank=True, max_length=180),
        ),
        migrations.AddField(
            model_name="user",
            name="mailing_city",
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AddField(
            model_name="user",
            name="mailing_country",
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AddField(
            model_name="user",
            name="mailing_postal_code",
            field=models.CharField(blank=True, max_length=20),
        ),
        migrations.AddField(
            model_name="user",
            name="mailing_state",
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AddField(
            model_name="user",
            name="username",
            field=models.CharField(blank=True, max_length=80),
        ),
    ]
