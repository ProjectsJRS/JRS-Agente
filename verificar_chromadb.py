# verificar_chromadb.py
try:
    import chromadb
    print(f"✅ ChromaDB instalado, versión: {chromadb.__version__}")

    # Crear cliente persistente (datos guardados en disco)
    cliente = chromadb.PersistentClient(path="./chroma_data")
    print("✅ Cliente persistente creado en ./chroma_data")

    # Crear o obtener una colección de prueba
    coleccion = cliente.get_or_create_collection(name="prueba_jrs")
    print(f"✅ Colección 'prueba_jrs' creada/obtenida")

    # Insertar un documento de prueba
    coleccion.add(
        documents=["This is a test document about ceiling height for retail."],
        ids=["prueba-001"],
        metadatas=[{"source": "test", "topic": "ceiling"}],
    )
    print("✅ Documento de prueba insertado")

    # Hacer una query semántica
    resultados = coleccion.query(
        query_texts=["how tall must a retail ceiling be?"],
        n_results=1,
    )
    print(f"✅ Query exitosa. Resultado: {resultados['documents'][0][0][:80]}...")

    print("\n🎉 ChromaDB funciona perfectamente en tu computadora.")

except Exception as e:
    print(f"❌ ERROR: {e}")