from django.db import models
from django.conf import settings
from django.utils import timezone
from datetime import timedelta


class Package(models.Model):
    """A purchasable subscription package. Seeded via migration."""

    PACKAGE_IDS = [
        ('basic',        'Basic'),
        ('professional', 'Professional'),
        ('enterprise',   'Enterprise'),
    ]

    slug              = models.CharField(max_length=20, choices=PACKAGE_IDS, unique=True)
    name              = models.CharField(max_length=100)
    price             = models.DecimalField(max_digits=8, decimal_places=2)
    profile_limit     = models.PositiveIntegerField(help_text='0 = unlimited')
    validity_days     = models.PositiveIntegerField()
    features          = models.JSONField(default=list, help_text='List of feature strings')
    recommended       = models.BooleanField(default=False)
    sort_order        = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sort_order']

    def __str__(self):
        return f"{self.name} (${self.price})"

    @property
    def is_unlimited(self):
        return self.profile_limit == 0


class Purchase(models.Model):
    """An employer's purchase of a package. Acts as the unlock-quota holder."""

    STATUS_CHOICES = [
        ('active',    'Active'),
        ('expired',   'Expired'),
        ('exhausted', 'Exhausted'),
    ]

    employer       = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='purchases',
    )
    package        = models.ForeignKey(Package, on_delete=models.PROTECT, related_name='purchases')

    # Snapshot fields (so historical purchases stay accurate if package changes)
    package_name   = models.CharField(max_length=100)
    price_paid     = models.DecimalField(max_digits=8, decimal_places=2)
    profile_limit  = models.PositiveIntegerField()
    validity_days  = models.PositiveIntegerField()

    purchased_at   = models.DateTimeField(auto_now_add=True)
    expires_at     = models.DateTimeField()

    # Mock payment details (kept for FYP realism, never used)
    payment_method = models.CharField(max_length=20, default='card')
    transaction_id = models.CharField(max_length=64, blank=True, default='')

    class Meta:
        ordering = ['-purchased_at']

    def __str__(self):
        return f"{self.employer.username} → {self.package_name} ({self.status_label})"

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(days=self.validity_days)
        if not self.transaction_id:
            # Generate a fake transaction ID for display in receipts
            import uuid
            self.transaction_id = f"FYP-{uuid.uuid4().hex[:16].upper()}"
        super().save(*args, **kwargs)

    @property
    def is_active(self) -> bool:
        if not self.expires_at:
            return False
        return timezone.now() < self.expires_at

    @property
    def unlocks_used(self) -> int:
        return self.unlocks.count()

    @property
    def unlocks_remaining(self):
        """None = unlimited."""
        if self.profile_limit == 0:
            return None
        return max(0, self.profile_limit - self.unlocks_used)

    @property
    def has_capacity(self) -> bool:
        if self.profile_limit == 0:
            return True
        return self.unlocks_used < self.profile_limit

    @property
    def status_label(self) -> str:
        if not self.is_active:
            return 'expired'
        if not self.has_capacity:
            return 'exhausted'
        return 'active'


class ProfileUnlock(models.Model):
    """
    Records that an employer has unlocked one specific candidate profile,
    consuming one slot from a Purchase.
    """

    purchase    = models.ForeignKey(Purchase, on_delete=models.CASCADE, related_name='unlocks')
    employer    = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile_unlocks')
    candidate   = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='unlocked_by_employers')
    unlocked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('employer', 'candidate')
        ordering = ['-unlocked_at']

    def __str__(self):
        return f"{self.employer.username} unlocked {self.candidate.username}"
