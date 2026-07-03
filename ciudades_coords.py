# ciudades_coords.py
# Traduccion "nombre de ciudad" -> coordenadas (lat, lon) para el mapa de
# burbujas del dashboard. Determinista y sin dependencias de red: es una
# "agenda de direcciones" que el dashboard consulta al dibujar el mapa.
#
# COMO SE USA:
#   resolver_coords(location, state) -> (lat, lon) | None
#
# COMO AGREGAR UNA CIUDAD NUEVA:
#   Anade una linea a CIUDADES con la clave normalizada "ciudad, st"
#   (todo en minusculas) y su (lat, lon). Para conseguir las coordenadas:
#   Google Maps -> clic derecho sobre el punto -> el primer numero que
#   aparece es lat, el segundo lon. Este archivo es codigo: agregar una
#   ciudad requiere commit + deploy (a diferencia del archivado, que es
#   runtime). Las ubicaciones cambian poco, asi que compensa la simplicidad.

from typing import Optional, Tuple

# ---------------------------------------------------------------------------
# Ciudades con coordenadas EXACTAS. Clave: "ciudad, st" en minusculas.
# Sembrado con las ubicaciones activas reales de JRS.
# ---------------------------------------------------------------------------
CIUDADES = {
    "manassas, va": (38.7509, -77.4753),
}

# ---------------------------------------------------------------------------
# Centroide aproximado de cada estado (+ DC). Fallback: si la ciudad exacta
# no esta en CIUDADES, la burbuja cae en el centro del estado correcto en
# vez de desaparecer del mapa. Cubrir los 50 estados asegura que ningun crew
# se pierda, opere donde opere. Es un dato de referencia estatico.
# ---------------------------------------------------------------------------
ESTADO_CENTROIDE = {
    "AL": (32.806, -86.791), "AK": (61.371, -152.404), "AZ": (33.730, -111.431),
    "AR": (34.970, -92.373), "CA": (36.116, -119.682), "CO": (39.060, -105.311),
    "CT": (41.598, -72.755), "DE": (39.319, -75.507), "FL": (27.766, -81.687),
    "GA": (33.041, -83.643), "HI": (21.094, -157.498), "ID": (44.240, -114.479),
    "IL": (40.349, -88.986), "IN": (39.849, -86.258), "IA": (42.012, -93.211),
    "KS": (38.527, -96.726), "KY": (37.668, -84.670), "LA": (31.170, -91.868),
    "ME": (44.694, -69.382), "MD": (39.064, -76.802), "MA": (42.230, -71.530),
    "MI": (43.327, -84.536), "MN": (45.694, -93.900), "MS": (32.742, -89.679),
    "MO": (38.456, -92.288), "MT": (46.922, -110.454), "NE": (41.125, -98.268),
    "NV": (38.314, -117.055), "NH": (43.452, -71.564), "NJ": (40.299, -74.521),
    "NM": (34.841, -106.248), "NY": (42.166, -74.948), "NC": (35.630, -79.806),
    "ND": (47.529, -99.784), "OH": (40.389, -82.765), "OK": (35.565, -96.929),
    "OR": (44.572, -122.071), "PA": (40.591, -77.210), "RI": (41.681, -71.512),
    "SC": (33.857, -80.945), "SD": (44.300, -99.439), "TN": (35.748, -86.692),
    "TX": (31.054, -97.563), "UT": (40.150, -111.862), "VT": (44.046, -72.711),
    "VA": (37.769, -78.170), "WA": (47.401, -121.490), "WV": (38.491, -80.954),
    "WI": (44.269, -89.617), "WY": (42.756, -107.302), "DC": (38.897, -77.027),
}


def resolver_coords(location: str, state: str) -> Optional[Tuple[float, float]]:
    """
    Traduce (location, state) -> (lat, lon).

    Orden de resolucion:
      1) Match exacto de la ciudad tal cual viene (p.ej. "manassas, va").
      2) Si el location no trae el estado, prueba "ciudad, st".
      3) Fallback: centroide del estado.
      4) None si no hay ciudad ni estado reconocible (se omite del mapa).
    """
    loc = (location or "").strip().lower()
    st = (state or "").strip().upper()

    # 1) match directo (el location de JRS ya suele venir como "Ciudad, ST")
    if loc in CIUDADES:
        return CIUDADES[loc]

    # 2) si el location viene sin estado, reconstruir "ciudad, st"
    if st:
        con_estado = f"{loc}, {st.lower()}"
        if con_estado in CIUDADES:
            return CIUDADES[con_estado]

    # 3) fallback al centroide del estado (burbuja en el centro del estado)
    if st in ESTADO_CENTROIDE:
        return ESTADO_CENTROIDE[st]

    # 4) sin datos suficientes
    return None
