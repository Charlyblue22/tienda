# webapp/api/router.py
from django.urls import path
from django.views.decorators.csrf import csrf_exempt
from .permissions import superuser_required


class AdminAPIRouter:
    """
    Router especializado para la Admin API.
    Aplica automáticamente el permiso de superusuario (IsSuperUser)
    y el manejo de CSRF a todos los endpoints que registra, garantizando que
    ninguna vista de administración quede expuesta sin protección y eliminando
    la necesidad de decorar vista por vista.
    """

    def __init__(self, guard=superuser_required):
        self.guard = guard
        self._patterns = []

    def register(self, route: str, view_func, name: str = None):
        """
        Registra una ruta asegurando que el guard de permisos y csrf_exempt
        se apliquen de forma centralizada en el enrutador.
        """
        protected_view = csrf_exempt(self.guard(view_func))
        self._patterns.append(path(route, protected_view, name=name))

    @property
    def urls(self):
        """Retorna la lista de rutas compiladas para ser consumidas por include()."""
        return self._patterns

