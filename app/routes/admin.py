from flask import Blueprint, jsonify, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.services.proveedor_service import ProveedorService
from app.services.user_service import UserService
from app.services.orden_service import OrdenService
from app.services.orden_detalle_service import OrdenDetalleService
from app.services.proveedores.buscador_producto import BuscadorProducto
from app.services.CurrencyService import CurrencyService
from app.auth.decorators import role_required
from datetime import datetime
import re



admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.get("/")
@login_required
@role_required("admin")
def dashboard():
    return render_template("admin/dashboard.html")


@admin_bp.get("/users")
@login_required
@role_required("admin")
def users():
    usuarios = UserService.get_all()
    return render_template("admin/users.html", usuarios=usuarios)


@admin_bp.get("/users/create")
@login_required
@role_required("admin")
def create_user():
    return render_template("admin/form_user.html", usuario=None)


@admin_bp.post("/users/create")
@login_required
@role_required("admin")
def create_user_post():
    user, error = UserService.create(
        username=request.form.get("username"),
        email=request.form.get("email"),
        role=request.form.get("role"),
        nombre=request.form.get("nombre"),
        ap_paterno=request.form.get("ap_paterno"),
        ap_materno=request.form.get("ap_materno"),
        password=request.form.get("password"),
    )

    if error:
        flash(error, "danger")
        return render_template("admin/form_user.html", usuario=None)

    flash("Usuario creado correctamente", "success")
    return redirect(url_for("admin.users"))


@admin_bp.get("/users/<int:user_id>/edit")
@login_required
@role_required("admin")
def edit_user(user_id):
    usuario = UserService.get_by_id(user_id)

    if not usuario:
        flash("Usuario no encontrado", "danger")
        return redirect(url_for("admin.users"))

    return render_template("admin/form_user.html", usuario=usuario)


@admin_bp.post("/users/<int:user_id>/edit")
@login_required
@role_required("admin")
def edit_user_post(user_id):
    user, error = UserService.update(
        user_id=user_id,
        username=request.form.get("username"),
        email=request.form.get("email"),
        role=request.form.get("role"),
        nombre=request.form.get("nombre"),
        ap_paterno=request.form.get("ap_paterno"),
        ap_materno=request.form.get("ap_materno"),
        password=request.form.get("password"),
    )

    if error:
        flash(error, "danger")
        usuario = UserService.get_by_id(user_id)
        return render_template("admin/form_user.html", usuario=usuario)

    flash("Usuario actualizado correctamente", "success")
    return redirect(url_for("admin.users"))


@admin_bp.post("/users/<int:user_id>/delete")
@login_required
@role_required("admin")
def delete_user(user_id):
    success, error = UserService.soft_delete(user_id)

    if error:
        flash(error, "danger")
    else:
        flash("Usuario eliminado correctamente", "success")

    return redirect(url_for("admin.users"))

@admin_bp.route("/ordenes")
@login_required
@role_required("admin")
def ordenes():
    search = request.args.get('search', '').strip() or None
    estado = request.args.get('estado', 'pendiente')
    fecha_inicio = request.args.get('fecha_inicio', '').strip() or None
    fecha_fin = request.args.get('fecha_fin', '').strip() or None
    page = request.args.get('page', 1, type=int)
    
    ordenes, total_pages, error = OrdenService.search_orders(
        search=search,
        estado=estado,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        page=page,
        per_page=12
    )
    
    if error:
        flash(error, 'error')
        ordenes, total_pages = [], 0
    
    return render_template(
        'admin/ordenes.html',
        ordenes=ordenes,
        page=page,
        total_pages=total_pages,
        search=search,
        estado_actual=estado,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin
    )


@admin_bp.get('/ordenes/create')
@login_required
@role_required("admin")
def nueva_orden():
    """
    Muestra el formulario para crear una nueva orden.
    """
    # Pasar la fecha actual formateada para el campo de fecha
    today = datetime.now().strftime('%Y-%m-%d')
    return render_template('admin/nueva_orden.html', today=today)


@admin_bp.post('/ordenes/create')
@login_required
@role_required("admin")
def nueva_orden_post():
    """
    Procesa la creación de una orden con sus detalles.
    """
    try:
        clave_orden = request.form.get('clave_orden', '').strip()
        comprador = request.form.get('comprador', '').strip()
        fecha_creacion_str = request.form.get('fecha_creacion', '').strip()
        estado = 'pendiente'  # Fijo

        if not clave_orden:
            flash("La clave de la orden es obligatoria.", "error")
            return redirect(url_for('admin.nueva_orden'))
        if not comprador:
            flash("El comprador es obligatorio.", "error")
            return redirect(url_for('admin.nueva_orden'))

        fecha_creacion = None
        if fecha_creacion_str:
            try:
                fecha_creacion = datetime.strptime(fecha_creacion_str, '%Y-%m-%d')
            except ValueError:
                flash("Formato de fecha inválido.", "error")
                return redirect(url_for('admin.nueva_orden'))

        # Extraer detalles simplificados
        detalles_raw = {}
        for key in request.form:
            match = re.match(r'detalles\[(\d+)\]\[(\w+)\]', key)
            if match:
                idx = int(match.group(1))
                campo = match.group(2)
                if idx not in detalles_raw:
                    detalles_raw[idx] = {}
                detalles_raw[idx][campo] = request.form.get(key)

        if not detalles_raw:
            flash("Debe agregar al menos un producto a la orden.", "error")
            return redirect(url_for('admin.nueva_orden'))

        detalles_list = [detalles_raw[i] for i in sorted(detalles_raw.keys())]

        # Validar campos requeridos de cada detalle
        for i, det in enumerate(detalles_list):
            if not det.get('producto'):
                flash(f"El producto #{i+1} no tiene nombre.", "error")
                return redirect(url_for('admin.nueva_orden'))
            try:
                cantidad = int(det.get('cantidad', 0))
                if cantidad <= 0:
                    raise ValueError
            except ValueError:
                flash(f"El producto #{i+1} debe tener una cantidad válida > 0.", "error")
                return redirect(url_for('admin.nueva_orden'))

        # Preparar detalles con valores por defecto para campos no incluidos
        for det in detalles_list:
            det.setdefault('precio_unitario', '0.00')
            det.setdefault('ganancia_unitaria', '0.00')
            det.setdefault('costo_envio', '0.00')
            det.setdefault('margen_ganancia', '0.00')
            # id_proveedor se deja nulo
            if 'id_proveedor' not in det:
                det['id_proveedor'] = None

        id_usuario = current_user.id

        data_orden = {
            "clave_orden": clave_orden,
            "id_usuario": id_usuario,
            "comprador": comprador,
            "estado": estado,
            "total": "0.00",
        }
        if fecha_creacion:
            data_orden["fecha_creacion"] = fecha_creacion

        orden, error = OrdenService.create(data_orden)
        if error:
            flash(f"Error al crear la orden: {error}", "error")
            return redirect(url_for('admin.nueva_orden'))

        detalles_creados, error_detalles = OrdenDetalleService.add_bulk(orden.id_orden, detalles_list)
        if error_detalles:
            OrdenService.delete(orden.id_orden)
            flash(f"Error al agregar productos: {error_detalles}", "error")
            return redirect(url_for('admin.nueva_orden'))
        
        nuevo_total, error_total = OrdenService.recalculate_total(orden.id_orden)
        if error_total:
            OrdenService.delete(orden.id_orden)
            flash(error_total, "error")
            return redirect(url_for('admin.nueva_orden'))

        flash(f"Orden '{orden.clave_orden}' creada exitosamente con {len(detalles_creados)} producto(s).", "success")
        return redirect(url_for('admin.ordenes'))

    except Exception as e:
        flash(f"Error inesperado: {str(e)}", "error")
        return redirect(url_for('admin.nueva_orden'))


@admin_bp.get('/ordenes/<int:id_orden>')
@login_required
@role_required("admin")
def orden_detalle(id_orden):
    """
    Muestra la página de detalle de una orden con todos sus productos.
    """
    orden, detalles, error = OrdenService.get_with_details(id_orden)
    if error or not orden:
        flash(error or "Orden no encontrada", "error")
        return redirect(url_for('admin.ordenes'))
    
    proveedores = ProveedorService.get_all()

    return render_template(
        'admin/detalle_orden.html',
        orden=orden,
        proveedores=proveedores
    )


@admin_bp.post('/ordenes/<int:id_orden>/update')
@login_required
@role_required("admin")
def orden_update(id_orden):

    data = {
        "clave_orden": request.form.get("clave_orden", "").strip(),
        "comprador": request.form.get("comprador", "").strip(),
        "estado": request.form.get("estado", "").strip(),
        "fecha_creacion": request.form.get("fecha_creacion", "").strip(),
    }

    orden, error = OrdenService.update(id_orden, data)

    if error:
        flash(error, "error")
    else:
        flash("Orden actualizada correctamente", "success")

    return redirect(url_for('admin.orden_detalle', id_orden=id_orden))


@admin_bp.post('/ordenes/<int:id_orden>/detalles')
@login_required
@role_required("admin")
def orden_agregar_detalle(id_orden):

    try:
        orden = OrdenService.get_by_id(id_orden)
        if not orden:
            flash("La orden no existe.", "error")
            return redirect(url_for('admin.ordenes'))

        producto = request.form.get('producto', '').strip()
        clave_producto = request.form.get('clave_producto', '').strip() or None
        
        try:
            cantidad = int(request.form.get('cantidad', 0))
            if cantidad <= 0:
                raise ValueError
        except (ValueError, TypeError):
            flash("La cantidad debe ser un número válido mayor a 0.", "error")
            return redirect(url_for('admin.orden_detalle', id_orden=id_orden))

        if not producto:
            flash("El nombre del producto es obligatorio.", "error")
            return redirect(url_for('admin.orden_detalle', id_orden=id_orden))

        data = {
            "producto": producto,
            "clave_producto": clave_producto,
            "cantidad": cantidad,
            "precio_unitario": 0.00,  # Valor por defecto
            "ganancia_unitaria": 0.00,  # Valor por defecto
            "costo_envio": 0.00,  # Valor por defecto
            "margen_ganancia": 0.00,  # Valor por defecto
            "id_proveedor": None  # Se deja nulo por defecto
        }

        detalle, error = OrdenDetalleService.add_detalle(id_orden, data)
        
        if error:
            flash(f"Error al agregar el producto: {error}", "error")
            return redirect(url_for('admin.orden_detalle', id_orden=id_orden))

        # Recalcular totales de la orden
        nuevo_total, error_total = OrdenService.recalculate_total(id_orden)
        
        if error_total:
            if detalle and detalle.get('id_detalle'):
                OrdenDetalleService.delete(detalle['id_detalle'])
            flash(f"Error al actualizar los totales: {error_total}", "error")
            return redirect(url_for('admin.orden_detalle', id_orden=id_orden))

        flash(f"Producto '{producto}' agregado exitosamente a la orden.", "success")
        return redirect(url_for('admin.orden_detalle', id_orden=id_orden))

    except Exception as e:
        flash(f"Error inesperado al agregar producto: {str(e)}", "error")
        return redirect(url_for('admin.orden_detalle', id_orden=id_orden))


@admin_bp.get('/ordenes/detalles/<int:id_detalle>')
@login_required
def orden_detalle_show(id_detalle):

    detalle = OrdenDetalleService.get_by_id(id_detalle)

    return render_template(
        'admin/detalle_show.html',
        detalle=detalle
    )


@admin_bp.post('/ordenes/detalles/<int:id_detalle>/update')
@login_required
@role_required("admin")
def orden_detalle_update(id_detalle):

    detalle_actual = OrdenDetalleService.get_by_id(id_detalle)

    if not detalle_actual:
        flash("Producto no encontrado", "error")
        return redirect(url_for('admin.ordenes'))

    data = {
        "producto": request.form.get("producto", "").strip(),
        "clave_producto": request.form.get("clave_producto") or None,
        "cantidad": request.form.get("cantidad", type=int),
        "precio_unitario": request.form.get("precio_unitario", type=float),
        "costo_envio": request.form.get("costo_envio", type=float),
        "margen_ganancia": request.form.get("margen_ganancia", type=float),
        "url_producto": request.form.get("url_producto") or None,
        "url_imagen": request.form.get("url_imagen") or None,
    }

    detalle, error = OrdenDetalleService.update_detalle(
        id_detalle=id_detalle,
        data=data,
    )

    if error:
        flash(error, "error")
        return redirect(
            url_for(
                "admin.orden_detalle",
                id_orden=detalle_actual.id_orden,
            )
        )
        
    nuevo_total, error_total = OrdenService.recalculate_total(detalle.id_orden)
    if error_total:
        flash(error_total, "error")
        return redirect(
            url_for(
                "admin.orden_detalle",
                id_orden=detalle.id_orden,
            )
        )

    flash("Producto actualizado", "success")

    return redirect(
        url_for(
            "admin.orden_detalle",
            id_orden=detalle.id_orden,
        )
    )


@admin_bp.post('/ordenes/detalles/<int:id_detalle>/delete')
@login_required
@role_required("admin")
def orden_delete_detalle(id_detalle):

    detalle = OrdenDetalleService.get_by_id(id_detalle)

    if not detalle:
        flash("Producto no encontrado", "error")
        return redirect(url_for('admin.ordenes'))

    id_orden = detalle.id_orden

    success, error = OrdenDetalleService.delete_detalle(id_detalle)

    if not success:
        flash(error, "error")
        
    nuevo_total, error_total = OrdenService.recalculate_total(id_orden)
    if error_total:
        flash(error_total, "error")
        return redirect(url_for('admin.orden_detalle', id_orden=id_orden))
    
    flash("Producto eliminado", "success")

    return redirect(
        url_for('admin.orden_detalle',id_orden=id_orden))


@admin_bp.post('/ordenes/<int:id_orden>/delete')
@login_required
@role_required("admin")
def orden_delete(id_orden):

    orden, detalles, error = OrdenService.get_with_details(id_orden)

    if error or not orden:
        flash(error or "Orden no encontrada", "error")
        return redirect(url_for('admin.ordenes'))

    success, error = OrdenService.delete(id_orden)

    if not success:
        flash(error or "No se pudo eliminar la orden", "error")
    else:
        flash("Orden eliminada correctamente", "success")

    return redirect(url_for('admin.ordenes'))


@admin_bp.get('/ordenes/<int:id_detalle>/proveedores')
@login_required
def orden_detalle_proveedores(id_detalle):
    
    detalle = OrdenDetalleService.get_by_id(id_detalle)
    if not detalle:
        flash("Producto no encontrado", "error")
        return redirect(url_for('admin.ordenes'))
    
    if not detalle.clave_producto:
        flash("El producto no tiene clave SKU para buscar proveedores", "error")
        return redirect(
            url_for(
                "admin.orden_detalle_show",
                id_detalle=id_detalle,
            )
        )
        
    productos = BuscadorProducto.buscar(nombre=detalle.producto, sku=detalle.clave_producto)

    return render_template(
        'admin/proveedores.html',
        productos=productos,
        id_detalle=id_detalle
    )
    
    
@admin_bp.post('/ordenes/<int:id_detalle>/proveedores')
@login_required
def orden_detalle_seleccionar_proveedor(id_detalle):

    detalle = OrdenDetalleService.get_by_id(id_detalle)

    if not detalle:
        flash("Producto no encontrado", "error")
        return redirect(url_for('admin.ordenes'))

    existencia = request.form.get("existencia", type=int)

    if existencia is not None:

        if existencia <= 0:
            flash(
                "El proveedor seleccionado no tiene existencia disponible",
                "error"
            )

            return redirect(
                url_for(
                    "admin.orden_detalle_show",
                    id_detalle=id_detalle,
                )
            )

        if existencia < detalle.cantidad:
            flash(
                (
                    "El proveedor seleccionado tiene existencia "
                    f"insuficiente ({existencia} disponibles) "
                    f"para la cantidad requerida ({detalle.cantidad})."
                ),
                "error"
            )

            return redirect(
                url_for(
                    "admin.orden_detalle_show",
                    id_detalle=id_detalle,
                )
            )

    proveedor_nombre = request.form.get("proveedor")

    if not proveedor_nombre:
        flash("Proveedor no seleccionado", "error")

        return redirect(
            url_for(
                "admin.orden_detalle_show",
                id_detalle=id_detalle,
            )
        )

    proveedor = ProveedorService.search_by_nombre(
        proveedor_nombre
    )

    if not proveedor:
        flash("Proveedor no encontrado", "error")

        return redirect(
            url_for(
                "admin.orden_detalle_show",
                id_detalle=id_detalle,
            )
        )

    data = {
        "id_proveedor": proveedor.id_proveedor
    }

    imagen = request.form.get("url_imagen")

    if not detalle.url_imagen and imagen:
        data["url_imagen"] = imagen

    moneda = request.form.get("moneda")
    precio = request.form.get(
        "precio",
        type=float
    )

    if moneda and precio is not None:
        precio_mxn, error = CurrencyService.calcular_conversion_MXN(
            precio=precio,
            from_currency=moneda
        )
        
        if error:
            flash(error, "error")
            return redirect(
                url_for("admin.orden_detalle_show",id_detalle=id_detalle)
            )

        data["precio_unitario"] = precio_mxn

    success, error = OrdenDetalleService.update_detalle(
        id_detalle=id_detalle,
        data=data
    )

    if not success:

        flash(
            error or "No se pudo asignar el proveedor",
            "error"
        )

    else:

        flash(
            "Proveedor asignado correctamente",
            "success"
        )

    return redirect(
        url_for(
            "admin.orden_detalle_show",
            id_detalle=id_detalle,
        )
    )
    

@admin_bp.post('/ordenes/<int:id_detalle>/proveedores/manual')
@login_required
def orden_detalle_asignar_proveedor_manual(id_detalle):

    detalle = OrdenDetalleService.get_by_id(id_detalle)

    if not detalle:
        flash("Producto no encontrado", "error")
        return redirect(url_for('admin.ordenes'))

    proveedor_nombre = request.form.get("proveedor").strip()

    if not proveedor_nombre:
        flash("El nombre del proveedor es obligatorio", "error")
        return redirect(
            url_for(
                "admin.orden_detalle_show",
                id_detalle=id_detalle,
            )
        )

    proveedor = ProveedorService.search_by_nombre(proveedor_nombre)

    if not proveedor:
        proveedor, error = ProveedorService.create({"nombre": proveedor_nombre})
        if error:
            flash(f"Error al crear el proveedor: {error}", "error")
            return redirect(
                url_for(
                    "admin.orden_detalle_show",
                    id_detalle=id_detalle,
                )
            )

    data = {
        "id_proveedor": proveedor.id_proveedor
    }

    success, error = OrdenDetalleService.update_detalle(
        id_detalle=id_detalle,
        data=data
    )

    if not success:
        flash(
            error or "No se pudo asignar el proveedor",
            "error"
        )
    else:
        flash(
            "Proveedor asignado correctamente",
            "success"
        )

    return redirect(
        url_for(
            "admin.orden_detalle_show",
            id_detalle=id_detalle,
        )
    )