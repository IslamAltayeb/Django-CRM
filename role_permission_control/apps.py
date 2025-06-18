from django.apps import AppConfig


class RolePermissionControlConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'role_permission_control'

    def ready(self):
        """
        Import signals when the app is ready.
        This ensures our signal handlers are registered.
        """
        import role_permission_control.signals 
