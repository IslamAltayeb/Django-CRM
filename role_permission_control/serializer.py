from rest_framework import serializers
from .models import Role, Permission, RolePermission

class PermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Permission
        fields = ['id', 'name' , 'description']

class RoleWithPermissionsSerializer(serializers.ModelSerializer):
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = Role
        fields = ['id', 'name', 'description', 'permissions']

    def get_permissions(self, role):
        role_permissions = RolePermission.objects.filter(role=role).select_related('permission')
        return PermissionSerializer([rp.permission for rp in role_permissions], many=True).data