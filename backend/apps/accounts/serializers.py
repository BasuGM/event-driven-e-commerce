from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="display_name")

    class Meta:
        model = User
        fields = ["id", "email", "name", "is_staff"]
        read_only_fields = fields


class MeSerializer(serializers.Serializer):
    user = UserSerializer(allow_null=True, read_only=True)
    cart_count = serializers.IntegerField(read_only=True, help_text="Units in your cart (0 when logged out)")


class CsrfSerializer(serializers.Serializer):
    csrf_token = serializers.CharField(read_only=True)


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(trim_whitespace=False, style={"input_type": "password"})


class RegisterSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(trim_whitespace=False, min_length=8, style={"input_type": "password"})

    def validate_email(self, value: str) -> str:
        value = value.strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value

    def validate(self, attrs):
        first, _, last = attrs["name"].strip().partition(" ")
        candidate = User(username=attrs["email"], email=attrs["email"], first_name=first, last_name=last)
        validate_password(attrs["password"], user=candidate)  # Django's validators -> 400 messages
        return attrs

    def create(self, validated_data):
        first, _, last = validated_data["name"].strip().partition(" ")
        return User.objects.create_user(
            username=validated_data["email"], email=validated_data["email"],
            password=validated_data["password"], first_name=first, last_name=last,
        )
