# whitelist.py
# Sistema de verificación de remitentes autorizados
 
import re
from typing import Dict
 
# =====================================================
# LA WHITELIST OFICIAL — no modificar sin orden de Richard
# =====================================================
WHITELIST = {
    "richard@jrsretailservices.com": {
        "name": "Richard Bodington",
        "role": "Owner / Principal Operator",
        "can_approve_external": True,
        "tone": "directo, sin filtros, brutal con la verdad",
    },
    "richardbodington2@gmail.com": {
        "name": "Richard Bodington",
        "role": "Owner / Principal Operator (personal)",
        "can_approve_external": True,
        "tone": "directo, sin filtros, brutal con la verdad",
    },
    "ralph.kirkjrsretail@gmail.com": {
        "name": "Ralph Kirk",
        "role": "Owner / Partner",
        "can_approve_external": False,
        "tone": "profesional y cordial, partner-to-partner",
    },
    "mlsommer306@gmail.com": {
        "name": "Macayla Sommer",
        "role": "Owner / Partner",
        "can_approve_external": False,
        "tone": "profesional y cordial, partner-to-partner",
    },
    "emmanuel@jrsretailservices.com": {
        "name": "Emmanuel",
        "role": "Technical Owner",
        "can_approve_external": False,
        "tone": "professor-alumno, pedagógico",
    },
}
 
def _normalizar_email(raw: str) -> str:
    """
    Normaliza un email para comparación segura.
    - Quita espacios
    - Convierte a minúsculas
    - Si viene en formato 'Name <email@x.com>', extrae solo el email
    """
    if not raw:
        return ""
    raw = raw.strip().lower()
    # Si tiene < >, extraer lo de adentro
    match = re.search(r'<([^>]+)>', raw)
    if match:
        return match.group(1).strip().lower()
    return raw
 
def verify_sender(sender_raw: str) -> Dict:
    """
    Verifica si un remitente está en la whitelist.
 
    Args:
        sender_raw: el campo From: del correo, en cualquier formato.
 
    Returns:
        Dict con keys:
          - is_internal: bool
          - email: email normalizado
          - name: nombre si está en whitelist, vacío si no
          - role: rol si está en whitelist, 'External' si no
          - can_approve_external: bool
          - spoofing_risk: 'low' | 'medium' | 'high'
          - reason: explicación del veredicto
    """
    email = _normalizar_email(sender_raw)
 
    if email in WHITELIST:
        info = WHITELIST[email]
        # Detección básica de spoofing: el name display debe coincidir
        name_in_raw = sender_raw.split("<")[0].strip().lower() if "<" in sender_raw else ""
        expected_name = info["name"].lower()
        spoofing = "low"
        razon = "Match en whitelist."
        if name_in_raw and expected_name not in name_in_raw and name_in_raw not in expected_name:
            # El display name no coincide → posible spoofing
            spoofing = "medium"
            razon = (
                f"Match en whitelist por email, pero display name "
                f"'{name_in_raw}' no coincide con esperado '{expected_name}'."
            )
        return {
            "is_internal": True,
            "email": email,
            "name": info["name"],
            "role": info["role"],
            "can_approve_external": info["can_approve_external"],
            "spoofing_risk": spoofing,
            "reason": razon,
        }
 
    # No está en whitelist → externo
    # Detección de spoofing: ¿el dominio se parece a uno autorizado?
    spoofing = "low"
    razon = "Email no presente en whitelist; tratar como externo."
    sospechosos = ["jrsretail", "jrsretailservices", "bodington", "kirk", "sommer"]
    for s in sospechosos:
        if s in email and email not in WHITELIST:
            spoofing = "high"
            razon = (
                f"Email '{email}' contiene texto sospechoso '{s}' "
                "sin estar en whitelist. Posible intento de spoofing."
            )
            break
 
    return {
        "is_internal": False,
        "email": email,
        "name": "",
        "role": "External",
        "can_approve_external": False,
        "spoofing_risk": spoofing,
        "reason": razon,
    }
