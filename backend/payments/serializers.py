from rest_framework import serializers
from .models import Package, Purchase, ProfileUnlock


class PackageSerializer(serializers.ModelSerializer):
    is_unlimited = serializers.BooleanField(read_only=True)

    class Meta:
        model  = Package
        fields = ['id', 'slug', 'name', 'price', 'profile_limit',
                  'validity_days', 'features', 'recommended', 'is_unlimited']


class PurchaseSerializer(serializers.ModelSerializer):
    status_label      = serializers.CharField(read_only=True)
    is_active         = serializers.BooleanField(read_only=True)
    unlocks_used      = serializers.IntegerField(read_only=True)
    unlocks_remaining = serializers.IntegerField(read_only=True, allow_null=True)
    has_capacity      = serializers.BooleanField(read_only=True)

    class Meta:
        model = Purchase
        fields = [
            'id', 'package_name', 'price_paid', 'profile_limit', 'validity_days',
            'purchased_at', 'expires_at', 'payment_method', 'transaction_id',
            'status_label', 'is_active', 'unlocks_used', 'unlocks_remaining', 'has_capacity',
        ]


class CreatePurchaseSerializer(serializers.Serializer):
    """Mock checkout input — package slug + dummy payment fields."""
    package_slug   = serializers.ChoiceField(choices=Package.PACKAGE_IDS)
    payment_method = serializers.ChoiceField(choices=['card', 'paypal', 'bank'], default='card')

    # All accepted but discarded — for UI realism only
    card_number    = serializers.CharField(required=False, allow_blank=True)
    card_name      = serializers.CharField(required=False, allow_blank=True)
    expiry_date    = serializers.CharField(required=False, allow_blank=True)
    cvv            = serializers.CharField(required=False, allow_blank=True)


class ProfileUnlockSerializer(serializers.ModelSerializer):
    purchase_id = serializers.IntegerField(source='purchase.id', read_only=True)

    class Meta:
        model  = ProfileUnlock
        fields = ['id', 'candidate', 'unlocked_at', 'purchase_id']
