import os
from django.contrib.auth.models import User
from django.core.management import BaseCommand, call_command

from webapp.models import ConfiguracionTienda, Producto
from webapp.services import asegurar_ventas_demostracion


class Command(BaseCommand):
    help = 'Inicializa datos de catálogo, ventas de demostración y superusuario para producción (Render).'

    def handle(self, *args, **options):
        # 1. Cargar catálogo inicial si la base de datos está vacía
        if not Producto.objects.exists():
            self.stdout.write('Cargando catálogo inicial desde fixture datos_iniciales.json...')
            call_command('loaddata', 'datos_iniciales')
            self.stdout.write(self.style.SUCCESS('Catálogo inicial cargado correctamente.'))
        else:
            self.stdout.write('El catálogo ya cuenta con productos registrados.')

        # 2. Asegurar configuración de tienda y ventas de demostración
        ConfiguracionTienda.obtener()
        asegurar_ventas_demostracion()
        self.stdout.write(self.style.SUCCESS('Configuración y datos de ventas verificados.'))

        # 3. Asegurar superusuario administrador
        username = os.environ.get('DJANGO_SUPERUSER_USERNAME', 'admin').strip()
        email = os.environ.get('DJANGO_SUPERUSER_EMAIL', 'admin@patitaschile.cl').strip()
        password = os.environ.get('DJANGO_SUPERUSER_PASSWORD', 'admin12345')

        user = User.objects.filter(username=username).first()
        if not user:
            User.objects.create_superuser(username=username, email=email, password=password)
            self.stdout.write(
                self.style.SUCCESS(f"Superusuario '{username}' creado exitosamente.")
            )
        elif os.environ.get('DJANGO_SUPERUSER_PASSWORD'):
            user.email = email or user.email
            user.is_staff = True
            user.is_superuser = True
            user.set_password(password)
            user.save()
            self.stdout.write(
                self.style.SUCCESS(f"Credenciales del superusuario '{username}' actualizadas.")
            )
        else:
            self.stdout.write(f"Superusuario '{username}' ya existe.")

