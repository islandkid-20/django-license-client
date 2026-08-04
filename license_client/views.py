from django.http import JsonResponse

from license_client.decorators import license_exempt
from license_client.state import resolve


@license_exempt
def status(request):
    """Machine-readable state, for your own monitoring. No client data is exposed."""
    state = resolve(request.get_host().split(":")[0])
    return JsonResponse(
        {
            "level": state.level,
            "reason": state.reason,
            "period_end": (
                state.license.period_end.isoformat() if state.license else None
            ),
        }
    )
