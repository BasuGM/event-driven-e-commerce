from django.contrib.auth import authenticate, get_user_model, login, logout
from django.db.models import Sum
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.cart.models import CartItem

from .serializers import CsrfSerializer, LoginSerializer, MeSerializer, RegisterSerializer, UserSerializer

User = get_user_model()


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CsrfView(APIView):
    """Sets the csrftoken cookie. The browser sends it back as X-CSRFToken on unsafe requests."""

    permission_classes = [AllowAny]

    @extend_schema(responses=CsrfSerializer, summary="Get a CSRF token (sets the csrftoken cookie)")
    def get(self, request):
        return Response({"csrf_token": get_token(request)})


class MeView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(responses=MeSerializer, summary="The logged-in user, or null")
    def get(self, request):
        if not request.user.is_authenticated:
            return Response({"user": None, "cart_count": 0})
        # One request gives the header everything it needs (name + cart badge)
        count = CartItem.objects.filter(cart__user=request.user).aggregate(n=Sum("quantity"))["n"] or 0
        return Response({"user": UserSerializer(request.user).data, "cart_count": count})


# DRF's SessionAuthentication only checks CSRF for *authenticated* requests. Login/register are
# anonymous, so protect them explicitly (prevents login CSRF).
@method_decorator(csrf_protect, name="dispatch")
class LoginView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(request=LoginSerializer, responses={200: UserSerializer}, summary="Log in with email and password")
    def post(self, request):
        data = LoginSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        email, password = data.validated_data["email"], data.validated_data["password"]
        account = User.objects.filter(email__iexact=email).first()
        user = authenticate(request, username=account.username, password=password) if account else None
        if user is None:
            return Response(
                {"code": "invalid_credentials", "detail": "Email or password is incorrect."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        login(request, user)  # rotates the session id and the CSRF token
        return Response(UserSerializer(user).data)


@method_decorator(csrf_protect, name="dispatch")
class RegisterView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(request=RegisterSerializer, responses={201: UserSerializer}, summary="Create an account and log in")
    def post(self, request):
        data = RegisterSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        user = data.save()
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


class LogoutView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(request=None, responses={204: None}, summary="Log out")
    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)
