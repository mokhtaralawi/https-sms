from rest_framework.permissions import BasePermission

from api_keys.authentication import APIKeyPrincipal


class IsSuperAdmin(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and getattr(user, "is_super_admin", False))


class IsAdminOrSuper(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and (getattr(user, "is_admin", False) or getattr(user, "is_super_admin", False)))


class IsStaffUser(BasePermission):
    """Only for real user accounts (not API keys)."""

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and not isinstance(user, APIKeyPrincipal))


class IsCustomerUser(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and getattr(user, "is_customer", False))


class IsCustomerUserOrBetter(BasePermission):
    """CUSTOMER or CUSTOMER_USER or staff or an authenticated API key principal."""

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if isinstance(user, APIKeyPrincipal):
            return True
        return (
            getattr(user, "is_super_admin", False)
            or getattr(user, "is_admin", False)
            or getattr(user, "is_customer", False)
            or getattr(user, "is_customer_user", False)
        )


class HasCustomerAccess(BasePermission):
    """
    Object-level permission: verifies that the user belongs to the customer
    on the object, or is staff.
    """

    def has_object_permission(self, request, view, obj):
        user = request.user
        if isinstance(user, APIKeyPrincipal):
            # API key owns its customer
            return getattr(obj, "customer_id", None) == user.customer.id
        if not (user and user.is_authenticated):
            return False
        if getattr(user, "is_super_admin", False) or getattr(user, "is_admin", False):
            return True
        customer = getattr(obj, "customer", None)
        return customer is not None and user.customer_id == customer.id


class IsActiveCustomerResource(BasePermission):
    """Allow authenticated requesters that belong to an ACTIVE customer."""

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if isinstance(user, APIKeyPrincipal):
            return user.customer.status == "ACTIVE"
        if getattr(user, "is_super_admin", False) or getattr(user, "is_admin", False):
            return True
        customer = getattr(user, "customer", None)
        return customer is not None and customer.status == "ACTIVE"
