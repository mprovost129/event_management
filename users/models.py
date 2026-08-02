from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone

from .managers import UserManager


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    username = models.CharField(max_length=80, blank=True)
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    avatar = models.ImageField(upload_to="user-avatars/%Y/%m/", blank=True)
    mailing_address_line1 = models.CharField(max_length=180, blank=True)
    mailing_address_line2 = models.CharField(max_length=180, blank=True)
    mailing_city = models.CharField(max_length=80, blank=True)
    mailing_state = models.CharField(max_length=80, blank=True)
    mailing_postal_code = models.CharField(max_length=20, blank=True)
    mailing_country = models.CharField(max_length=80, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_subscription_exempt = models.BooleanField(
        default=False,
        help_text=(
            "When enabled, this user can manage organizations without an active paid "
            "platform subscription."
        ),
    )
    date_joined = models.DateTimeField(default=timezone.now)
    email_verified_at = models.DateTimeField(null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = "user"
        verbose_name_plural = "users"
        constraints = [
            models.UniqueConstraint(Lower("email"), name="users_email_ci_unique")
        ]

    def save(self, *args, **kwargs):
        self.email = self.email.strip().lower()
        self.username = self.username.strip()
        super().save(*args, **kwargs)

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def get_short_name(self):
        return self.first_name

    def __str__(self):
        return self.email

    @property
    def is_email_verified(self):
        return self.email_verified_at is not None
