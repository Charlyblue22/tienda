from django.db.utils import OperationalError, ProgrammingError
from .models import ConfiguracionTienda


def tienda_context(request):
    """Inyecta la configuración general de la tienda y banderas de navegación en todas las plantillas."""
    try:
        config = ConfiguracionTienda.obtener()
    except (OperationalError, ProgrammingError):
        config = {
            'nombre_tienda': 'Patitas Chile',
            'slogan': 'Nutrición, salud y bienestar premium para tu mascota',
            'email_contacto': 'contacto@patitaschile.cl',
            'telefono_contacto': '+56 9 8450 3210',
            'direccion': 'Av. Providencia 1450, Providencia, Santiago',
            'horario_atencion': 'Lunes a Sábado: 09:00 a 20:00 hrs',
            'iva_porcentaje': 19,
            'stock_minimo_alerta': 10,
            'envio_gratis_desde': 35000,
        }

    url_name = getattr(getattr(request, 'resolver_match', None), 'url_name', '') or ''
    return {
        'config_tienda': config,
        'nav_home': url_name == 'portal_home',
        'nav_productos': url_name in ('lista_productos', 'detalle_producto'),
        'nav_categorias': url_name == 'lista_categorias',
        'nav_marcas': url_name == 'lista_marcas',
    }
