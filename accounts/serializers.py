from rest_framework import serializers

from accounts.models import User
from customers.models import Customer


class UserSerializer(serializers.ModelSerializer):
    customer = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = User
        fields = [
            "id", "email", "full_name", "phone", "role", "customer",
            "is_active", "last_login", "created_at",
        ]
        read_only_fields = ["id", "role", "customer", "is_active", "last_login", "created_at"]


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    company_name = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = User
        fields = ["email", "password", "full_name", "phone", "company_name"]

    def create(self, validated_data):
        company_name = validated_data.pop("company_name", "")
        full_name = validated_data.pop("full_name", "")
        email = validated_data["email"]
        password = validated_data["password"]

        # Create the customer first
        customer = Customer.objects.create(
            name=full_name or email.split("@")[0],
            company_name=company_name,
            email=email,
            status=Customer.ACTIVE,
            owner=None,
        )

        user = User.objects.create_user(
            email=email,
            password=password,
            full_name=full_name,
            role=User.Role.CUSTOMER,
            customer=customer,
        )
        customer.owner = user
        customer.save(update_fields=["owner"])
        return user


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)

    def validate_old_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Old password is incorrect.")
        return value


class CustomerUserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ["email", "password", "full_name", "phone"]

    def validate(self, attrs):
        request = self.context["request"]
        if not getattr(request.user, "customer_id", None) and not getattr(request.user, "is_super_admin", False):
            raise serializers.ValidationError("No customer associated with this user.")
        return attrs

    def create(self, validated_data):
        request = self.context["request"]
        customer = getattr(request.user, "customer", None)
        if customer is None and getattr(request.user, "is_super_admin", False):
            customer = validated_data.pop("customer", None)
        if customer is None:
            raise serializers.ValidationError("A customer is required.")

        user = User.objects.create_user(
            email=validated_data["email"],
            password=validated_data["password"],
            full_name=validated_data.get("full_name", ""),
            phone=validated_data.get("phone", ""),
            role=User.Role.CUSTOMER_USER,
            customer=customer,
        )
        return user
