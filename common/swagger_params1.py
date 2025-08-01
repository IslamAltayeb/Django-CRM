from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter
from role_permission_control.models import Role

organization_params_in_header = OpenApiParameter(
    "org", OpenApiTypes.STR, OpenApiParameter.HEADER
)

organization_params = [
    organization_params_in_header,
]

roles = Role.objects.values_list("name", flat=True)
user_list_params = [
    organization_params_in_header,
    OpenApiParameter("email",  OpenApiTypes.STR,OpenApiParameter.QUERY),
    OpenApiParameter(
        #"role", OpenApiTypes.STR, OpenApiParameter.QUERY,enum=["ADMIN", "USER"]
        "role", OpenApiTypes.STR, OpenApiParameter.QUERY,enum=list(roles)
    ),
    OpenApiParameter(
        "status",
        OpenApiTypes.STR,
        OpenApiParameter.QUERY,
        enum=["Active", "In Active"],
    ),
]

document_get_params = [
    organization_params_in_header,
    OpenApiParameter("title", OpenApiTypes.STR,OpenApiParameter.QUERY),
    OpenApiParameter(
        "status",
        OpenApiTypes.STR,
        OpenApiParameter.QUERY,
        enum=["Active", "In Active"],
    ),
    OpenApiParameter("shared_to", OpenApiTypes.STR,OpenApiParameter.QUERY),
]

