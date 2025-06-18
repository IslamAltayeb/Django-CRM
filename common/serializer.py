import re
from datetime import datetime

from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.hashers import check_password
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.core.mail import send_mail
from django.conf import settings
from rest_framework import serializers
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken
from rest_framework.response import Response
from common.utils import COUNTRIES
from common.tasks import send_email_to_reset_password
from django.utils import timezone
from common.token_generator import account_activation_token
from role_permission_control.models import Role
from common.models import (
    Address,
    APISettings,
    Attachments,
    Comment,
    Document,
    Org,
    Profile,
    User,
)


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Org
        fields = ("id", "name","api_key")


class SocialLoginSerializer(serializers.Serializer):
    token = serializers.CharField()


class CommentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Comment
        fields = (
            "id",
            "comment",
            "commented_on",
            "commented_by",
            "account",
            "lead",
            "opportunity",
            "contact",
            "case",
            "task",
            "invoice",
            "event",
            "profile",
        )


class LeadCommentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Comment
        fields = (
            "id",
            "comment",
            "commented_on",
            "commented_by",
            "lead",
        )



class OrgProfileCreateSerializer(serializers.ModelSerializer):
    """
    It is for creating organization
    """

    name = serializers.CharField(max_length=255)

    class Meta:
        model = Org
        fields = ["name"]
        extra_kwargs = {
            "name": {"required": True}
        }

    def validate_name(self, name):
        if bool(re.search(r"[~\!_.@#\$%\^&\*\ \(\)\+{}\":;'/\[\]]", name)):
            raise serializers.ValidationError(
                "organization name should not contain any special characters"
            )
        if Org.objects.filter(name=name).exists():
            raise serializers.ValidationError(
                "Organization already exists with this name"
            )
        return name


class ShowOrganizationListSerializer(serializers.ModelSerializer):
    """
    we are using it for show orjanization list
    """

    org = OrganizationSerializer()

    class Meta:
        model = Profile
        fields = (
            "role",
            "alternate_phone",
            "has_sales_access",
            "has_marketing_access",
            "is_organization_admin",
            "org",
        )


class BillingAddressSerializer(serializers.ModelSerializer):
    #country_display  = serializers.SerializerMethodField(read_only=True)

    #def get_country(self, obj):
    #    return obj.get_country_display()

    class Meta:
        model = Address
        fields = ("address_line", "street", "city", "state", "postcode", "country")

    def __init__(self, *args, **kwargs):
        account_view = kwargs.pop("account", False)

        super().__init__(*args, **kwargs)

        if account_view:
            self.fields["address_line"].required = True
            self.fields["street"].required = True
            self.fields["city"].required = True
            self.fields["state"].required = True
            self.fields["postcode"].required = True
            self.fields["country"].required = True


class CreateUserSerializer(serializers.ModelSerializer):

    class Meta:
        model = User
        fields = (
            "username",
            "email",
            "password",
            "profile_pic",
        )

    def __init__(self, *args, **kwargs):
        self.org = kwargs.pop("org", None)
        super().__init__(*args, **kwargs)
        self.fields["email"].required = True
        self.fields["username"].required = True
        #self.fields["password"].required = True
        # Only require password if it's a create operation
        if self.instance is None:
            self.fields["password"].required = True
        else:
            self.fields["password"].required = False
            self.fields["password"].allow_blank = True

    # def validate_email(self, email):
    #     if self.instance:
    #         if self.instance.email != email:
    #             if not Profile.objects.filter(user__email=email, org=self.org).exists():
    #                 return email
    #             raise serializers.ValidationError("Email already exists")
    #         return email
    #     if not Profile.objects.filter(user__email=email.lower(), org=self.org).exists():
    #         return email
    #     raise serializers.ValidationError("Given Email id already exists")
    
    def validate_password(self, password):
        errors = []

        if len(password) < 8:
            errors.append("Password must be at least 8 characters long.")
        if not re.search(r"[a-z]", password):
            errors.append("Password must contain at least one lowercase letter.")
        if not re.search(r"[A-Z]", password):
            errors.append("Password must contain at least one uppercase letter.")
        if not re.search(r"\d", password):
            errors.append("Password must contain at least one digit.")
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
            errors.append("Password must contain at least one special character.")

        if not errors:
            return True
        raise serializers.ValidationError(", ".join(str(item) for item in errors))

class CreateProfileSerializer(serializers.ModelSerializer):
    role = serializers.SlugRelatedField(
        slug_field='name',  
        queryset=Role.objects.all()
    )

    class Meta:
        model = Profile
        fields = (
            "role",
            "phone",
            "alternate_phone",
            "has_sales_access",
            "has_marketing_access",
            "is_organization_admin",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["alternate_phone"].required = False
        self.fields["role"].required = True
        self.fields["phone"].required = True


class UserSerializer(serializers.ModelSerializer):

    class Meta:
        model = User
        fields = ["id","username","email","profile_pic"] 


class RoleSerializer(serializers.ModelSerializer):

    class Meta:
        model = Role
        fields = ["id","name","description"] 


class ProfileSerializer(serializers.ModelSerializer):
    address = BillingAddressSerializer( read_only=True)
    user_details = UserSerializer(source="user", read_only=True)
    role_details = RoleSerializer(source="role", read_only=True)

    class Meta:
        model = Profile
        fields = (
            "id",
            "user_details",
            "role_details",
            "address",
            "has_marketing_access",
            "has_sales_access",
            "phone",
            "alternate_phone",
            "date_of_joining",
            "is_active",
        )


class AttachmentsSerializer(serializers.ModelSerializer):
    file_path = serializers.SerializerMethodField()

    def get_file_path(self, obj):
        if obj.attachment:
            return obj.attachment.url
        None

    class Meta:
        model = Attachments
        fields = ["id", "created_by", "file_name", "created_at", "file_path"]


class DocumentSerializer(serializers.ModelSerializer):
    shared_to = ProfileSerializer(read_only=True, many=True)
    teams = serializers.SerializerMethodField()
    created_by = UserSerializer()
    org = OrganizationSerializer()

    def get_teams(self, obj):
        return obj.teams.all().values()

    class Meta:
        model = Document
        fields = [
            "id",
            "title",
            "document_file",
            "status",
            "shared_to",
            "teams",
            "created_at",
            "created_by",
            "org",
        ]


class DocumentCreateSerializer(serializers.ModelSerializer):
    def __init__(self, *args, **kwargs):
        request_obj = kwargs.pop("request_obj", None)
        super().__init__(*args, **kwargs)
        self.fields["title"].required = True
        self.org = request_obj.profile.org

    def validate_title(self, title):
        if self.instance:
            if (
                Document.objects.filter(title__iexact=title, org=self.org)
                .exclude(id=self.instance.id)
                .exists()
            ):
                raise serializers.ValidationError(
                    "Document with this Title already exists"
                )
        if Document.objects.filter(title__iexact=title, org=self.org).exists():
            raise serializers.ValidationError("Document with this Title already exists")
        return title

    class Meta:
        model = Document
        fields = ["title", "document_file", "status", "org"]


def find_urls(string):
    # website_regex = "^((http|https)://)?([A-Za-z0-9.-]+\.[A-Za-z]{2,63})?$"  # (http(s)://)google.com or google.com
    # website_regex = "^https?://([A-Za-z0-9.-]+\.[A-Za-z]{2,63})?$"  # (http(s)://)google.com
    # http(s)://google.com
    website_regex = "^https?://[A-Za-z0-9.-]+\.[A-Za-z]{2,63}$"
    # http(s)://google.com:8000
    website_regex_port = "^https?://[A-Za-z0-9.-]+\.[A-Za-z]{2,63}:[0-9]{2,4}$"
    url = re.findall(website_regex, string)
    url_port = re.findall(website_regex_port, string)
    if url and url[0] != "":
        return url
    return url_port


class APISettingsSerializer(serializers.ModelSerializer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    class Meta:
        model = APISettings
        fields = ("title", "website")

    def validate_website(self, website):
        if website and not (
            website.startswith("http://") or website.startswith("https://")
        ):
            raise serializers.ValidationError("Please provide valid schema")
        if not len(find_urls(website)) > 0:
            raise serializers.ValidationError(
                "Please provide a valid URL with schema and without trailing slash - Example: http://google.com"
            )
        return website


class APISettingsListSerializer(serializers.ModelSerializer):
    created_by = UserSerializer()
    lead_assigned_to = ProfileSerializer(read_only=True, many=True)
    tags = serializers.SerializerMethodField()
    org = OrganizationSerializer()

    def get_tags(self, obj):
        return obj.tags.all().values()

    class Meta:
        model = APISettings
        fields = [
            "title",
            "apikey",
            "website",
            "created_at",
            "created_by",
            "lead_assigned_to",
            "tags",
            "org",
        ]

class APISettingsSwaggerSerializer(serializers.ModelSerializer):
    class Meta:
        model = APISettings
        fields = [
            "title",
            "website",
            "lead_assigned_to",
            "tags",
        ]


class DocumentCreateSwaggerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = [
            "title",
            "document_file",
            "teams",
            "shared_to",
        ]

class DocumentEditSwaggerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = [
            "title",
            "document_file",
            "teams",
            "shared_to",
            "status"
        ]


class UserCreateSwaggerSerializer(serializers.Serializer):
    """
    It is swagger for creating or updating user
    """
    #ROLE_CHOICES = ["ADMIN", "USER"]

    username = serializers.CharField(max_length=1000,required=True)
    email = serializers.CharField(max_length=1000,required=True)
    password = serializers.CharField(max_length=1000)
    #role = serializers.ChoiceField(choices = ROLE_CHOICES,required=True)
    role = serializers.CharField(max_length=1000,required=True)
    phone = serializers.CharField(max_length=12)
    alternate_phone = serializers.CharField(max_length=12)
    address_line = serializers.CharField(max_length=10000,required=True)
    street = serializers.CharField(max_length=1000)
    city = serializers.CharField(max_length=1000)
    state = serializers.CharField(max_length=1000)
    postcode = serializers.CharField(max_length=1000)
    country = serializers.ChoiceField(choices=COUNTRIES)

class AdminCreateSwaggerSerializer(serializers.Serializer):
    """
    It is swagger for creating or updating admin
    """

    username = serializers.CharField(max_length=1000,required=True)
    email = serializers.CharField(max_length=1000,required=True)
    password = serializers.CharField(max_length=1000)
 

class UserUpdateStatusSwaggerSerializer(serializers.Serializer):

    STATUS_CHOICES = ["Active", "Inactive"]

    status = serializers.ChoiceField(choices = STATUS_CHOICES,required=True)

# serializer for Customized_login
class CustomLoginSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    password = serializers.CharField(required=True, write_only=True)

    def validate(self, attrs):
        email = attrs.get("email")
        password = attrs.get("password")
        User = get_user_model()

        if not email or not password:
            raise serializers.ValidationError("Email and password is required.")

        try:
           user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise serializers.ValidationError("Incorrect email or password.")

        if not check_password(password, user.password):
            raise serializers.ValidationError("Incorrect email or password.")

        if not user.is_active:
            raise serializers.ValidationError("User is not active.")

        attrs['user'] = user
        return attrs
class GoogleAuthConfigSerializer(serializers.Serializer):
    google_enabled = serializers.BooleanField()
        

class ActivateUserSwaggerSerializer(serializers.Serializer):
    """
    It is swagger for activate new user and set new password
    """

    uid = serializers.CharField(max_length=1000,required=True)
    token = serializers.CharField(max_length=1000,required=True)
    old_password = serializers.CharField(max_length=1000,required=True)
    new_password = serializers.CharField(max_length=1000,required=True)

class PasswordResetRequestSerializer(serializers.Serializer):

    """
    It is a swagger for requesting a password reset.
    """

    email = serializers.EmailField()
    def validate(self, attrs):
        email = attrs.get("email")
        if not email:
            raise serializers.ValidationError("Email is required.")
        User = get_user_model()
        if not User.objects.filter(email=email).exists():
            raise serializers.ValidationError("User with this email does not exist.")
        return attrs
    # def save(self):
    #     request = self.context.get('request')
    #     email = self.validated_data['email']
    #     user = User.objects.get(email=email)
    #     uid = urlsafe_base64_encode(force_bytes(user.pk))
    #     token = default_token_generator.make_token(user)
        #reset_link = f"{request.scheme}://{request.get_host()}/reset-password-confirm/{uid}/{token}/"

        #send_email_to_reset_password(email)
    
        # send_mail(
        #     subject="Password Reset",
        #     message=f"Use the following link to reset your password: {reset_link}",
        #     from_email=settings.DEFAULT_FROM_EMAIL,
        #     recipient_list=[email]
        # )
class PasswordResetConfirmSerializer(serializers.Serializer):
    """
    It is a swagger for confirming a password reset.
    """

    uid = serializers.CharField(max_length=1000, required=True)
    token = serializers.CharField(max_length=1000, required=True)
    new_password = serializers.CharField(max_length=1000, required=True)

    def validate(self, attrs):
        uid = attrs.get("uid")
        token = attrs.get("token")
        new_password = attrs.get("new_password")

        if not uid or not token or not new_password:
            raise serializers.ValidationError("All fields are required.")
        return attrs

        # User = get_user_model()

        # try:
        #     user_id = urlsafe_base64_decode(uid).decode()
        #     self.user = User.objects.get(pk=user_id)
           
        # except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        #     raise serializers.ValidationError("Invalid UID.")
        # activation_str = self.user.activation_key
        # if not activation_str:
        #     return Response({"detail": "password reset link is already used"}, status=400)
        # activation_time = datetime.strptime(activation_str, "%Y-%m-%d-%H-%M-%S")
        # if timezone.now() > timezone.make_aware(activation_time):
        #     return Response({"detail": "password reset link is expired"}, status=400)

        # if not account_activation_token.check_token(self.user, token):
        #     raise serializers.ValidationError("Invalid token.")
    
        # def save(self):
        #  self.user.set_password(new_password)
        #  self.user.activation_key = None 
        #  self.user.save()