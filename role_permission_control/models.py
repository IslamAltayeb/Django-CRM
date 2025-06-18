from django.db import models
from django.contrib.auth.models import AbstractUser, Group, Permission as DjangoPermission 
from django.conf import settings

class Role(models.Model):
    name = models.CharField(max_length=80, unique=True, null=False)
    description = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = "Role"
        verbose_name_plural = "Roles"
        ordering = ['name'] 
        db_table = 'role'
        

    def __str__(self):
        return self.name

class Permission(models.Model):
    name = models.CharField(max_length=100, unique=True, null=False)
    description = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = "Permission"
        verbose_name_plural = "Permissions"
        ordering = ['name'] 
        db_table = 'permission'

    def __str__(self):
        return self.name
    

class RolePermission(models.Model):
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name='role_permissions')
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE, related_name='permission_roles')

    class Meta:
        unique_together = ('role', 'permission') # A role should only have a specific permission once
        verbose_name = "Role Permission"
        verbose_name_plural = "Role Permissions"
        db_table = 'role_permission'

    def __str__(self):
        return f"{self.role.name} - {self.permission.name}"
