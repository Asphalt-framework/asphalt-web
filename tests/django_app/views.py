from django.http import HttpRequest, HttpResponse, JsonResponse

from asphalt.core import inject, resource


@inject
async def index(
    request: HttpRequest,
    my_resource: str = resource(),
    another_resource: str = resource("another"),
) -> HttpResponse:
    return JsonResponse(
        {
            "message": request.GET["param"],
            "my resource": my_resource,
            "another resource": another_resource,
        }
    )
