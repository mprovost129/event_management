from django.contrib.auth.tokens import PasswordResetTokenGenerator


class EmailVerificationTokenGenerator(PasswordResetTokenGenerator):
    def _make_hash_value(self, user, timestamp):
        verified_at = (
            user.email_verified_at.isoformat() if user.email_verified_at else ""
        )
        return f"{user.pk}{timestamp}{user.email}{user.is_active}{verified_at}"


email_verification_token = EmailVerificationTokenGenerator()
