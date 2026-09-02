from rest_framework import serializers

from customers.models import Customer


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = [
            "id", "name", "company_name", "email", "phone", "status", "timezone",
            "plan", "max_devices", "max_api_keys", "rate_rps", "rate_per_min",
            "rate_per_hour", "rate_per_day", "rate_per_month", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class CustomerCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = ["name", "company_name", "email", "phone", "timezone"]
        extra_kwargs = {"email": {"required": True}}


class CustomerUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = ["name", "company_name", "phone", "timezone", "status"]
