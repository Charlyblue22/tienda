# webapp/api/permissions.py
import functools
import logging
from django.http import JsonResponse

logger = logging.getLogger('admin_api')


class IsSuperUserPermission:
    """
    Guard de permisos que restringe el acceso exclusivamente a superusuarios.
    Retorna:
      - 401 Unauthorized si la petición es anónima.
      - 403 Forbidden si el usuario está autenticado pero no posee rol de superusuario.
    """

    @classmethod
    def check_permission(cls, request):
        if not request.user.is_authenticated:
            return False, JsonResponse({
                'error': 'No autenticado.',
                'detalle': 'Se requiere iniciar sesión con credenciales válidas para acceder a este recurso.',
                'codigo': 'unauthorized'
            }, status=401)

        if not request.user.is_superuser:
            return False, JsonResponse({
                'error': 'Acceso denegado.',
                'detalle': 'Permisos insuficientes. Este recurso está restringido únicamente a superusuarios.',
                'codigo': 'forbidden'
            }, status=403)

        return True, None


def superuser_required(view_func):
    """
    Decorador / Wrapper reutilizable que aplica IsSuperUserPermission.
    """
    @functools.wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        allowed, response = IsSuperUserPermission.check_permission(request)
        if not allowed:
            return response
        return view_func(request, *args, **kwargs)
    return _wrapped_view
