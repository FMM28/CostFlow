from decimal import Decimal
from typing import Optional, List
import requests
from flask import current_app

from app.services.proveedores.proveedor_productos import ProveedorProductos
from app.models.producto_proveedor import ProductoProveedor, ExistenciaSucursal


class SyscomService(ProveedorProductos):
    """Servicio para consultar productos de SYSCOM vía API REST"""
    
    @classmethod
    def _get_base_url(cls) -> str:
        """Obtiene la URL base de la API de SYSCOM desde la configuración"""
        url = current_app.config.get("SYSCOM_URL")
        if not url:
            raise ValueError("La URL de SYSCOM no está configurada (SYSCOM_URL)")
        return url.rstrip('/')

    
    @classmethod
    def _get_full_url(cls, endpoint: str) -> str:
        """Construye la URL completa para acceder a la API"""
        base = cls._get_base_url()
        return f"{base}/api/v1{endpoint}"
    
    @classmethod
    def _get_access_token(cls) -> Optional[str]:
        """Obtiene el token de acceso OAuth2 usando client credentials"""
        token_url = f"{cls._get_base_url()}/oauth/token"
        client_id = current_app.config.get("SYSCOM_CLIENT_ID")
        client_secret = current_app.config.get("SYSCOM_CLIENT_SECRET")
        
        if not client_id or not client_secret:
            print("Error: SYSCOM_CLIENT_ID y SYSCOM_CLIENT_SECRET deben estar configurados")
            return None
        
        try:
            response = requests.post(
                token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": client_secret
                },
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            return data.get("access_token")
        except requests.RequestException as e:
            print(f"Error obteniendo token de SYSCOM: {e}")
            return None
    
    @classmethod
    def _get_headers(cls) -> Optional[dict]:
        """Construye los headers con el token Bearer"""
        token = cls._get_access_token()
        if not token:
            return None
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json"
        }
    
    @classmethod
    def _buscar_producto(cls, nombre: str | None, sku: str | None) -> Optional[dict]:
        """
        Busca un producto por su nombre o SKU en SYSCOM.
        """
        headers = cls._get_headers()
        if not headers:
            return None
        
        url = cls._get_full_url("/productos")
        
        params = {
            "busqueda": f'{nombre} + {sku}',
            "pagina": 1
        }
        
        # print(requests.get(cls._get_full_url("/tipocambio"), headers=cls._get_headers()).text)
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=(5,20))
            response.raise_for_status()
            data = response.json()
            
            productos = data.get("productos", [])
            
            if productos:
                for producto in productos:
                    print(producto.get("modelo", ""), sku)
                    if producto.get("modelo", "").strip().upper() == sku.strip().upper():
                        return producto
            
            return None
            
        except requests.RequestException as e:
            print(f"Error buscando SKU '{sku}' en SYSCOM: {e}")
            return None
    
    @classmethod
    def _parse_existencias(cls, data: dict) -> tuple[int, List[ExistenciaSucursal]]:
        """Parsea las existencias por sucursal del producto"""
        existencias_sucursal = []
        existencia_total = 0
        
        existencia_data = data.get("existencia", {})
        
        for sucursal, cantidad in existencia_data.items():
            if isinstance(cantidad, (int, float)):
                cantidad_int = int(cantidad)
                existencias_sucursal.append(
                    ExistenciaSucursal(
                        sucursal=sucursal.upper().replace("_", " "),
                        existencia=cantidad_int
                    )
                )
                existencia_total += cantidad_int
        
        return existencia_total, existencias_sucursal
    
    @classmethod
    def _parse_precios(cls, data: dict) -> tuple[Decimal, Optional[Decimal], str]:
        """Parsea los precios del producto"""
        precios = data.get("precios", {})
        
        precio_lista = Decimal(str(precios.get("precio_lista", 0)))
        
        precio_especial = precios.get("precio_especial")
        precio_descuento = precios.get("precio_descuento")
        
        descuento = None
        if precio_especial is not None:
            descuento = Decimal(str(precio_especial))
        if precio_descuento is not None:
            descuento_d = Decimal(str(precio_descuento))
            if descuento is None or descuento_d < descuento:
                descuento = descuento_d
        
        moneda = "USD"
        return precio_lista, descuento, moneda
    
    @classmethod
    def _get_imagen_principal(cls, data: dict) -> Optional[str]:
        """Obtiene la URL de la imagen principal del producto"""
        img_portada = data.get("img_portada")
        if img_portada:
            return img_portada
        
        imagenes = data.get("imagenes", [])
        if imagenes and len(imagenes) > 0:
            return imagenes[0].get("url")
        
        return None
    
    @classmethod
    def buscar_producto(cls, nombre: str | None = None, sku: str | None = None) -> Optional[ProductoProveedor]:
        """
        Busca un producto por su SKU en SYSCOM.
        """
        if not sku and not nombre:
            return None
        
        
        data = cls._buscar_producto(nombre,sku)
        
        if not data:
            print(f"No se encontró producto con SKU '{sku}' en SYSCOM")
            return None
        
        existencia_total, existencias_sucursal = cls._parse_existencias(data)
        precio, descuento, moneda = cls._parse_precios(data)
        
        url_producto = data.get("link")
        if url_producto:
            base_store = cls._get_base_url()
            url_producto = f"{base_store}{url_producto}"
        
        producto = ProductoProveedor(
            proveedor="SYSCOM",
            nombre=data.get("titulo") or data.get("modelo") or "",
            precio=precio,
            moneda=moneda,
            existencia=existencia_total,
            descuento=descuento,
            existencias_sucursal=existencias_sucursal,
            url=url_producto,
            url_imagen=cls._get_imagen_principal(data)
        )
        
        return producto