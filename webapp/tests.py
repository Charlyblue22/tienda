# webapp/tests.py
import json
from django.contrib.auth.models import User
from django.test import Client, TestCase
from webapp.models import Categoria, ConfiguracionTienda, Marca, Producto, Venta


class AdminAPIPermissionsTestCase(TestCase):
    """
    Suite de pruebas para verificar:
    1. Anónimo -> 401 Unauthorized en Admin API.
    2. Usuario normal / staff no superuser -> 403 Forbidden en Admin API.
    3. Superusuario -> 200 OK (GET), 201 Created (POST), 200 OK (PUT), 204 No Content (DELETE).
    4. Separación de API Base pública (Solo GET, 405 en escritura).
    5. Contabilidad de ventas, cálculo de IVA/subtotales, descuento de stock y exportación CSV.
    6. Gestión de usuarios, configuración y ausencia de referencias a Postman.
    """

    def setUp(self):
        self.client = Client()

        # 1. Superusuario
        self.super_user = User.objects.create_superuser(
            username='admin_boss', password='password123', email='admin@patitaschile.cl'
        )

        # 2. Usuario cliente normal
        self.normal_user = User.objects.create_user(
            username='cliente_juan', password='password123', email='juan@patitaschile.cl'
        )

        # 3. Usuario staff no superusuario
        self.staff_user = User.objects.create_user(
            username='staff_pedro', password='password123', email='pedro@patitaschile.cl', is_staff=True
        )

        # Datos de prueba
        self.categoria = Categoria.objects.create(nombre='Juguetes', descripcion='Juguetes para mascotas')
        self.marca = Marca.objects.create(nombre='Kong', pais_origen='USA')
        self.producto = Producto.objects.create(
            nombre='Pelota Resistente',
            precio=4990,
            stock=15,
            especie='perro',
            categoria=self.categoria,
            marca=self.marca
        )

    # -------------------------------------------------------------
    # 1. PRUEBAS PARA PETICIONES ANÓNIMAS (401 Unauthorized)
    # -------------------------------------------------------------
    def test_anonymous_request_returns_401(self):
        """Un usuario anónimo debe recibir 401 en cualquier método de la Admin API."""
        res = self.client.get('/api/admin/productos/')
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json().get('codigo'), 'unauthorized')

        res = self.client.post(
            '/api/admin/productos/',
            data=json.dumps({'nombre': 'Nuevo'}),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 401)

        res = self.client.put(
            f'/api/admin/productos/{self.producto.id}/',
            data=json.dumps({'nombre': 'Modificado'}),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 401)

        res = self.client.delete(f'/api/admin/productos/{self.producto.id}/')
        self.assertEqual(res.status_code, 401)

    # -------------------------------------------------------------
    # 2. PRUEBAS PARA USUARIOS NO SUPERUSUARIOS (403 Forbidden)
    # -------------------------------------------------------------
    def test_authenticated_normal_user_returns_403(self):
        """Un usuario normal autenticado debe recibir 403 Forbidden."""
        self.client.force_login(self.normal_user)
        res = self.client.get('/api/admin/productos/')
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json().get('codigo'), 'forbidden')

    def test_staff_non_superuser_returns_403(self):
        """Un miembro de staff sin rol de superusuario también debe recibir 403 Forbidden."""
        self.client.force_login(self.staff_user)
        res = self.client.get('/api/admin/productos/')
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json().get('codigo'), 'forbidden')

    # -------------------------------------------------------------
    # 3. PRUEBAS PARA SUPERUSUARIO (200, 201, 204)
    # -------------------------------------------------------------
    def test_superuser_get_list_and_detail_returns_200(self):
        """El superusuario puede consultar listas y detalles con 200 OK."""
        self.client.force_login(self.super_user)

        res_list = self.client.get('/api/admin/productos/')
        self.assertEqual(res_list.status_code, 200)
        self.assertEqual(res_list.json()['count'], 1)

        res_detail = self.client.get(f'/api/admin/productos/{self.producto.id}/')
        self.assertEqual(res_detail.status_code, 200)
        self.assertEqual(res_detail.json()['nombre'], 'Pelota Resistente')

    def test_superuser_post_valid_creates_product_returns_201(self):
        """El superusuario puede crear productos válidos con 201 Created."""
        self.client.force_login(self.super_user)
        payload = {
            'nombre': 'Rascador Torre 3 Niveles',
            'descripcion': 'Ideal para gatos activos.',
            'precio': 34990,
            'stock': 8,
            'especie': 'gato',
            'categoria_id': self.categoria.id,
            'marca_id': self.marca.id
        }
        res = self.client.post(
            '/api/admin/productos/',
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertEqual(data['nombre'], 'Rascador Torre 3 Niveles')
        self.assertTrue(Producto.objects.filter(nombre='Rascador Torre 3 Niveles').exists())

    def test_superuser_post_invalid_returns_400(self):
        """Datos inválidos o faltantes en POST retornan 400 Bad Request."""
        self.client.force_login(self.super_user)
        payload = {'descripcion': 'Incompleto'}
        res = self.client.post(
            '/api/admin/productos/',
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn('campos_faltantes', res.json())

    def test_superuser_put_update_returns_200(self):
        """El superusuario puede actualizar completamente un producto con 200 OK."""
        self.client.force_login(self.super_user)
        payload = {
            'nombre': 'Pelota Resistente Ultra',
            'descripcion': 'Versión reforzada 2026',
            'precio': 5990,
            'stock': 25,
            'especie': 'perro',
            'categoria_id': self.categoria.id
        }
        res = self.client.put(
            f'/api/admin/productos/{self.producto.id}/',
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.nombre, 'Pelota Resistente Ultra')
        self.assertEqual(self.producto.precio, 5990)

    def test_superuser_delete_removes_product_returns_204(self):
        """El superusuario puede eliminar un producto con 204 No Content."""
        self.client.force_login(self.super_user)
        res = self.client.delete(f'/api/admin/productos/{self.producto.id}/')
        self.assertEqual(res.status_code, 204)
        self.assertFalse(Producto.objects.filter(id=self.producto.id).exists())

    # -------------------------------------------------------------
    # 4. PRUEBAS DE SEPARACIÓN CON LA API BASE PÚBLICA
    # -------------------------------------------------------------
    def test_public_base_api_is_read_only(self):
        """La API Base (/api/productos/) permite GET público pero rechaza POST con 405."""
        res_get = self.client.get('/api/productos/')
        self.assertEqual(res_get.status_code, 200)

        res_post = self.client.post(
            '/api/productos/',
            data=json.dumps({'nombre': 'Hack'}),
            content_type='application/json'
        )
        self.assertEqual(res_post.status_code, 405)

    # -------------------------------------------------------------
    # 5. PRUEBAS DE RUTAS PROTEGIDAS Y AUSENCIA DE POSTMAN
    # -------------------------------------------------------------
    def test_admin_docs_view_permission(self):
        """La ruta protegida solo puede ser vista por superusuarios."""
        res_anon = self.client.get('/api-docs/admin/')
        self.assertEqual(res_anon.status_code, 302)

        self.client.force_login(self.normal_user)
        res_normal = self.client.get('/api-docs/admin/')
        self.assertEqual(res_normal.status_code, 302)

        self.client.force_login(self.super_user)
        res_super = self.client.get('/api-docs/admin/')
        self.assertEqual(res_super.status_code, 200)

    def test_admin_panel_renders_without_postman(self):
        """El panel de administración carga para superusuarios y no contiene referencias a Postman."""
        self.client.force_login(self.super_user)
        res = self.client.get('/admin-api/')
        self.assertEqual(res.status_code, 200)
        html = res.content.decode('utf-8')
        self.assertNotIn('Postman', html)
        self.assertNotIn('postman', html)
        self.assertIn('Dashboard Ejecutivo', html)
        self.assertIn('Contabilidad Ventas', html)

    # -------------------------------------------------------------
    # 6. PRUEBAS DE CONTABILIDAD DE VENTAS, DASHBOARD Y EXPORTACIÓN CSV
    # -------------------------------------------------------------
    def test_ventas_crud_stock_and_csv_export(self):
        """Crear una venta descuenta stock, calcula totales e IVA, y permite exportar a CSV."""
        self.client.force_login(self.super_user)
        stock_inicial = self.producto.stock

        payload_venta = {
            'cliente_nombre': 'Ana María Pérez',
            'cliente_email': 'ana@correo.cl',
            'metodo_pago': 'tarjeta',
            'estado': 'completada',
            'items': [
                {'producto_id': self.producto.id, 'cantidad': 3}
            ]
        }
        res_post = self.client.post(
            '/api/admin/ventas/',
            data=json.dumps(payload_venta),
            content_type='application/json'
        )
        self.assertEqual(res_post.status_code, 201)
        venta_data = res_post.json()
        self.assertEqual(venta_data['total'], 4990 * 3)
        self.assertGreater(venta_data['subtotal'], 0)
        self.assertGreater(venta_data['iva'], 0)

        # Verificar descuento de stock
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock, stock_inicial - 3)

        # Consultar contabilidad y resumen
        res_list = self.client.get('/api/admin/ventas/')
        self.assertEqual(res_list.status_code, 200)
        self.assertEqual(res_list.json()['resumen']['total_bruto'], 4990 * 3)

        # Consultar métricas de dashboard
        res_metricas = self.client.get('/api/admin/metricas/')
        self.assertEqual(res_metricas.status_code, 200)
        self.assertEqual(res_metricas.json()['total_ventas_monto'], 4990 * 3)

        # Exportar a CSV
        res_csv = self.client.get('/api/admin/ventas/exportar-csv/')
        self.assertEqual(res_csv.status_code, 200)
        self.assertIn('text/csv', res_csv['Content-Type'])
        csv_text = res_csv.content.decode('utf-8')
        self.assertIn('Ana María Pérez', csv_text)

        # Cancelar venta restituye stock
        venta_id = venta_data['id']
        res_cancel = self.client.patch(
            f'/api/admin/ventas/{venta_id}/',
            data=json.dumps({'estado': 'cancelada'}),
            content_type='application/json'
        )
        self.assertEqual(res_cancel.status_code, 200)
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock, stock_inicial)

    # -------------------------------------------------------------
    # 7. PRUEBAS DE GESTIÓN DE USUARIOS Y CONFIGURACIÓN
    # -------------------------------------------------------------
    def test_usuarios_and_configuracion_endpoints(self):
        """El superusuario puede gestionar usuarios y actualizar la configuración de la tienda."""
        self.client.force_login(self.super_user)

        res_u = self.client.post(
            '/api/admin/usuarios/',
            data=json.dumps({
                'username': 'nuevo_cliente',
                'password': 'claveSegura123',
                'email': 'nuevo@cliente.cl',
                'first_name': 'Nuevo',
                'last_name': 'Cliente',
                'rol': 'cliente'
            }),
            content_type='application/json'
        )
        self.assertEqual(res_u.status_code, 201)
        self.assertTrue(User.objects.filter(username='nuevo_cliente').exists())

        res_cfg = self.client.put(
            '/api/admin/configuracion/',
            data=json.dumps({
                'nombre_tienda': 'Patitas Chile Pro',
                'iva_porcentaje': 19,
                'envio_gratis_desde': 40000
            }),
            content_type='application/json'
        )
        self.assertEqual(res_cfg.status_code, 200)
        self.assertEqual(ConfiguracionTienda.obtener().nombre_tienda, 'Patitas Chile Pro')

    # -------------------------------------------------------------
    # 8. PRUEBAS DE VISTAS PÚBLICAS PARA EL USUARIO / CLIENTE
    # -------------------------------------------------------------
    def test_public_store_views_render_correctly(self):
        """Todas las páginas públicas de la tienda cargan con 200 OK para clientes y visitantes."""
        for url in [
            '/',
            '/productos/',
            f'/productos/?categoria={self.categoria.id}&especie=perro&q=Pelota&orden=precio_asc',
            f'/productos/{self.producto.id}/',
            '/categorias/',
            '/marcas/',
            '/login/',
        ]:
            res = self.client.get(url)
            self.assertEqual(res.status_code, 200, f"Fallo al cargar la ruta {url}")

