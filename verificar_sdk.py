# verificar_sdk.py
# Prueba mínima de que el Claude Agent SDK está instalado
 
try:
    import claude_agent_sdk
    print("✅ Claude Agent SDK importado correctamente")
    print(f"   Versión instalada: {claude_agent_sdk.__version__}")
except ImportError as e:
    print("❌ ERROR: el SDK no está instalado")
    print(f"   Detalle: {e}")
    print("   Ejecuta: pip install claude-agent-sdk")
