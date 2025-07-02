import jwt
from django.conf import settings
from django.contrib.auth import logout
from django.core.exceptions import PermissionDenied
from rest_framework.exceptions import AuthenticationFailed
from rest_framework import status
from rest_framework.response import Response
from crum import get_current_user
from django.utils.functional import SimpleLazyObject

from common.models import Org, Profile, User


def get_actual_value(request):
    if request.user is None:
        return None
    return request.user


class GetProfileAndOrg(object):
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        self.process_request(request)
        return self.get_response(request)

    def process_request(self, request):
        try:
            request.profile = None
            user_id = None

            # Handle JWT token from "Authorization" header
            if request.headers.get("Authorization"):
                token1 = request.headers.get("Authorization")
                if token1.lower().startswith("bearer "):
                    token = token1.split(" ")[1]
                else:
                    token = token1
                decoded = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGO])
                user_id = decoded['user_id']

            # Handle API key authentication (optional)
            api_key = request.headers.get('Token')

            # here I am getting the jwt token passing in header
            # if request.headers.get("Authorization"):
            #     token1 = request.headers.get("Authorization", "")
            #     if token1.startswith("Bearer "):
            #         token = token1.split(" ")[1]  # getting the token value
            #         decoded = jwt.decode(token, (settings.SECRET_KEY), algorithms=[settings.JWT_ALGO])
            #         user_id = decoded['user_id']
            #     else:
            #         raise PermissionDenied("Invalid or missing Authorization header")
            # api_key = request.headers.get('Token')  # Get API key from request query params

            if api_key:
                try:
                    organization = Org.objects.get(api_key=api_key)
                    request.META['org'] = organization.id
                    profile = Profile.objects.filter(org=organization, role="ADMIN").first()
                    user_id = profile.user.id
                except Org.DoesNotExist:
                    raise AuthenticationFailed('Invalid API Key')

            if user_id is not None:
                try:
                    if request.headers.get("org"):
                        profile = Profile.objects.get(
                            user_id=user_id, org=request.headers.get("org"), is_active=True
                        )
                        if profile:
                            request.profile = profile
                except Profile.DoesNotExist:
                    raise PermissionDenied("Profile not found or inactive.")
        except Exception as e:
            print("Middleware error:", str(e))
            raise PermissionDenied("Access Denied due to authentication failure.")
