# Generated migration for Venta, DetalleVenta, and ConfiguracionTienda
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('webapp', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ConfiguracionTienda',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre_tienda', models.CharField(default='Patitas Chile', max_length=100)),
                ('slogan', models.CharField(default='Nutrición, salud y bienestar premium para tu mascota', max_length=200)),
                ('email_contacto', models.EmailField(default='contacto@patitaschile.cl', max_length=254)),
                ('telefono_contacto', models.CharField(default='+56 9 8450 3210', max_length=30)),
                ('direccion', models.CharField(default='Av. Providencia 1450, Providencia, Santiago', max_length=200)),
                ('horario_atencion', models.CharField(default='Lunes a Sábado: 09:00 a 20:00 hrs', max_length=120)),
                ('iva_porcentaje', models.PositiveIntegerField(default=19)),
                ('stock_minimo_alerta', models.PositiveIntegerField(default=10)),
                ('envio_gratis_desde', models.PositiveIntegerField(default=35000)),
                ('actualizado', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Configuración de Tienda',
                'verbose_name_plural': 'Configuraciones de Tienda',
            },
        ),
        migrations.CreateModel(
            name='Venta',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('folio', models.CharField(blank=True, max_length=24, unique=True)),
                ('cliente_nombre', models.CharField(default='Cliente General', max_length=120)),
                ('cliente_email', models.EmailField(blank=True, max_length=254)),
                ('estado', models.CharField(choices=[('completada', 'Completada'), ('pendiente', 'Pendiente'), ('cancelada', 'Cancelada')], default='completada', max_length=15)),
                ('metodo_pago', models.CharField(choices=[('tarjeta', 'Tarjeta Débito / Crédito'), ('transferencia', 'Transferencia Bancaria'), ('efectivo', 'Efectivo')], default='tarjeta', max_length=20)),
                ('subtotal', models.PositiveIntegerField(default=0, help_text='Monto neto en CLP')),
                ('iva', models.PositiveIntegerField(default=0, help_text='IVA (19%) en CLP')),
                ('total', models.PositiveIntegerField(default=0, help_text='Monto total bruto en CLP')),
                ('notas', models.TextField(blank=True)),
                ('fecha', models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ('usuario', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='ventas', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-fecha', '-id'],
            },
        ),
        migrations.CreateModel(
            name='DetalleVenta',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre_producto', models.CharField(max_length=120)),
                ('cantidad', models.PositiveIntegerField(default=1)),
                ('precio_unitario', models.PositiveIntegerField(help_text='Precio unitario en CLP')),
                ('subtotal', models.PositiveIntegerField(help_text='Subtotal de la línea en CLP')),
                ('producto', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='detalles_venta', to='webapp.producto')),
                ('venta', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='detalles', to='webapp.venta')),
            ],
            options={
                'ordering': ['id'],
            },
        ),
    ]

