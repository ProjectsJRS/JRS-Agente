# crear_colecciones.py
import chromadb

cliente = chromadb.PersistentClient(path="./chroma_data")

COLECCIONES = [
    ("building_codes",        "IBC, IFC, IPC, IECC, IMC"),
    ("safety_codes",          "NFPA 101, NFPA 1, NFPA 13, NFPA 70, NFPA 72"),
    ("accessibility",         "ADA Standards 2010, ICC A117.1"),
    ("osha_safety",           "OSHA 29 CFR 1926 y 1910"),
    ("aia_contracts",         "AIA A101, A102, A201, A401, G702, G703, etc."),
    ("state_amendments",      "Enmiendas estatales y municipales"),
    ("construction_methods",  "Métodos modernos: modular, overnight, fast-track"),
    ("estimating_data",       "RSMeans benchmarks, regional cost data"),
]

for nombre, descripcion in COLECCIONES:
    coleccion = cliente.get_or_create_collection(
        name=nombre,
        metadata={"description": descripcion},
    )
    print(f"✅ Colección '{nombre}' lista — {descripcion}")

print(f"\n📚 Total de colecciones creadas: {len(COLECCIONES)}")