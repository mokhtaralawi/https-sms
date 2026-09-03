import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import redirect, render

from accounts.models import User
from customers.models import Customer
from otp.services import OTPError, OTPService

logger = logging.getLogger("httpsms.web")


def _email_for_login(email: str) -> str:
    return (email or "").strip().lower()


def index_view(request):
    """Landing page. Redirect to dashboard if logged in, else login page."""
    if request.user.is_authenticated:
        return redirect("webapp:dashboard")
    return redirect("webapp:login")


def _client_ip(request):
    fwd = request.META.get("HTTP_X_FORWARDED_FOR")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def register_view(request):
    """Registration: collect email + password, then send email OTP."""
    if request.user.is_authenticated:
        return redirect("webapp:dashboard")

    if request.method == "POST":
        email = _email_for_login(request.POST.get("email"))
        password = request.POST.get("password")
        password2 = request.POST.get("password_confirm")
        full_name = request.POST.get("full_name", "").strip()
        company_name = request.POST.get("company_name", "").strip()

        if not email or not password:
            messages.error(request, "البريد الإلكتروني وكلمة المرور مطلوبان.")
        elif password != password2:
            messages.error(request, "كلمتا المرور غير متطابقتين.")
        elif len(password) < 8:
            messages.error(request, "كلمة المرور يجب أن تكون 8 أحرف على الأقل.")
        elif User.objects.filter(email__iexact=email).exists():
            messages.error(request, "هذا البريد الإلكتروني مسجل مسبقاً. سجّل دخولك.")
        else:
            # Persist form data in session until OTP is verified.
            request.session["pending_register"] = {
                "email": email,
                "password": password,
                "full_name": full_name,
                "company_name": company_name,
            }
            try:
                OTPService.send_email(email, purpose="registration")
            except OTPError as exc:
                messages.error(request, str(exc))
            except Exception:
                logger.exception("Failed to send email OTP")
                messages.error(request, "تعذر إرسال رمز التحقق. تحقق من إعداد البريد.")
            else:
                return redirect("webapp:otp")

    return render(request, "webapp/register.html")


def otp_view(request):
    """Enter the code sent to the email and complete registration."""
    pending = request.session.get("pending_register")
    if not pending:
        return redirect("webapp:register")

    email = pending["email"]

    if request.method == "POST":
        action = request.POST.get("action")
        code = request.POST.get("code", "").strip()

        if action == "resend":
            try:
                OTPService.send_email(email, purpose="registration")
            except OTPError as exc:
                messages.error(request, str(exc))
            else:
                messages.info(request, "تم إعادة إرسال الرمز.")
            return redirect("webapp:otp")

        if action == "cancel":
            request.session.pop("pending_register", None)
            return redirect("webapp:register")

        if len(code) < 4:
            messages.error(request, "أدخل رمز التحقق.")
        else:
            try:
                ok = OTPService.verify_email(email, code, purpose="registration")
            except OTPError as exc:
                messages.error(request, str(exc))
                ok = False
                return redirect("webapp:otp")

            if ok:
                return _create_user_from_pending(request)
            messages.error(request, "رمز التحقق غير صحيح أو منتهي الصلاحية.")

    return render(request, "webapp/otp.html", {"email": email})


def _create_user_from_pending(request):
    from audit.models import AuditLog

    pending = request.session.pop("pending_register", None)
    if not pending:
        return redirect("webapp:register")

    email = pending["email"]
    password = pending["password"]
    full_name = pending.get("full_name") or email.split("@")[0]
    company_name = pending.get("company_name", "")

    try:
        with transaction.atomic():
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

            # Auto-generate an API key for the new customer.
            from api_keys.models import APIKey
            api_key, raw = APIKey.create_for_customer(
                user.customer, name="Default API Key", environment="LIVE"
            )
            request.session["api_key_once"] = {"key": raw, "name": api_key.name}

            AuditLog.objects.create(
                action="register", user=user, customer=customer,
                metadata={"method": "web_email_otp"},
            )

        auth_login(request, user)
        messages.success(request, "تم تفعيل حسابك بنجاح.")
        return redirect("webapp:dashboard")
    except Exception:
        logger.exception("Failed to create user after OTP")
        messages.error(request, "حدث خطأ أثناء إنشاء الحساب. حاول مجدداً.")
        return redirect("webapp:register")


def login_view(request):
    if request.user.is_authenticated:
        return redirect("webapp:dashboard")

    if request.method == "POST":
        email = _email_for_login(request.POST.get("email"))
        password = request.POST.get("password")
        user = User.objects.filter(email__iexact=email).first()
        if user is not None and user.check_password(password) and user.is_active:
            auth_login(request, user)
            user.last_login_ip = _client_ip(request)
            user.save(update_fields=["last_login_ip"])
            from audit.models import AuditLog
            AuditLog.objects.create(
                action="login", user=user, customer=user.customer,
                ip_address=_client_ip(request), metadata={"method": "web_login"},
            )
            messages.success(request, "مرحباً بعودتك!")
            return redirect("webapp:dashboard")
        messages.error(request, "بيانات الدخول غير صحيحة.")

    return render(request, "webapp/login.html")


@login_required(login_url="webapp:login")
def dashboard_view(request):
    from api_keys.models import APIKey

    api_key_once = request.session.pop("api_key_once", None)
    api_key_objs = list(APIKey.objects.filter(customer=request.user.customer).order_by("-created_at")[:20])
    return render(request, "webapp/dashboard.html", {
        "api_key_once": api_key_once,
        "api_keys": api_key_objs,
    })


def logout_view(request):
    from audit.models import AuditLog
    if request.user.is_authenticated:
        AuditLog.objects.create(
            action="logout", user=request.user, customer=getattr(request.user, "customer", None)
        )
    auth_logout(request)
    messages.info(request, "تم تسجيل الخروج.")
    return redirect("webapp:login")


def google_login(request):
    """Redirect to Google's OAuth consent screen (requires GOOGLE_OAUTH_* settings)."""
    client_id = settings.GOOGLE_OAUTH_CLIENT_ID
    redirect_uri = settings.GOOGLE_REDIRECT_URI or (
        request.build_absolute_uri("/google/callback/")
    )
    if not client_id:
        messages.error(request, "تسجيل الدخول عبر Google غير مفعّل بعد.")
        return redirect("webapp:login")

    base = "https://accounts.google.com/o/oauth2/v2/auth"
    state = _google_state(request)
    params = (
        "?client_id=%s&redirect_uri=%s&response_type=code"
        "&scope=openid%%20email%%20profile&state=%s"
        % (client_id, redirect_uri, state)
    )
    return redirect(base + params)


def _google_state(request):
    from django.utils.crypto import get_random_string
    state = get_random_string(32)
    request.session["google_oauth_state"] = state
    return state


def google_callback(request):
    from django.utils.crypto import constant_time_compare

    error = request.GET.get("error")
    if error:
        messages.error(request, "أُلغيت مصادقة Google.")
        return redirect("webapp:login")

    state = request.GET.get("state")
    if not state or not constant_time_compare(
        state, request.session.pop("google_oauth_state", "")
    ):
        messages.error(request, "فشل التحقق من طلب Google.")
        return redirect("webapp:login")

    code = request.GET.get("code")
    if not code:
        messages.error(request, "لم يتم استلام رمز التأكيد من Google.")
        return redirect("webapp:login")

    client_id = settings.GOOGLE_OAUTH_CLIENT_ID
    client_secret = settings.GOOGLE_OAUTH_CLIENT_SECRET
    redirect_uri = settings.GOOGLE_REDIRECT_URI or (
        request.build_absolute_uri("/google/callback/")
    )

    import urllib.parse
    import urllib.request

    token_data = urllib.parse.urlencode({
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }).encode()

    token_req = urllib.request.Request(
        "https://oauth2.googleapis.com/token", data=token_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(token_req) as resp:
            token_payload = __import__("json").loads(resp.read().decode())
    except Exception:
        logger.exception("Google token exchange failed")
        messages.error(request, "تعذر إنهاء مصادقة Google.")
        return redirect("webapp:login")

    access_token = token_payload.get("access_token")
    if not access_token:
        messages.error(request, "تعذر الحصول على رمز الوصول من Google.")
        return redirect("webapp:login")

    import json
    userinfo_req = urllib.request.Request(
        "https://www.googleapis.com/oauth2/v2/userinfo",
        headers={"Authorization": "Bearer %s" % access_token},
    )
    try:
        with urllib.request.urlopen(userinfo_req) as resp:
            info = json.loads(resp.read().decode())
    except Exception:
        logger.exception("Google userinfo failed")
        messages.error(request, "تعذر قراءة بيانات حساب Google.")
        return redirect("webapp:login")

    google_email = (info.get("email") or "").lower()
    if not google_email:
        messages.error(request, "لم يوفّر حساب Google بريداً إلكترونياً.")
        return redirect("webapp:login")

    return _login_or_register_google(request, google_email, info.get("name") or "")


def _login_or_register_google(request, email, full_name):
    from audit.models import AuditLog

    user = User.objects.filter(email__iexact=email).first()
    if user is None:
        password = User.objects.make_random_password(24)
        customer = Customer.objects.create(
            name=full_name or email.split("@")[0],
            email=email,
            status=Customer.ACTIVE,
            owner=None,
        )
        user = User.objects.create_user(
            email=email, password=password, full_name=full_name,
            role=User.Role.CUSTOMER, customer=customer,
        )
        customer.owner = user
        customer.save(update_fields=["owner"])

        from api_keys.models import APIKey
        APIKey.create_for_customer(user.customer, name="Default API Key", environment="LIVE")

    auth_login(request, user)
    AuditLog.objects.create(
        action="login", user=user, customer=user.customer,
        ip_address=_client_ip(request), metadata={"method": "google_oauth"},
    )
    messages.success(request, "تم تسجيل الدخول عبر Google.")
    return redirect("webapp:dashboard")
