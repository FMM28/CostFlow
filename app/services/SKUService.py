import requests
import time
from concurrent.futures import ThreadPoolExecutor, as_completed


def obtener_sku_rapido(producto: str) -> dict:
    try:
        response = requests.post(
            "http://localhost:1234/v1/chat/completions",
            json={
                "model": "qwen/qwen3.5-9b",
                "messages": [
                    {
                        "role": "user",
                        "content": producto
                    }
                ],
                "temperature": 0,
                "max_tokens": 50
            },
            timeout=20
        )

        data = response.json()

        if "choices" not in data:
            return {"producto": producto, "sku": f"ERROR: {data}"}

        sku = data["choices"][0]["message"]["content"].strip()

        return {"producto": producto, "sku": sku if sku else "NO_ENCONTRADO"}

    except Exception as e:
        return {"producto": producto, "sku": f"ERROR:{str(e)}"}

# Procesamiento en lote (paralelo controlado)
def procesar_lista_productos(productos: list, max_workers: int = 2) -> list:
    resultados = []
    # Usamos solo 2 workers para no saturar el MCP/local
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(obtener_sku_rapido, p): p for p in productos}
        for future in as_completed(futures):
            resultados.append(future.result())
            # Pequeño delay para evitar rate limiting
            time.sleep(0.5)
    return resultados

# Ejemplo de uso
productos = [
    "PROCESADOR AMD RYZEN 5 5500",
    "DISCO DURO INTERNO WD BLACK 6TB 3.5 ESCRITORIO SATA3 6GB/S 256MB 7200RPM"
]

resultados = procesar_lista_productos(productos)
for r in resultados:
    print(f"{r['producto']} → {r['sku']}")