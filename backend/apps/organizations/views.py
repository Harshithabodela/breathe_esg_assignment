from django.contrib.auth import authenticate, login, logout
from django.middleware.csrf import get_token
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated

class LoginView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        username = request.data.get("username")
        password = request.data.get("password")
        user = authenticate(request, username=username, password=password)
        if user is None:
            return Response({"error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)
        login(request, user)
        get_token(request)
        org = None
        if hasattr(user, "membership"):
            org = {"id": user.membership.organization.id, "name": user.membership.organization.name}
        return Response({"id": user.id, "username": user.username, "organization": org})

class LogoutView(APIView):
    def post(self, request):
        logout(request)
        return Response({"ok": True})

class CsrfView(APIView):
    permission_classes = [AllowAny]
    def get(self, request):
        return Response({"csrfToken": get_token(request)})

class MeView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        user = request.user
        org = None
        if hasattr(user, "membership"):
            org = {"id": user.membership.organization.id, "name": user.membership.organization.name}
        return Response({"id": user.id, "username": user.username, "organization": org})
