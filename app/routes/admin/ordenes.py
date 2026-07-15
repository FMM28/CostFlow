from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    send_file,
)
from flask_login import login_required, current_user
from app.auth.decorators import role_required
from app.services.orden_service import OrdenService
from app.services.orden_detalle_service import OrdenDetalleService
from app.services.proveedor_service import ProveedorService
from app.services.agrupacion_service import AgrupacionService
from app.services.departamento_unam_service import DepartamentoUNAMService
from app.services.pdf.cotizacion_pdf_service import CotizacionPDFService
from app.services.proveedores import BuscadorProducto
from app.services.CurrencyService import CurrencyService
from datetime import datetime
import re

ordenes_bp = Blueprint("ordenes", __name__)


def obtener_detalles_form():
    detalles = {}
    for key in request.form:
        match = re.match(r"detalles\[(\d+)\]\[(\w+)\]", key)
        if match:
            idx = int(match.group(1))
            campo = match.group(2)
            if idx not in detalles:
                detalles[idx] = {}
            detalles[idx][campo] = request.form.get(key)
    return [detalles[i] for i in sorted(detalles.keys())]


def render_formulario_orden():
    return render_template(
        "admin/nueva_orden.html",
        today=request.form.get("fecha_creacion") or datetime.now().strftime("%Y-%m-%d"),
        form_data=request.form,
        detalles=obtener_detalles_form(),
    )


@ordenes_bp.get("/")
@login_required
@role_required("admin")
def index():
    search = request.args.get("search", "").strip() or None
    estado = request.args.get("estado", "pendiente")
    fecha_inicio = request.args.get("fecha_inicio", "").strip() or None
    fecha_fin = request.args.get("fecha_fin", "").strip() or None
    page = request.args.get("page", 1, type=int)

    ordenes, total_pages, error = OrdenService.search_orders(
        search=search,
        estado=estado,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        page=page,
        per_page=12,
    )

    if error:
        flash(error, "error")
        ordenes, total_pages = [], 0

    if total_pages > 0 and page > total_pages:
        page = total_pages

    return render_template(
        "admin/ordenes.html",
        ordenes=ordenes,
        page=page,
        total_pages=total_pages,
        search=search,
        estado_actual=estado,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
    )


@ordenes_bp.get("/create")
@login_required
@role_required("admin")
def create():
    today = datetime.now().strftime("%Y-%m-%d")
    return render_template("admin/nueva_orden.html", today=today)


@ordenes_bp.post("/create")
@login_required
@role_required("admin")
def create_post():
    try:
        comprador = request.form.get("comprador", "").strip()
        fecha_creacion_str = request.form.get("fecha_creacion", "").strip()
        estado = "pendiente"

        if not comprador:
            flash("El comprador es obligatorio.", "error")
            return render_formulario_orden()

        fecha_creacion = None
        if fecha_creacion_str:
            try:
                fecha_creacion = datetime.strptime(fecha_creacion_str, "%Y-%m-%d")
            except ValueError:
                flash("Formato de fecha inválido.", "error")
                return render_formulario_orden()

        detalles_raw = {}
        for key in request.form:
            match = re.match(r"detalles\[(\d+)\]\[(\w+)\]", key)
            if match:
                idx = int(match.group(1))
                campo = match.group(2)
                if idx not in detalles_raw:
                    detalles_raw[idx] = {}
                detalles_raw[idx][campo] = request.form.get(key)

        if not detalles_raw:
            flash("Debe agregar al menos un producto a la orden.", "error")
            return render_formulario_orden()

        detalles_list = [detalles_raw[i] for i in sorted(detalles_raw.keys())]

        for i, det in enumerate(detalles_list):
            if not det.get("producto"):
                flash(f"El producto #{i + 1} no tiene nombre.", "error")
                return render_formulario_orden()

            try:
                cantidad = int(det.get("cantidad", 0))
                if cantidad <= 0:
                    raise ValueError
            except (ValueError, TypeError):
                flash(
                    f"El producto #{i + 1} debe tener una cantidad válida mayor a 0.",
                    "error",
                )
                return render_formulario_orden()

        for det in detalles_list:
            det.setdefault("precio_unitario", "0.00")
            det.setdefault("ganancia_unitaria", "0.00")
            det.setdefault("costo_envio", "0.00")
            det.setdefault("margen_ganancia", "0.00")
            det.setdefault("id_proveedor", None)

        data_orden = {
            "id_usuario": current_user.id_usuario,
            "comprador": comprador,
            "estado": estado,
            "total": "0.00",
        }

        if fecha_creacion:
            data_orden["fecha_creacion"] = fecha_creacion

        orden, error = OrdenService.create(data_orden)
        if error:
            flash(f"Error al crear la orden: {error}", "error")
            return render_formulario_orden()

        detalles_creados, error_detalles = OrdenDetalleService.add_bulk(
            orden.id_orden, detalles_list
        )

        if error_detalles:
            OrdenService.delete(orden.id_orden)
            flash(f"Error al agregar productos: {error_detalles}", "error")
            return render_formulario_orden()

        nuevo_total, error_total = OrdenService.recalculate_total(orden.id_orden)

        if error_total:
            OrdenService.delete(orden.id_orden)
            flash(error_total, "error")
            return render_formulario_orden()

        return redirect(url_for("admin.ordenes.detail", id_orden=orden.id_orden))

    except Exception as e:
        flash(f"Error inesperado: {str(e)}", "error")
        return render_formulario_orden()


@ordenes_bp.get("/<int:id_orden>")
@login_required
@role_required("admin")
def detail(id_orden):
    orden, detalles, error = OrdenService.get_with_details(id_orden)
    if error or not orden:
        flash(error or "Orden no encontrada", "error")
        return redirect(url_for("admin.ordenes.index"))

    departamentos = DepartamentoUNAMService.get_all()

    return render_template(
        "admin/detalle_orden.html", orden=orden, departamentos=departamentos
    )


@ordenes_bp.post("/<int:id_orden>/update")
@login_required
@role_required("admin")
def update(id_orden):
    data = {
        "clave_orden": request.form.get("clave_orden", "").strip(),
        "comprador": request.form.get("comprador", "").strip(),
        "estado": request.form.get("estado", "").strip(),
        "fecha_creacion": request.form.get("fecha_creacion", "").strip(),
        "vigencia": request.form.get("vigencia", "").strip(),
        "tipo_cotizacion": request.form.get("tipo_cotizacion", "").strip(),
        "departamento": request.form.get("departamento", "").strip(),
        "punto_entrega": request.form.get("punto_entrega", "").strip(),
        "no_solicitud": request.form.get("no_solicitud", "").strip(),
        "proveedor_unam": request.form.get("proveedor_unam", "").strip(),
        "terminos_condiciones": request.form.get("terminos_condiciones", ""),
        "incluir_firma": request.form.get("incluir_firma") == "1",
        "incluir_imagenes": request.form.get("incluir_imagenes") == "1",
    }

    orden, error = OrdenService.update(id_orden, data)

    if error:
        flash(error, "error")
    else:
        flash("Orden actualizada correctamente", "success")

    return redirect(url_for("admin.ordenes.detail", id_orden=id_orden))


@ordenes_bp.post("/<int:id_orden>/delete")
@login_required
@role_required("admin")
def delete(id_orden):
    orden, detalles, error = OrdenService.get_with_details(id_orden)

    if error or not orden:
        flash(error or "Orden no encontrada", "error")
        return redirect(url_for("admin.ordenes.index"))

    success, error = OrdenService.delete(id_orden)

    if not success:
        flash(error or "No se pudo eliminar la orden", "error")
    else:
        flash("Orden eliminada correctamente", "success")

    return redirect(url_for("admin.ordenes.index"))


@ordenes_bp.post("/<int:id_orden>/detalles")
@login_required
@role_required("admin")
def add_detail(id_orden):
    try:
        orden = OrdenService.get_by_id(id_orden)
        if not orden:
            flash("La orden no existe.", "error")
            return redirect(url_for("admin.ordenes.index"))

        producto = request.form.get("producto", "").strip()
        clave_producto = request.form.get("clave_producto", "").strip() or None

        try:
            cantidad = int(request.form.get("cantidad", 0))
            if cantidad <= 0:
                raise ValueError
        except (ValueError, TypeError):
            flash("La cantidad debe ser un número válido mayor a 0.", "error")
            return redirect(url_for("admin.ordenes.detail", id_orden=id_orden))

        if not producto:
            flash("El nombre del producto es obligatorio.", "error")
            return redirect(url_for("admin.ordenes.detail", id_orden=id_orden))

        data = {
            "producto": producto,
            "clave_producto": clave_producto,
            "cantidad": cantidad,
            "precio_unitario": 0.00,
            "ganancia_unitaria": 0.00,
            "costo_envio": 0.00,
            "margen_ganancia": 0.00,
            "id_proveedor": None,
        }

        detalle, error = OrdenDetalleService.add_detalle(id_orden, data)

        if error:
            flash(f"Error al agregar el producto: {error}", "error")
            return redirect(url_for("admin.ordenes.detail", id_orden=id_orden))

        nuevo_total, error_total = OrdenService.recalculate_total(id_orden)

        if error_total:
            if detalle and detalle.get("id_detalle"):
                OrdenDetalleService.delete(detalle["id_detalle"])
            flash(f"Error al actualizar los totales: {error_total}", "error")
            return redirect(url_for("admin.ordenes.detail", id_orden=id_orden))

        flash(f"Producto '{producto}' agregado exitosamente a la orden.", "success")
        return redirect(url_for("admin.ordenes.detail", id_orden=id_orden))

    except Exception as e:
        flash(f"Error inesperado al agregar producto: {str(e)}", "error")
        return redirect(url_for("admin.ordenes.detail", id_orden=id_orden))


@ordenes_bp.get("/detalles/<int:id_detalle>")
@login_required
@role_required("admin")
def detail_show(id_detalle):
    detalle = OrdenDetalleService.get_by_id(id_detalle)
    return render_template("admin/detalle_show.html", detalle=detalle)


@ordenes_bp.post("/detalles/<int:id_detalle>/update")
@login_required
@role_required("admin")
def detail_update(id_detalle):
    detalle_actual = OrdenDetalleService.get_by_id(id_detalle)

    if not detalle_actual:
        flash("Producto no encontrado", "error")
        return redirect(url_for("admin.ordenes.index"))

    data = {
        "producto": request.form.get("producto", "").strip(),
        "clave_producto": request.form.get("clave_producto") or None,
        "cantidad": request.form.get("cantidad", type=int),
        "precio_unitario": request.form.get("precio_unitario", type=float),
        "costo_envio": request.form.get("costo_envio", type=float),
        "margen_ganancia": request.form.get("margen_ganancia", type=float),
        "url_producto": request.form.get("url_producto") or None,
        "url_imagen": request.form.get("url_imagen") or None,
        "informacion_adicional": request.form.get("informacion_adicional") or None,
        "notas_internas": request.form.get("notas_internas") or None,
    }

    detalle, error = OrdenDetalleService.update_detalle(
        id_detalle=id_detalle,
        data=data,
    )

    if error:
        flash(error, "error")
        return redirect(
            url_for(
                "admin.ordenes.detail",
                id_orden=detalle_actual.id_orden,
            )
        )

    nuevo_total, error_total = OrdenService.recalculate_total(detalle.id_orden)
    if error_total:
        flash(error_total, "error")
        return redirect(
            url_for(
                "admin.ordenes.detail_show",
                id_detalle=id_detalle,
            )
        )

    flash("Producto actualizado", "success")
    return redirect(
        url_for(
            "admin.ordenes.detail_show",
            id_detalle=id_detalle,
        )
    )


@ordenes_bp.post("/detalles/<int:id_detalle>/delete")
@login_required
@role_required("admin")
def detail_delete(id_detalle):
    detalle = OrdenDetalleService.get_by_id(id_detalle)

    if not detalle:
        flash("Producto no encontrado", "error")
        return redirect(url_for("admin.ordenes.index"))

    id_orden = detalle.id_orden

    success, error = OrdenDetalleService.delete_detalle(id_detalle)

    if not success:
        flash(error, "error")

    nuevo_total, error_total = OrdenService.recalculate_total(id_orden)
    if error_total:
        flash(error_total, "error")
        return redirect(url_for("admin.ordenes.detail", id_orden=id_orden))

    flash("Producto eliminado", "success")
    return redirect(url_for("admin.ordenes.detail", id_orden=id_orden))


@ordenes_bp.get("/<int:id_detalle>/proveedores")
@login_required
@role_required("admin")
def detail_proveedores(id_detalle):
    detalle = OrdenDetalleService.get_by_id(id_detalle)
    if not detalle:
        flash("Producto no encontrado", "error")
        return redirect(url_for("admin.ordenes.index"))

    if not detalle.clave_producto:
        flash("El producto no tiene clave SKU para buscar proveedores", "error")
        return redirect(
            url_for(
                "admin.ordenes.detail_show",
                id_detalle=id_detalle,
            )
        )

    productos, errores = BuscadorProducto.buscar(
        nombre=detalle.producto, sku=detalle.clave_producto
    )

    for error in errores:
        flash(error, "error")

    return render_template(
        "admin/proveedores.html", productos=productos, id_detalle=id_detalle
    )


@ordenes_bp.post("/<int:id_detalle>/proveedores")
@login_required
@role_required("admin")
def detail_select_proveedor(id_detalle):
    detalle = OrdenDetalleService.get_by_id(id_detalle)

    if not detalle:
        flash("Producto no encontrado", "error")
        return redirect(url_for("admin.ordenes.index"))

    existencia = request.form.get("existencia", type=int)

    if existencia is not None:
        if existencia <= 0:
            flash("El proveedor seleccionado no tiene existencia disponible", "error")
            return redirect(
                url_for(
                    "admin.ordenes.detail_show",
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
                "error",
            )
            return redirect(
                url_for(
                    "admin.ordenes.detail_show",
                    id_detalle=id_detalle,
                )
            )

    proveedor_nombre = request.form.get("proveedor")

    if not proveedor_nombre:
        flash("Proveedor no seleccionado", "error")
        return redirect(
            url_for(
                "admin.ordenes.detail_show",
                id_detalle=id_detalle,
            )
        )

    proveedor = ProveedorService.search_by_nombre(proveedor_nombre)

    if not proveedor:
        proveedor, error = ProveedorService.create({"nombre": proveedor_nombre})

    data = {"id_proveedor": proveedor.id_proveedor}

    imagen = request.form.get("url_imagen")
    if not detalle.url_imagen and imagen:
        data["url_imagen"] = imagen

    url_producto = request.form.get("url")
    if url_producto:
        data["url_producto"] = url_producto

    moneda = request.form.get("moneda")
    precio = request.form.get("precio", type=float)

    if moneda and precio is not None:
        precio_mxn, error = CurrencyService.calcular_conversion_MXN(
            precio=precio, from_currency=moneda
        )

        if error:
            flash(error, "error")
            return redirect(url_for("admin.ordenes.detail_show", id_detalle=id_detalle))

        data["precio_unitario"] = precio_mxn

    success, error = OrdenDetalleService.update_detalle(
        id_detalle=id_detalle, data=data
    )

    nuevo_total, error_total = OrdenService.recalculate_total(detalle.id_orden)

    if error_total:
        flash(f"Error al actualizar los totales: {error_total}", "error")

    if not success:
        flash(error or "No se pudo asignar el proveedor", "error")
    else:
        flash("Proveedor asignado correctamente", "success")

    return redirect(
        url_for(
            "admin.ordenes.detail_show",
            id_detalle=id_detalle,
        )
    )


@ordenes_bp.post("/<int:id_detalle>/proveedores/manual")
@login_required
@role_required("admin")
def detail_assign_proveedor_manual(id_detalle):
    detalle = OrdenDetalleService.get_by_id(id_detalle)

    if not detalle:
        flash("Producto no encontrado", "error")
        return redirect(url_for("admin.ordenes.index"))

    proveedor_nombre = request.form.get("proveedor").strip()

    if not proveedor_nombre:
        flash("El nombre del proveedor es obligatorio", "error")
        return redirect(
            url_for(
                "admin.ordenes.detail_show",
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
                    "admin.ordenes.detail_show",
                    id_detalle=id_detalle,
                )
            )

    data = {"id_proveedor": proveedor.id_proveedor}

    success, error = OrdenDetalleService.update_detalle(
        id_detalle=id_detalle, data=data
    )

    if not success:
        flash(error or "No se pudo asignar el proveedor", "error")
    else:
        flash("Proveedor asignado correctamente", "success")

    return redirect(
        url_for(
            "admin.ordenes.detail_show",
            id_detalle=id_detalle,
        )
    )


@ordenes_bp.get("/<int:id_orden>/pdf")
@login_required
@role_required("admin")
def preview_pdf(id_orden):
    orden = OrdenService.get_by_id(id_orden)
    return render_template(
        "admin/pdf_preview.html",
        orden=orden,
        pdf_url=url_for(
            "admin.ordenes.pdf_file",
            id_orden=id_orden,
        ),
    )


@ordenes_bp.get("/<int:id_orden>/pdf/file")
@login_required
@role_required("admin")
def pdf_file(id_orden):
    orden = OrdenService.get_by_id(id_orden)
    pdf = CotizacionPDFService.generar(orden)
    return send_file(
        pdf,
        mimetype="application/pdf",
        download_name=f"{orden.clave_orden}.pdf",
        as_attachment=False,
    )


@ordenes_bp.get("/<int:id_orden>/agrupaciones")
@login_required
@role_required("admin")
def agrupaciones(id_orden):
    orden = OrdenService.get_by_id(id_orden)

    agrupaciones_info, error = AgrupacionService.get_orden_complete_details(
        id_orden=id_orden
    )

    return render_template(
        "admin/agrupaciones.html",
        agrupaciones_info=agrupaciones_info,
        orden=orden,
    )


@ordenes_bp.post("/<int:id_orden>/agrupaciones/create")
@login_required
@role_required("admin")
def agrupaciones_create(id_orden):
    tipo = request.form.get("tipo", "").strip()
    detalles = request.form.getlist("detalles")

    data = {"id_orden": id_orden, "tipo": tipo, "detalles": detalles}

    agrupacion, error = AgrupacionService.create(data)

    if error:
        flash(error or "No se pudo crear la agrupacion", "error")

    return redirect(url_for("admin.ordenes.agrupaciones", id_orden=id_orden))


@ordenes_bp.post("/<int:id_orden>/agrupaciones/delete")
@login_required
@role_required("admin")
def agrupaciones_delete(id_orden):
    id_agrupacion = request.form.get("id_agrupacion", "").strip()

    _, error = AgrupacionService.delete(id_agrupacion=id_agrupacion)

    if error:
        flash(error or "No se pudo eliminar la agrupacion", "error")

    return redirect(url_for("admin.ordenes.agrupaciones", id_orden=id_orden))


@ordenes_bp.post("/<int:id_orden>/agrupaciones/update")
@login_required
@role_required("admin")
def agrupaciones_update(id_orden):
    id_agrupacion = request.form.get("id_agrupacion", "").strip()
    descripcion = request.form.get("descripcion", "").strip()
    informacion_adicional = request.form.get("informacion_adicional", "").strip()

    data = {"descripcion": descripcion, "informacion_adicional": informacion_adicional}

    agrupacion, error = AgrupacionService.update(id_agrupacion=id_agrupacion, data=data)

    if error:
        flash(error or "No se pudo actualizar la agrupacion", "error")

    return redirect(url_for("admin.ordenes.agrupaciones", id_orden=id_orden))


@ordenes_bp.post("/<int:id_orden>/agrupaciones/add_detail")
@login_required
@role_required("admin")
def agrupaciones_add_detail(id_orden):
    id_agrupacion = request.form.get("id_agrupacion", "").strip()
    id_detalle = request.form.get("id_detalle", "").strip()

    _, error = AgrupacionService.add_detalle(
        id_agrupacion=id_agrupacion, id_detalle=id_detalle
    )

    if error:
        flash(error or "No se pudo agregar el detalle", "error")

    return redirect(url_for("admin.ordenes.agrupaciones", id_orden=id_orden))


@ordenes_bp.post("/<int:id_orden>/agrupaciones/delete_detail")
@login_required
@role_required("admin")
def agrupaciones_delete_detail(id_orden):
    id_agrupacion = request.form.get("id_agrupacion", "").strip()
    id_detalle = request.form.get("id_detalle", "").strip()

    _, error = AgrupacionService.delete_detalle(
        id_agrupacion=id_agrupacion, id_detalle=id_detalle
    )

    if error:
        flash(error or "No se pudo eliminar el detalle", "error")

    return redirect(url_for("admin.ordenes.agrupaciones", id_orden=id_orden))
