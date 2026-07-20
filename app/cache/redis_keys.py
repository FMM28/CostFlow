class RedisKeys:
    PREFIX = "costflow"

    PRODUCTOS = f"{PREFIX}:productos"
    TIPO_CAMBIO = f"{PREFIX}:tipo_cambio"
    SESSION = f"{PREFIX}:session"

    @classmethod
    def producto(cls, sku: str) -> str:
        return f"{cls.PRODUCTOS}:{sku.strip().upper()}"

    @classmethod
    def tipo_cambio(cls, moneda: str) -> str:
        return f"{cls.TIPO_CAMBIO}:{moneda.strip().upper()}"
    
    @classmethod
    def session(cls, proveedor: str) -> str:
        return f"{cls.SESSION}:{proveedor.strip().upper()}"