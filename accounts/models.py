from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models

from accounts.managers import UserManager
from core.models import UUIDModel, TimeStampedModel


class User(UUIDModel, AbstractBaseUser, PermissionsMixin, TimeStampedModel):
    class Role(models.TextChoices):
        SUPER_ADMIN = "SUPER_ADMIN", "Super Admin"
        ADMIN = "ADMIN", "Admin"
        CUSTOMER = "CUSTOMER", "Customer"
        CUSTOMER_USER = "CUSTOMER_USER", "Customer User"

    email = models.EmailField(unique=True, db_index=True)
    full_name = models.CharField(max_length=255, blank=True, default="")
    phone = models.CharField(max_length=20, blank=True, default="")

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CUSTOMER, db_index=True)
    customer = models.ForeignKey(
        "customers.Customer",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="users",
    )

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)

    last_login = models.DateTimeField(null=True, blank=True)
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["role", "is_active"]),
        ]
        verbose_name = "مستخدم"
        verbose_name_plural = "المستخدمون"

    def __str__(self):
        return self.email

    @property
    def is_super_admin(self) -> bool:
        return self.role == self.Role.SUPER_ADMIN or self.is_superuser

    @property
    def is_admin(self) -> bool:
        return self.role == self.Role.ADMIN

    @property
    def is_customer(self) -> bool:
        return self.role == self.Role.CUSTOMER

    @property
    def is_customer_user(self) -> bool:
        return self.role == self.Role.CUSTOMER_USER

    def get_customer(self):
        """Resolve the customer this user belongs to."""
        if self.customer_id:
            return self.customer
        return None

    def has_customer_access(self, customer) -> bool:
        """RBAC: whether user can access a given customer's data."""
        if self.is_super_admin or self.is_admin:
            return True
        return customer is not None and self.customer_id == customer.id
