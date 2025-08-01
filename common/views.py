import json
import secrets
# from multiprocessing import context
from datetime import datetime
from role_permission_control.models import Role

import requests
from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.hashers import make_password
from rest_framework_simplejwt.tokens import RefreshToken
from django.conf import settings
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.utils.translation import gettext as _
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status, serializers
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Account, Contact, Tags
from accounts.serializer import AccountSerializer
from cases.models import Case
from cases.serializer import CaseSerializer

from common import swagger_params1
from common.models import APISettings, Document, Org, Profile, User

# from common.serializer import *
from common.serializer import (
    APISettingsListSerializer,
    APISettingsSerializer,
    APISettingsSwaggerSerializer,
    ActivateUserSwaggerSerializer,
    AdminCreateSwaggerSerializer,
    BillingAddressSerializer,
    CommentSerializer,
    CreateProfileSerializer,
    CreateUserSerializer,
    CustomLoginSerializer,
    DocumentCreateSerializer,
    DocumentCreateSwaggerSerializer,
    DocumentEditSwaggerSerializer,
    DocumentSerializer,
    GoogleAuthConfigSerializer,
    OrgProfileCreateSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    ProfileSerializer,
    RoleSerializer,
    ShowOrganizationListSerializer,
    SocialLoginSerializer,
    UserCreateSwaggerSerializer,
    UserUpdateStatusSwaggerSerializer,
)
from common.tasks import (
    send_email_to_new_user,
    send_email_to_reset_password,
)
from common.token_generator import account_activation_token

from contacts.serializer import ContactSerializer
from leads.models import Lead
from leads.serializer import LeadSerializer
from opportunity.models import Opportunity
from opportunity.serializer import OpportunitySerializer
from role_permission_control.serializer import RoleWithPermissionsSerializer
from teams.models import Teams
from teams.serializer import TeamsSerializer

from common.models import GoogleAuthConfig

import uuid
import os


class GetTeamsAndUsersView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(tags=["users"], parameters=swagger_params1.organization_params)
    def get(self, request, *args, **kwargs):
        data = {}
        teams = Teams.objects.filter(org=request.profile.org).order_by("-id")
        teams_data = TeamsSerializer(teams, many=True).data
        profiles = Profile.objects.filter(
            is_active=True, org=request.profile.org
        ).order_by("user__email")
        profiles_data = ProfileSerializer(profiles, many=True).data
        data["teams"] = teams_data
        data["profiles"] = profiles_data
        return Response(data)


class AdminSignupView(APIView):
    @extend_schema(request=AdminCreateSwaggerSerializer)
    def post(self, request, format=None):
        if User.objects.exists():
            return Response(
                {"error": "Admin sign up not allowed."},
                status=status.HTTP_403_FORBIDDEN,
            )
        else:
            params = request.data
            if params:
                user_serializer = CreateUserSerializer(data=params)
                data = {}
                if not user_serializer.is_valid():
                    data["user_errors"] = dict(user_serializer.errors)
                if data:
                    return Response(
                        {"error": True, "errors": data},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                admin = user_serializer.save(is_active=True)
                admin.set_password(params.get("password"))
                admin.save()

                return Response(
                    {"error": False, "message": "User Created Successfully"},
                    status=status.HTTP_201_CREATED,
                )


class UsersListView(APIView, LimitOffsetPagination):
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        parameters=swagger_params1.organization_params,
        request=UserCreateSwaggerSerializer,
    )
    def post(self, request, format=None):
        print(request.profile.role.name, request.user.is_superuser)
        # if self.request.profile.role.name != "ADMIN" and not self.request.user.is_superuser:
        if not self.request.profile.role.has_permission("Create new user"):
            return Response(
                {"error": True, "errors": "Permission Denied"},
                status=status.HTTP_403_FORBIDDEN,
            )
        else:
            params = request.data
            if params:
                user_serializer = CreateUserSerializer(
                    data=params, org=request.profile.org
                )
                address_serializer = BillingAddressSerializer(data=params)
                profile_serializer = CreateProfileSerializer(data=params)
                data = {}
                if not user_serializer.is_valid():
                    data["user_errors"] = dict(user_serializer.errors)
                if not profile_serializer.is_valid():
                    data["profile_errors"] = profile_serializer.errors
                if not address_serializer.is_valid():
                    data["address_errors"] = (address_serializer.errors,)
                if data:
                    return Response(
                        {"error": True, "errors": data},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if address_serializer.is_valid():
                    address_obj = address_serializer.save()
                    user = user_serializer.save(
                        is_active=False,
                    )
                    user.email = user.email
                    user.username = user.username
                    user.set_password(params.get("password"))
                    user.save()

                    user_role = Role.objects.get(name=params.get("role"))
                    if not user_role:
                        return Response(
                            {"error": True, "errors": "Role is not defined"},
                            status=status.HTTP_400_BAD_REQUEST,
                        )

                    profile = Profile.objects.create(
                        user=user,
                        date_of_joining=timezone.now(),
                        role=user_role,
                        address=address_obj,
                        org=request.profile.org,
                        phone=params.get("phone"),
                        alternate_phone=params.get("alternate_phone"),
                    )
                    send_email_to_new_user(user.id)
                    # send_email_to_new_user.delay(
                    #     profile.id,
                    #     request.profile.org.id,
                    # )
                    return Response(
                        {"error": False, "message": "User Created Successfully"},
                        status=status.HTTP_201_CREATED,
                    )

    @extend_schema(parameters=swagger_params1.user_list_params)
    def get(self, request, format=None):
        # if self.request.profile.role.name != "ADMIN" and not self.request.user.is_superuser:
        if not self.request.profile.role.has_permission("View all users"):
            return Response(
                {"error": True, "errors": "Permission Denied"},
                status=status.HTTP_403_FORBIDDEN,
            )
        queryset = Profile.objects.filter(org=request.profile.org).order_by("-id")
        params = request.query_params
        if params:
            if params.get("email"):
                queryset = queryset.filter(user__email__icontains=params.get("email"))
            if params.get("role"):
                queryset = queryset.filter(role__name=params.get("role"))
            if params.get("status"):
                queryset = queryset.filter(is_active=params.get("status"))

        context = {}
        queryset_active_users = queryset.filter(is_active=True)
        results_active_users = self.paginate_queryset(
            queryset_active_users.distinct(), self.request, view=self
        )
        active_users = ProfileSerializer(results_active_users, many=True).data
        if results_active_users:
            offset = queryset_active_users.filter(
                id__gte=results_active_users[-1].id
            ).count()
            if offset == queryset_active_users.count():
                offset = None
        else:
            offset = 0
        context["active_users"] = {
            "active_users_count": self.count,
            "active_users": active_users,
            "offset": offset,
        }

        queryset_inactive_users = queryset.filter(is_active=False)
        results_inactive_users = self.paginate_queryset(
            queryset_inactive_users.distinct(), self.request, view=self
        )
        inactive_users = ProfileSerializer(results_inactive_users, many=True).data
        if results_inactive_users:
            offset = queryset_inactive_users.filter(
                id__gte=results_inactive_users[-1].id
            ).count()
            if offset == queryset_inactive_users.count():
                offset = None
        else:
            offset = 0
        context["inactive_users"] = {
            "inactive_users_count": self.count,
            "inactive_users": inactive_users,
            "offset": offset,
        }

        context["admin_email"] = settings.ADMIN_EMAIL
        # context["roles"] = ROLES
        context["roles"] = RoleSerializer(Role.objects.all(), many=True).data
        context["status"] = [("True", "Active"), ("False", "In Active")]
        return Response(context)


class UserDetailView(APIView):
    permission_classes = (IsAuthenticated,)

    def get_object(self, pk):
        profile = get_object_or_404(Profile, pk=pk)
        return profile

    @extend_schema(tags=["users"], parameters=swagger_params1.organization_params)
    def get(self, request, pk, format=None):
        profile_obj = self.get_object(pk)
        if (
            not self.request.profile.role.has_permission("View user")
            and self.request.profile.id != profile_obj.id
        ):
            return Response(
                {"error": True, "errors": "Permission Denied"},
                status=status.HTTP_403_FORBIDDEN,
            )
        if profile_obj.org != request.profile.org:
            return Response(
                {"error": True, "errors": "User company doesnot match with header...."},
                status=status.HTTP_403_FORBIDDEN,
            )
        assigned_data = Profile.objects.filter(
            org=request.profile.org, is_active=True
        ).values("id", "user__email")
        context = {}
        context["profile_obj"] = ProfileSerializer(profile_obj).data

        # upload_path = os.path.join(
        #     settings.MEDIA_URL,
        #     "uploads",
        #     "profile_pics",
        #     context["profile_obj"]["user_details"]["profile_pic"],
        # )
        profile_pic = context["profile_obj"]["user_details"].get("profile_pic")

        if profile_pic:
            upload_path = os.path.join(
                settings.MEDIA_URL,
                "uploads",
                "profile_pics",
                profile_pic,
            )
        else:
            upload_path = None

        context["profile_obj"]["user_details"]["profile_pic"] = upload_path

        opportunity_list = Opportunity.objects.filter(assigned_to=profile_obj)
        context["opportunity_list"] = OpportunitySerializer(
            opportunity_list, many=True
        ).data
        contacts = Contact.objects.filter(assigned_to=profile_obj)
        context["contacts"] = ContactSerializer(contacts, many=True).data
        cases = Case.objects.filter(assigned_to=profile_obj)
        context["cases"] = CaseSerializer(cases, many=True).data
        context["assigned_data"] = assigned_data
        comments = profile_obj.user_comments.all()
        context["comments"] = CommentSerializer(comments, many=True).data
        # context["countries"] = COUNTRIES
        return Response(
            {"error": False, "data": context},
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        tags=["users"],
        parameters=swagger_params1.organization_params,
        request=UserCreateSwaggerSerializer,
    )
    def put(self, request, pk, format=None):
        profile_pic_file = request.FILES.get("profile_pic")
        params = request.data

        filename = None
        full_path = None

        if profile_pic_file:
            filename = f"profile_{uuid.uuid4().hex}_{profile_pic_file.name}"
            upload_path = os.path.join("uploads", "profile_pics", filename)
            full_path = os.path.join(settings.MEDIA_ROOT, upload_path)

            os.makedirs(os.path.dirname(full_path), exist_ok=True)

            with open(full_path, "wb+") as destination:
                for chunk in profile_pic_file.chunks():
                    destination.write(chunk)

            # Save the relative path to use later
            params["profile_pic"] = filename

        profile = self.get_object(pk)
        address_obj = profile.address

        if (
            not self.request.profile.role.has_permission("Edit user")
            and self.request.profile.id != profile.id
        ):
            return Response(
                {"error": True, "errors": "Permission Denied"},
                status=status.HTTP_403_FORBIDDEN,
            )

        if profile.org != request.profile.org:
            return Response(
                {"error": True, "errors": "User company doesnot match with header...."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = CreateUserSerializer(
            data=params, instance=profile.user, org=request.profile.org
        )
        address_serializer = BillingAddressSerializer(data=params, instance=address_obj)
        profile_serializer = CreateProfileSerializer(data=params, instance=profile)

        data = {}
        if not serializer.is_valid():
            data["contact_errors"] = serializer.errors
        if not address_serializer.is_valid():
            data["address_errors"] = address_serializer.errors
        if not profile_serializer.is_valid():
            data["profile_errors"] = profile_serializer.errors

        if data:
            data["error"] = True
            return Response(data, status=status.HTTP_400_BAD_REQUEST)

        if address_serializer.is_valid():
            address_obj = address_serializer.save()
            user = serializer.save()

            if filename:
                user.profile_pic = filename

            user.email = user.email
            user.username = user.username
            password = params.get("password")
            if password:
                user.set_password(password)
            user.save()

        if profile_serializer.is_valid():
            profile = profile_serializer.save()
            return Response(
                {"error": False, "message": "User Updated Successfully"},
                status=status.HTTP_200_OK,
            )

        return Response(
            {"error": True, "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )
    
    @extend_schema(tags=["users"], parameters=swagger_params1.organization_params)
    def delete(self, request, pk, format=None):
        # if self.request.profile.role.name != "ADMIN" and not self.request.profile.is_admin:
        if not self.request.profile.role.has_permission("Delete user"):
            return Response(
                {"error": True, "errors": "Permission Denied"},
                status=status.HTTP_403_FORBIDDEN,
            )
        self.object = self.get_object(pk)
        if self.object.id == request.profile.id:
            return Response(
                {"error": True, "errors": "Permission Denied"},
                status=status.HTTP_403_FORBIDDEN,
            )
        deleted_by = self.request.profile.user.email

        user = self.object.user
        address = self.object.address
        self.object.delete()
        if user:
            user.delete()

        if address:
            address.delete()
        return Response({"status": "success"}, status=status.HTTP_200_OK)


# check_header not working
class ApiHomeView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(parameters=swagger_params1.organization_params)
    def get(self, request, format=None):
        accounts = Account.objects.filter(status="open", org=request.profile.org)
        contacts = Contact.objects.filter(org=request.profile.org)
        leads = Lead.objects.filter(org=request.profile.org).exclude(
            Q(status="converted") | Q(status="closed")
        )
        opportunities = Opportunity.objects.filter(org=request.profile.org)

        if (
            self.request.profile.role.name != "ADMIN"
            and not self.request.user.is_superuser
        ):
            accounts = accounts.filter(
                Q(assigned_to=self.request.profile)
                | Q(created_by=self.request.profile.user)
            )
            contacts = contacts.filter(
                Q(assigned_to__id__in=self.request.profile)
                | Q(created_by=self.request.profile.user)
            )
            leads = leads.filter(
                Q(assigned_to__id__in=self.request.profile)
                | Q(created_by=self.request.profile.user)
            ).exclude(status="closed")
            opportunities = opportunities.filter(
                Q(assigned_to__id__in=self.request.profile)
                | Q(created_by=self.request.profile.user)
            )
        context = {}
        context["accounts_count"] = accounts.count()
        context["contacts_count"] = contacts.count()
        context["leads_count"] = leads.count()
        context["opportunities_count"] = opportunities.count()
        context["accounts"] = AccountSerializer(accounts, many=True).data
        context["contacts"] = ContactSerializer(contacts, many=True).data
        context["leads"] = LeadSerializer(leads, many=True).data
        context["opportunities"] = OpportunitySerializer(opportunities, many=True).data
        return Response(context, status=status.HTTP_200_OK)


class OrgProfileCreateView(APIView):
    # authentication_classes = (CustomDualAuthentication,)
    permission_classes = (IsAuthenticated,)

    model1 = Org
    model2 = Profile
    serializer_class = OrgProfileCreateSerializer
    profile_serializer = CreateProfileSerializer

    @extend_schema(
        description="Organization and profile Creation api",
        request=OrgProfileCreateSerializer,
    )
    def post(self, request, format=None):
        data = request.data
        data["api_key"] = secrets.token_hex(16)
        serializer = self.serializer_class(data=data)
        if serializer.is_valid():
            org_obj = serializer.save()

            # now creating the profile
            admin_role = Role.objects.get(name="ADMIN")
            profile_obj = self.model2.objects.create(
                user=request.user, org=org_obj, role=admin_role
            )
            # now the current user is the admin of the newly created organisation
            profile_obj.is_organization_admin = True
            # profile_obj.role = "ADMIN"
            profile_obj.save()

            return Response(
                {
                    "error": False,
                    "message": "New Org is Created.",
                    "org": self.serializer_class(org_obj).data,
                    "status": status.HTTP_201_CREATED,
                }
            )
        else:
            return Response(
                {
                    "error": True,
                    "errors": serializer.errors,
                    "status": status.HTTP_400_BAD_REQUEST,
                }
            )

    @extend_schema(
        description="Just Pass the token, will return ORG list, associated with user"
    )
    def get(self, request, format=None):
        """
        here we are passing profile list of the user, where org details also included
        """
        profile_list = Profile.objects.filter(user=request.user)
        serializer = ShowOrganizationListSerializer(profile_list, many=True)
        return Response(
            {
                "error": False,
                "status": status.HTTP_200_OK,
                "profile_org_list": serializer.data,
            }
        )


class ProfileView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(parameters=swagger_params1.organization_params)
    def get(self, request, format=None):
        # profile=Profile.objects.get(user=request.user)
        context = {}
        context["user_obj"] = ProfileSerializer(self.request.profile).data
        return Response(context, status=status.HTTP_200_OK)


class DocumentListView(APIView, LimitOffsetPagination):
    # authentication_classes = (CustomDualAuthentication,)
    permission_classes = (IsAuthenticated,)
    model = Document

    def get_context_data(self, **kwargs):
        params = self.request.query_params
        queryset = self.model.objects.filter(org=self.request.profile.org).order_by(
            "-id"
        )
        if self.request.user.is_superuser or self.request.profile.role.name == "ADMIN":
            queryset = queryset
        else:
            if self.request.profile.documents():
                doc_ids = self.request.profile.documents().values_list("id", flat=True)
                shared_ids = queryset.filter(
                    Q(status="active") & Q(shared_to__id__in=[self.request.profile.id])
                ).values_list("id", flat=True)
                queryset = queryset.filter(Q(id__in=doc_ids) | Q(id__in=shared_ids))
            else:
                queryset = queryset.filter(
                    Q(status="active") & Q(shared_to__id__in=[self.request.profile.id])
                )

        request_post = params
        if request_post:
            if request_post.get("title"):
                queryset = queryset.filter(title__icontains=request_post.get("title"))
            if request_post.get("status"):
                queryset = queryset.filter(status=request_post.get("status"))

            if request_post.get("shared_to"):
                queryset = queryset.filter(
                    shared_to__id__in=json.loads(request_post.get("shared_to"))
                )

        context = {}
        profile_list = Profile.objects.filter(
            is_active=True, org=self.request.profile.org
        )
        if self.request.profile.role.name == "ADMIN" or self.request.profile.is_admin:
            profiles = profile_list.order_by("user__email")
        else:
            profiles = profile_list.filter(role__name="ADMIN").order_by("user__email")
        search = False
        if (
            params.get("document_file")
            or params.get("status")
            or params.get("shared_to")
        ):
            search = True
        context["search"] = search

        queryset_documents_active = queryset.filter(status="active")
        results_documents_active = self.paginate_queryset(
            queryset_documents_active.distinct(), self.request, view=self
        )
        documents_active = DocumentSerializer(results_documents_active, many=True).data
        if results_documents_active:
            offset = queryset_documents_active.filter(
                id__gte=results_documents_active[-1].id
            ).count()
            if offset == queryset_documents_active.count():
                offset = None
        else:
            offset = 0
        context["documents_active"] = {
            "documents_active_count": self.count,
            "documents_active": documents_active,
            "offset": offset,
        }

        queryset_documents_inactive = queryset.filter(status="inactive")
        results_documents_inactive = self.paginate_queryset(
            queryset_documents_inactive.distinct(), self.request, view=self
        )
        documents_inactive = DocumentSerializer(
            results_documents_inactive, many=True
        ).data
        if results_documents_inactive:
            offset = queryset_documents_inactive.filter(
                id__gte=results_documents_active[-1].id
            ).count()
            if offset == queryset_documents_inactive.count():
                offset = None
        else:
            offset = 0
        context["documents_inactive"] = {
            "documents_inactive_count": self.count,
            "documents_inactive": documents_inactive,
            "offset": offset,
        }

        context["users"] = ProfileSerializer(profiles, many=True).data
        context["status_choices"] = Document.DOCUMENT_STATUS_CHOICE
        return context

    @extend_schema(tags=["documents"], parameters=swagger_params1.document_get_params)
    def get(self, request, *args, **kwargs):
        context = self.get_context_data(**kwargs)
        return Response(context)

    @extend_schema(
        tags=["documents"],
        parameters=swagger_params1.organization_params,
        request=DocumentCreateSwaggerSerializer,
    )
    def post(self, request, *args, **kwargs):
        params = request.data
        serializer = DocumentCreateSerializer(data=params, request_obj=request)
        if serializer.is_valid():
            doc = serializer.save(
                created_by=request.profile.user,
                org=request.profile.org,
                document_file=request.FILES.get("document_file"),
            )
            if params.get("shared_to"):
                assinged_to_list = params.get("shared_to")
                profiles = Profile.objects.filter(
                    id__in=assinged_to_list, org=request.profile.org, is_active=True
                )
                if profiles:
                    doc.shared_to.add(*profiles)
            if params.get("teams"):
                teams_list = params.get("teams")
                teams = Teams.objects.filter(id__in=teams_list, org=request.profile.org)
                if teams:
                    doc.teams.add(*teams)

            return Response(
                {"error": False, "message": "Document Created Successfully"},
                status=status.HTTP_201_CREATED,
            )
        return Response(
            {"error": True, "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )


class DocumentDetailView(APIView):
    # authentication_classes = (CustomDualAuthentication,)
    permission_classes = (IsAuthenticated,)

    def get_object(self, pk):
        return Document.objects.filter(id=pk).first()

    @extend_schema(tags=["documents"], parameters=swagger_params1.organization_params)
    def get(self, request, pk, format=None):
        self.object = self.get_object(pk)
        if not self.object:
            return Response(
                {"error": True, "errors": "Document does not exist"},
                status=status.HTTP_403_FORBIDDEN,
            )
        if self.object.org != self.request.profile.org:
            return Response(
                {"error": True, "errors": "User company doesnot match with header...."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if (
            self.request.profile.role.name != "ADMIN"
            and not self.request.user.is_superuser
        ):
            if not (
                (self.request.profile == self.object.created_by)
                or (self.request.profile in self.object.shared_to.all())
            ):
                return Response(
                    {
                        "error": True,
                        "errors": "You do not have Permission to perform this action",
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
        profile_list = Profile.objects.filter(org=self.request.profile.org)
        if request.profile.role.name == "ADMIN" or request.user.is_superuser:
            profiles = profile_list.order_by("user__email")
        else:
            profiles = profile_list.filter(role__name="ADMIN").order_by("user__email")
        context = {}
        context.update(
            {
                "doc_obj": DocumentSerializer(self.object).data,
                "file_type_code": self.object.file_type()[1],
                "users": ProfileSerializer(profiles, many=True).data,
            }
        )
        return Response(context, status=status.HTTP_200_OK)

    @extend_schema(tags=["documents"], parameters=swagger_params1.organization_params)
    def delete(self, request, pk, format=None):
        document = self.get_object(pk)
        if not document:
            return Response(
                {"error": True, "errors": "Documdnt does not exist"},
                status=status.HTTP_403_FORBIDDEN,
            )
        if document.org != self.request.profile.org:
            return Response(
                {"error": True, "errors": "User company doesnot match with header...."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if (
            self.request.profile.role.name != "ADMIN"
            and not self.request.user.is_superuser
        ):
            if (
                self.request.profile != document.created_by
            ):  # or (self.request.profile not in document.shared_to.all()):
                return Response(
                    {
                        "error": True,
                        "errors": "You do not have Permission to perform this action",
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
        document.delete()
        return Response(
            {"error": False, "message": "Document deleted Successfully"},
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        tags=["documents"],
        parameters=swagger_params1.organization_params,
        request=DocumentEditSwaggerSerializer,
    )
    def put(self, request, pk, format=None):
        self.object = self.get_object(pk)
        params = request.data
        if not self.object:
            return Response(
                {"error": True, "errors": "Document does not exist"},
                status=status.HTTP_403_FORBIDDEN,
            )
        if self.object.org != self.request.profile.org:
            return Response(
                {"error": True, "errors": "User company doesnot match with header...."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if (
            self.request.profile.role.name != "ADMIN"
            and not self.request.user.is_superuser
        ):
            if not (
                (self.request.profile == self.object.created_by)
                or (self.request.profile in self.object.shared_to.all())
            ):
                return Response(
                    {
                        "error": True,
                        "errors": "You do not have Permission to perform this action",
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
        serializer = DocumentCreateSerializer(
            data=params, instance=self.object, request_obj=request
        )
        if serializer.is_valid():
            doc = serializer.save(
                document_file=request.FILES.get("document_file"),
                status=params.get("status"),
                org=request.profile.org,
            )
            doc.shared_to.clear()
            if params.get("shared_to"):
                assinged_to_list = params.get("shared_to")
                profiles = Profile.objects.filter(
                    id__in=assinged_to_list, org=request.profile.org, is_active=True
                )
                if profiles:
                    doc.shared_to.add(*profiles)

            doc.teams.clear()
            if params.get("teams"):
                teams_list = params.get("teams")
                teams = Teams.objects.filter(id__in=teams_list, org=request.profile.org)
                if teams:
                    doc.teams.add(*teams)
            return Response(
                {"error": False, "message": "Document Updated Successfully"},
                status=status.HTTP_200_OK,
            )
        return Response(
            {"error": True, "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )


class UserStatusView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        description="User Status View",
        parameters=swagger_params1.organization_params,
        request=UserUpdateStatusSwaggerSerializer,
    )
    def post(self, request, pk, format=None):
        if (
            self.request.profile.role.name != "ADMIN"
            and not self.request.user.is_superuser
        ):
            return Response(
                {
                    "error": True,
                    "errors": "You do not have permission to perform this action",
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        params = request.data
        profiles = Profile.objects.filter(org=request.profile.org)
        profile = profiles.get(id=pk)

        if params.get("status"):
            user_status = params.get("status")
            if user_status == "Active":
                profile.is_active = True
            elif user_status == "Inactive":
                profile.is_active = False
            else:
                return Response(
                    {"error": True, "errors": "Please enter Valid Status for user"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            profile.save()

        context = {}
        active_profiles = profiles.filter(is_active=True)
        inactive_profiles = profiles.filter(is_active=False)
        context["active_profiles"] = ProfileSerializer(active_profiles, many=True).data
        context["inactive_profiles"] = ProfileSerializer(
            inactive_profiles, many=True
        ).data
        return Response(context)


class DomainList(APIView):
    model = APISettings
    permission_classes = (IsAuthenticated,)

    @extend_schema(tags=["Settings"], parameters=swagger_params1.organization_params)
    def get(self, request, *args, **kwargs):
        api_settings = APISettings.objects.filter(org=request.profile.org)
        users = Profile.objects.filter(
            is_active=True, org=request.profile.org
        ).order_by("user__email")
        return Response(
            {
                "error": False,
                "api_settings": APISettingsListSerializer(api_settings, many=True).data,
                "users": ProfileSerializer(users, many=True).data,
            },
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        tags=["Settings"],
        parameters=swagger_params1.organization_params,
        request=APISettingsSwaggerSerializer,
    )
    def post(self, request, *args, **kwargs):
        params = request.data
        assign_to_list = []
        if params.get("lead_assigned_to"):
            assign_to_list = params.get("lead_assigned_to")
        serializer = APISettingsSerializer(data=params)
        if serializer.is_valid():
            settings_obj = serializer.save(
                created_by=request.profile.user, org=request.profile.org
            )
            if params.get("tags"):
                tags = params.get("tags")
                for tag in tags:
                    tag_obj = Tags.objects.filter(name=tag).first()
                    if not tag_obj:
                        tag_obj = Tags.objects.create(name=tag)
                    settings_obj.tags.add(tag_obj)
            if assign_to_list:
                settings_obj.lead_assigned_to.add(*assign_to_list)
            return Response(
                {"error": False, "message": "API key added sucessfully"},
                status=status.HTTP_201_CREATED,
            )
        return Response(
            {"error": True, "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )


class DomainDetailView(APIView):
    model = APISettings
    # authentication_classes = (CustomDualAuthentication,)
    permission_classes = (IsAuthenticated,)

    @extend_schema(tags=["Settings"], parameters=swagger_params1.organization_params)
    def get(self, request, pk, format=None):
        api_setting = self.get_object(pk)
        return Response(
            {"error": False, "domain": APISettingsListSerializer(api_setting).data},
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        tags=["Settings"],
        parameters=swagger_params1.organization_params,
        request=APISettingsSwaggerSerializer,
    )
    def put(self, request, pk, **kwargs):
        api_setting = self.get_object(pk)
        params = request.data
        assign_to_list = []
        if params.get("lead_assigned_to"):
            assign_to_list = params.get("lead_assigned_to")
        serializer = APISettingsSerializer(data=params, instance=api_setting)
        if serializer.is_valid():
            api_setting = serializer.save()
            api_setting.tags.clear()
            api_setting.lead_assigned_to.clear()
            if params.get("tags"):
                tags = params.get("tags")
                for tag in tags:
                    tag_obj = Tags.objects.filter(name=tag).first()
                    if not tag_obj:
                        tag_obj = Tags.objects.create(name=tag)
                    api_setting.tags.add(tag_obj)
            if assign_to_list:
                api_setting.lead_assigned_to.add(*assign_to_list)
            return Response(
                {"error": False, "message": "API setting Updated sucessfully"},
                status=status.HTTP_200_OK,
            )
        return Response(
            {"error": True, "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    @extend_schema(tags=["Settings"], parameters=swagger_params1.organization_params)
    def delete(self, request, pk, **kwargs):
        api_setting = self.get_object(pk)
        if api_setting:
            api_setting.delete()
        return Response(
            {"error": False, "message": "API setting deleted sucessfully"},
            status=status.HTTP_200_OK,
        )


class GoogleLoginView(APIView):
    """
    Check for authentication with google
    post:
        Returns token of logged In user
    """

    @extend_schema(
        description="Login through Google",
        request=SocialLoginSerializer,
    )
    def post(self, request):
        payload = {"access_token": request.data.get("token")}  # validate the token
        r = requests.get(
            "https://www.googleapis.com/oauth2/v2/userinfo", params=payload
        )
        data = json.loads(r.text)
        print(data)
        if "error" in data:
            content = {
                "message": "wrong google token / this google token is already expired."
            }
            return Response(content)
        # create user if not exist
        try:
            user = User.objects.get(email=data["email"])
        except User.DoesNotExist:
            user = User()
            user.email = data["email"]
            user.username = f"user_{user.id.hex[:8]}"
            user.profile_pic = data["picture"]
            # provider random default password
            user.password = make_password(BaseUserManager().make_random_password())
            user.email = data["email"]
            user.save()
        token = RefreshToken.for_user(
            user
        )  # generate token without username & password
        response = {}
        response["username"] = user.email
        response["access_token"] = str(token.access_token)
        response["refresh_token"] = str(token)
        response["user_id"] = user.id
        return Response(response)


class CustomLoginView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        description="Login with email and password and receive user details if it exists.",
        parameters=[
            OpenApiParameter(
                name="email",
                type=str,
                location=OpenApiParameter.QUERY,
                required=True,
                description="User email address",
            ),
        ],
        responses={200: CustomLoginSerializer, 400: None, 404: None},
    )
    def get(self, request):
        serializer = CustomLoginSerializer(data=request.query_params)
        if serializer.is_valid():
            # user_obj = serializer.validated_data['user']
            try:
                userProfile = Profile.objects.get(
                    user__email=request.query_params.get("email")
                )
            except User.DoesNotExist:
                raise serializers.ValidationError("Incorrect email or password.")

            return Response(
                {
                    "username": userProfile.user.username,
                    "email": userProfile.user.email,
                    "profile_pic": userProfile.user.profile_pic,
                    "user_id": userProfile.user.id,
                    "role": RoleWithPermissionsSerializer(userProfile.role).data,
                },
                status=status.HTTP_200_OK,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class GoogleAuthConfigView(APIView):
    def get(self, request):
        config, _ = GoogleAuthConfig.objects.get_or_create(id=1)
        return Response({"google_enabled": config.google_enabled})

    @extend_schema(
        request=GoogleAuthConfigSerializer, responses={200: GoogleAuthConfigSerializer}
    )
    def put(self, request):
        config, _ = GoogleAuthConfig.objects.get_or_create(id=1)
        new_value = request.data.get("google_enabled")
        if isinstance(new_value, bool):
            config.google_enabled = new_value
            config.save()
            return Response({"google_enabled": config.google_enabled}, status=200)
        return Response({"error": "Invalid value"}, status=400)


class UserActivate(APIView):
    @extend_schema(request=ActivateUserSwaggerSerializer)
    def post(self, request, format=None):
        uid = request.data.get("uid")
        token = request.data.get("token")
        old_password = request.data.get("old_password")
        new_password = request.data.get("new_password")

        if not all([uid, token, old_password, new_password]):
            return Response({"detail": "Missing data"}, status=400)

        uid_decoded = force_str(urlsafe_base64_decode(uid))
        user = User.objects.get(pk=uid_decoded)

        if not user:
            return Response({"detail": "Invalid Uid"}, status=400)

        activation_str = user.activation_key
        if not activation_str:
            return Response({"detail": "Activation link is already used"}, status=400)

        activation_time = datetime.strptime(activation_str, "%Y-%m-%d-%H-%M-%S")

        if timezone.now() > timezone.make_aware(activation_time):
            return Response({"detail": "Activation link is expired"}, status=400)

        if not account_activation_token.check_token(user, token):
            return Response({"detail": "Invalid token"}, status=400)

        if not user.check_password(old_password):
            return Response({"detail": "Incorrect current password."}, status=400)

        user.set_password(new_password)
        user.is_active = True
        user.activation_key = None
        user.save()

        return Response({"detail": "Password set and account activated"}, status=200)


class PasswordResetRequestView(APIView):
    @extend_schema(request=PasswordResetRequestSerializer)
    def post(self, request):
        serializer = PasswordResetRequestSerializer(
            data=request.data, context={"request": request}
        )
        if serializer.is_valid():
            send_email_to_reset_password(request.data.get("email"))
            return Response(
                {"message": "Password reset email sent."}, status=status.HTTP_200_OK
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PasswordResetConfirmView(APIView):
    @extend_schema(request=PasswordResetConfirmSerializer)
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        if serializer.is_valid():
            user_id = urlsafe_base64_decode(request.data.get("uid")).decode()
            user = User.objects.get(pk=user_id)
            if not user:
                return Response({"error": "Invalid value"}, status=400)

            activation_str = user.activation_key
            if not activation_str:
                return Response(
                    {"detail": "password reset link is already used"}, status=400
                )
            activation_time = datetime.strptime(activation_str, "%Y-%m-%d-%H-%M-%S")
            activation_time_aware = timezone.make_aware(activation_time, timezone.utc)
            if timezone.now() > activation_time_aware:
                print(timezone.now())
                print(user.activation_key)
                return Response(
                    {"detail": "password reset link is expired"}, status=400
                )

            if not account_activation_token.check_token(
                user, request.data.get("token")
            ):
                raise serializers.ValidationError("Invalid token.")

            user.set_password(request.data.get("new_password"))
            user.activation_key = None
            user.save()
            return Response(
                {"message": "Password has been reset."}, status=status.HTTP_200_OK
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
