import re
from rest_framework import serializers
from django.contrib.auth.hashers import check_password
from django.utils import timezone
from rest_framework import serializers
from .models import User, EmailVerificationOTP

class RegisterSerializer(serializers.ModelSerializer):
    username = serializers.CharField(required=False, validators=[])
    email = serializers.EmailField(required=True)
    phone = serializers.CharField(required=True)

    class Meta:
        model = User
        fields = ['username', 'email', 'password', 'role', 'phone', 'first_name', 'last_name']
        extra_kwargs = {
            'password': {'write_only': True}
        }

    def validate_email(self, value):
        cleaned_email = value.lower().strip()

        if User.objects.filter(email__iexact=cleaned_email).exists():
            raise serializers.ValidationError(
                'A user with this email already exists.'
            )

        return cleaned_email

    def validate_password(self, value):
        if len(value) < 8:
            raise serializers.ValidationError(
                'Password must be at least 8 characters long.'
            )

        if not re.search(r'[A-Za-z]', value):
            raise serializers.ValidationError(
                'Password must include at least 1 letter.'
            )

        if not re.search(r'\d', value):
            raise serializers.ValidationError(
                'Password must include at least 1 number.'
            )

        return value

    def validate_phone(self, value):
        cleaned_phone = re.sub(r'[\s()-]', '', value)

        if re.match(r'^03\d{9}$', cleaned_phone):
            cleaned_phone = '+92' + cleaned_phone[1:]
        elif re.match(r'^923\d{9}$', cleaned_phone):
            cleaned_phone = '+' + cleaned_phone
        elif re.match(r'^\+923\d{9}$', cleaned_phone):
            pass
        else:
            raise serializers.ValidationError(
                'Enter a valid phone number, e.g. 03001234567 or +923001234567.'
            )

        if User.objects.filter(phone=cleaned_phone).exists():
            raise serializers.ValidationError(
                'This phone number is already registered.'
            )

        return cleaned_phone

    def create(self, validated_data):
        email = validated_data['email']

        user = User.objects.create_user(
        username=email,
        email=email,
        password=validated_data['password'],
        role=validated_data['role'],
        phone=validated_data.get('phone'),
        first_name=validated_data.get('first_name', ''),
        last_name=validated_data.get('last_name', ''),
        is_active=False,
        email_verified=False,
    )
        return user
    
    from django.contrib.auth.hashers import check_password
from django.utils import timezone


class VerifyEmailOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(min_length=6, max_length=6)

    def validate_otp(self, value):
        value = value.strip()

        if not value.isdigit():
            raise serializers.ValidationError('OTP must contain digits only.')

        return value

    def validate(self, attrs):
        email = attrs['email'].lower().strip()
        otp = attrs['otp'].strip()

        user = User.objects.filter(email__iexact=email).first()

        if not user:
            raise serializers.ValidationError({
                'email': 'No account found with this email.'
            })

        if user.is_active and user.email_verified:
            raise serializers.ValidationError({
                'email': 'This email is already verified.'
            })

        otp_obj = EmailVerificationOTP.objects.filter(user=user).first()

        if not otp_obj:
            raise serializers.ValidationError({
                'otp': 'No OTP found. Please request a new OTP.'
            })

        if timezone.now() > otp_obj.expires_at:
            raise serializers.ValidationError({
                'otp': 'OTP has expired. Please request a new OTP.'
            })

        if otp_obj.attempts >= 5:
            raise serializers.ValidationError({
                'otp': 'Too many incorrect attempts. Please request a new OTP.'
            })

        if not check_password(otp, otp_obj.code_hash):
            otp_obj.attempts += 1
            otp_obj.save(update_fields=['attempts'])

            raise serializers.ValidationError({
                'otp': 'Invalid OTP.'
            })

        attrs['user'] = user
        attrs['otp_obj'] = otp_obj

        return attrs