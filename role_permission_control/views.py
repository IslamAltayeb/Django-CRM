from rest_framework.views import APIView
from rest_framework.response import Response
from .models import Role
from .serializer import RoleWithPermissionsSerializer
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from drf_spectacular.utils import extend_schema
from common.models import Profile

class RoleListAPIView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(tags=["roles"])
    def get(self, request):
        if self.request.profile.role.name != "ADMIN" and not self.request.user.is_superuser:
            return Response(
                {"error": True, "errors": "Permission Denied"},
                status=status.HTTP_403_FORBIDDEN,
            )
        roles = Role.objects.all()
        serializer = RoleWithPermissionsSerializer(roles, many=True)
        return Response(serializer.data)