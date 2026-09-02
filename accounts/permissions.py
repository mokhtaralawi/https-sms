from rest_framework.permissions import BasePermission, SAFE_METHODS


class IsSuperAdmin(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_super_admin)


class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_admin)


class IsAdminOrReadOnly(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and (request.user.is_admin or request.method in SAFE_METHODS)
        )


class IsOwnerOrAdmin(BasePermission):
    """Allow if user is admin, or object belongs to user's customer."""

    def has_object_permission(self, request, view, obj):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if user.is_admin:
            return True
        obj_customer = getattr(obj, "customer", None)
        if obj_customer is None and hasattr(obj, "user"):
            obj_customer = getattr(obj.user, "customer", None)
        return user.customer_id == getattr(obj_customer, "id", None)


class IsCustomerManager(BasePermission):
    """Allow only customer role with its own customer."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.customer_id)


class IsSelfCustomer(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_customer)


class AllowAnyAPIKey(BasePermission):
    def has_permission(self, request, view):
        return bool(request.auth and hasattr(request.auth, "api_key"))
