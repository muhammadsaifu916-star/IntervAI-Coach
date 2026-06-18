from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.db import transaction

from .models import Package, Purchase, ProfileUnlock
from .serializers import (
    PackageSerializer, PurchaseSerializer,
    CreatePurchaseSerializer, ProfileUnlockSerializer,
)


# ── Helpers ───────────────────────────────────────────────────────────────────
def _employer_only(request):
    """Return None if OK, else a Response to short-circuit with."""
    if request.user.role != 'employer':
        return Response(
            {'error': 'Only employers can use this endpoint.'},
            status=status.HTTP_403_FORBIDDEN,
        )
    return None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_packages(request):
    """Public catalog of purchasable packages."""
    packages = Package.objects.all()
    return Response(PackageSerializer(packages, many=True).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_purchase(request):
    """
    Self-checkout disabled.

    Payments are verified manually through bank transfer.
    Admin creates Purchase records after confirming payment proof.
    """
    err = _employer_only(request)
    if err:
        return err

    return Response(
        {
            'error': 'Online checkout is disabled.',
            'message': 'Please transfer payment using the displayed bank details and send proof on WhatsApp. Your package will be activated after manual verification.',
        },
        status=status.HTTP_403_FORBIDDEN,
    )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_purchases(request):
    """Employer's purchase history with usage stats."""
    err = _employer_only(request)
    if err: return err

    purchases = Purchase.objects.filter(employer=request.user)
    return Response(PurchaseSerializer(purchases, many=True).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def unlock_profile(request, candidate_id):
    """
    Unlock a single candidate's profile, consuming one slot from an active purchase.
    Body: empty (purchase is auto-selected — oldest active purchase with capacity).
    Idempotent: re-unlocking the same candidate is a no-op (returns existing record).
    """
    err = _employer_only(request)
    if err: return err

    # Verify the candidate is actually published
    from profiles.models import CandidateProfile
    try:
        CandidateProfile.objects.get(user__id=candidate_id, published=True)
    except CandidateProfile.DoesNotExist:
        return Response({'error': 'Candidate profile not found or not published.'},
                        status=status.HTTP_404_NOT_FOUND)

    if request.user.id == candidate_id:
        return Response({'error': 'You cannot unlock your own profile.'},
                        status=status.HTTP_400_BAD_REQUEST)
   
    with transaction.atomic():
        # Lock all purchase rows for this employer before checking capacity.
        # This prevents two unlock requests from consuming the same final slot.
        locked_purchases = list(
            Purchase.objects
            .select_for_update()
            .filter(employer=request.user)
            .order_by('purchased_at')
        )

        # Re-check existing unlock inside the transaction after locking.
        existing = ProfileUnlock.objects.filter(
            employer=request.user,
            candidate_id=candidate_id,
        ).first()

        if existing:
            return Response(
                {
                    'unlock': ProfileUnlockSerializer(existing).data,
                    'already_unlocked': True,
                },
                status=status.HTTP_200_OK,
            )

        usable_purchase = None
        for purchase in locked_purchases:
            if purchase.is_active and purchase.has_capacity:
                usable_purchase = purchase
                break

        if not usable_purchase:
            return Response(
                {
                    'error': 'No active purchase available.',
                    'reason': 'You need to buy a package or your current package has expired or run out of unlocks.',
                    'purchase_required': True,
                },
                status=status.HTTP_402_PAYMENT_REQUIRED,
            )

        # Final safety check before creating the unlock.
        if not usable_purchase.has_capacity:
            return Response(
                {
                    'error': 'No active purchase available.',
                    'reason': 'Your current package has run out of unlocks.',
                    'purchase_required': True,
                },
                status=status.HTTP_402_PAYMENT_REQUIRED,
            )

        unlock = ProfileUnlock.objects.create(
            purchase=usable_purchase,
            employer=request.user,
            candidate_id=candidate_id,
        )

        return Response(
            {
                'unlock': ProfileUnlockSerializer(unlock).data,
                'purchase': PurchaseSerializer(usable_purchase).data,
                'already_unlocked': False,
            },
            status=status.HTTP_201_CREATED,
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_unlocks(request):
    """List all profiles this employer has unlocked."""
    err = _employer_only(request)
    if err: return err

    unlocks = ProfileUnlock.objects.filter(employer=request.user).select_related('purchase')
    return Response(ProfileUnlockSerializer(unlocks, many=True).data)
