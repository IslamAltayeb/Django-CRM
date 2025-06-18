from django.db.models.signals import post_migrate
from django.dispatch import receiver
from django.apps import apps
from django.db import transaction


@receiver(post_migrate)
def seed_rbac_data(sender, app_config, verbosity, interactive, **kwargs):
    """
    Signal receiver to seed initial roles, permissions, and their mappings
    after migrations are applied for the 'role_permission_control' app.

    This function uses get_or_create to ensure idempotency, meaning it can be
    run multiple times without creating duplicate data.
    """
    # Only run this seeding logic for 'role_permission_control' app
    # This prevents it from running for every app's migrations.
    if app_config.label != 'role_permission_control':
        return

    try:
        Role = apps.get_model('role_permission_control', 'Role')
        Permission = apps.get_model('role_permission_control', 'Permission')
        RolePermission = apps.get_model('role_permission_control', 'RolePermission')
    except LookupError:
        print("RBAC models not found. Skipping initial data seeding.")
        return

    print("Seeding initial RBAC roles, permissions, and mappings...")

    with transaction.atomic(): # Ensure atomicity of the seeding process

        roles_to_create = {
            'ADMIN': 'Full system access, including user management and system settings.',
            'Sales Manager': 'Manages everything, but cannot manage users.',
            'Sales Representative': 'Manages their own resource.',
            'Generic Employee': 'Read-only access to basic contact information.'
        }

        # Create/Get Roles
        created_roles = {}
        for name, description in roles_to_create.items():
            role, created = Role.objects.get_or_create(
                name=name,
                defaults={'description': description}
            )
            created_roles[name] = role
            if created:
                print(f"  Created Role: {name}")

        permissions_to_create = [
            # User Management
            ('View all users', 'Allows viewing all users.'),
            ('Create new user', 'Allows creating new user.'),
            ('Edit user', 'Allows editing existing user.'),
            ('Delete user', 'Allows deleting user.'),

            #Role and permissions Management
            ('View roles and their permissions', 'Allows viewing defined roles and their associated permissions.'),
            ('Create new role','Allows creating new role and assign the needed permissions to it.'),
            ('Edit role','Allows editing an existing role and its permissions.'),
            ('Delete role','Allows deleting role.'),
            ('View all permissions','Allows viewing all permissions.'),
            ('Create new permission','Allows creating new permission.'),
            ('Edit permission', 'Allows editing an existing permission.'),
            ('Delete permission','Allows deleting an existing permission'),

            # Contact Management
            ('View all contacts', 'Allows viewing all contacts in the CRM.'),
            ('View own contacts', 'Allows viewing contacts owned by the user.'),
            ('Create new contacts', 'Allows creating new contact records.'),
            ('Edit any contact', 'Allows editing any contact record.'),
            ('Edit own contacts', 'Allows editing contact records owned by the user.'),
            ('Delete any contact', 'Allows deleting any contact record.'),
            ('Delete own contacts', 'Allows deleting contact records owned by the user.'),

            # Lead Management
            ('View all leads', 'Allows viewing all leads in the CRM.'),
            ('View own leads', 'Allows viewing leads owned by the user.'),
            ('Create new leads', 'Allows creating new lead records.'),
            ('Edit any lead', 'Allows editing any lead record.'),
            ('Edit own leads', 'Allows editing lead records owned by the user.'),
            ('Delete any lead', 'Allows deleting any lead record.'),
            ('Delete own leads', 'Allows deleting lead records owned by the user.'),

            # Opportunity Management
            ('View all opportunities', 'Allows viewing all opportunities in the CRM.'),
            ('View own opportunities', 'Allows viewing opportunities owned by the user.'),
            ('Create new opportunities', 'Allows creating new opportunity records.'),
            ('Edit any opportunity', 'Allows editing any opportunity record.'),
            ('Edit own opportunities', 'Allows editing opportunity records owned by the user.'),
            ('Delete any opportunity', 'Allows deleting any opportunity record.'),
            ('Delete own opportunities', 'Allows deleting opportunity records owned by the user.'),

            # Account Management 
            ('View all accounts', 'Allows viewing all account records in the CRM.'),
            ('View own accounts', 'Allows viewing account records owned by the user.'),
            ('Create new accounts', 'Allows creating new account records.'),
            ('Edit any account', 'Allows editing any account record.'),
            ('Edit own accounts', 'Allows editing account records owned by the user.'),
            ('Delete any account', 'Allows deleting any account record.'),
            ('Delete own accounts', 'Allows deleting account records owned by the user.'),

            # Company Management 
            ('View all companies', 'Allows viewing all company records in the CRM.'),
            ('View own companies', 'Allows viewing company records owned by the user.'),
            ('Create new companies', 'Allows creating new company records.'),
            ('Edit any company', 'Allows editing any company record.'),
            ('Edit own companies', 'Allows editing company records owned by the user.'),
            ('Delete any company', 'Allows deleting any company record.'),
            ('Delete own companies', 'Allows deleting company records owned by the user.'),

            # Case Management 
            ('View all cases', 'Allows viewing all case records in the CRM.'),
            ('View own cases', 'Allows viewing case records owned by the user.'),
            ('Create new cases', 'Allows creating new case records.'),
            ('Edit any case', 'Allows editing any case record.'),
            ('Edit own cases', 'Allows editing case records owned by the user.'),
            ('Delete any case', 'Allows deleting any case record.'),
            ('Delete own cases', 'Allows deleting case records owned by the user.'),

            # System Settings
            ('Manage system settings', 'Allows management of global system settings.'),
        ]

        # Create/Get Permissions
        created_permissions = {}
        for perm_name, perm_description in permissions_to_create:
            perm, created = Permission.objects.get_or_create(
                name=perm_name,
                defaults={'description': perm_description}
            )
            created_permissions[perm_name] = perm
            if created:
                print(f"  Created Permission: {perm_name}")

        # Define the mapping of permissions to roles 

        # Admin Role: All permissions
        admin_perms = [
            'View all users', 'Create new user', 'Edit user','Delete user',
            'View roles and their permissions','Create new role', 'Edit role','Delete role',
            'View all permissions', 'Create new permission', 'Edit permission', 'Delete permission',
            'View all contacts', 'Create new contacts', 'Edit any contact', 'Delete any contact',
            'View all leads', 'Create new leads', 'Edit any lead', 'Delete any lead',
            'View all opportunities', 'Create new opportunities', 'Edit any opportunity', 'Delete any opportunity',
            'View all accounts', 'Create new accounts', 'Edit any account', 'Delete any account',
            'View all companies', 'Create new companies', 'Edit any company', 'Delete any company',
            'View all cases', 'Create new cases', 'Edit any case', 'Delete any case',
            'Manage system settings',
        ]

        # Sales Manager Role: CRUD (except user management)
        sales_manager_perms = [
            'View all contacts', 'Create new contacts', 'Edit any contact', 'Delete any contact',
            'View all leads', 'Create new leads', 'Edit any lead', 'Delete any lead',
            'View all opportunities', 'Create new opportunities', 'Edit any opportunity', 'Delete any opportunity',
            'View all accounts', 'Create new accounts', 'Edit any account', 'Delete any account',
            'View all companies', 'Create new companies', 'Edit any company', 'Delete any company',
            'View all cases', 'Create new cases', 'Edit any case', 'Delete any case', 
        ]

        # Sales Rep Role: CRUD on own work
        sales_rep_perms = [
            'View own contacts', 'Create new contacts', 'Edit own contacts', 'Delete own contacts',
            'View own leads', 'Create new leads', 'Edit own leads', 'Delete own leads',
            'View own opportunities', 'Create new opportunities', 'Edit own opportunities', 'Delete own opportunities',
            'View own accounts', 'Create new accounts', 'Edit own accounts', 'Delete own accounts',
            'View own companies', 'Create new companies', 'Edit own companies', 'Delete own companies',
            'View own cases', 'Create new cases', 'Edit own cases', 'Delete own cases',
        ]

        # Generic Employee Role: Read basic data (contacts)
        generic_employee_perms = [
            'View all contacts',
        ]

        # Map permissions to roles in the RolePermission table
        role_permission_mappings = {
            'ADMIN': admin_perms,
            'Sales Manager': sales_manager_perms,
            'Sales Representative': sales_rep_perms,
            'Generic Employee': generic_employee_perms,
        }

        for role_name, perms_names in role_permission_mappings.items():
            role_obj = created_roles.get(role_name)
            if role_obj:
                for perm_name in perms_names:
                    perm_obj = created_permissions.get(perm_name)
                    if perm_obj:
                        _, created = RolePermission.objects.get_or_create(
                            role=role_obj,
                            permission=perm_obj
                        )
                        if created:
                            print(f"  Mapped {role_name} to '{perm_name}'")
                    else:
                        print(f"  Warning: Permission '{perm_name}' not found for role '{role_name}'.")
            else:
                print(f"  Warning: Role '{role_name}' not found for mapping permissions.")

        print("RBAC data seeding completed.")