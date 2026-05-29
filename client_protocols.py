# client_protocols.py
# Protocolos específicos por cliente Fortune 500
 
PROTOCOLS = {
    "lenscrafters": {
        "strictness": "EXTRA-STRICT",
        "environment": "medical retail",
        "key_rules": [
            "NO unplug or touch clinic / OD equipment unless authorized",
            "OD tech may be required for equipment disconnections",
            "NO paint over wallpaper: remove, skim coat, sand, paint",
            "Flooring goes under cabinets when possible",
            "Wrong ceiling tiles = serious QC issue",
            "Dust and debris are unacceptable",
            "Final photos MUST match client punchlist angles exactly",
            "Cleanliness and morning readiness are critical",
            "Medical retail = extra hygiene awareness",
        ],
        "common_issues": [
            "wallpaper improperly painted over",
            "wrong ceiling tile spec installed",
            "OD equipment moved without permission",
        ],
        "escalation_triggers": [
            "any equipment damage",
            "any dust contamination in clinic area",
            "wallpaper issues",
        ],
    },
    "lids": {
        "strictness": "STANDARD-RETAIL",
        "environment": "mall storefront",
        "key_rules": [
            "Most work after mall closing",
            "Daytime work limited to deliveries and staging",
            "Crews must NOT touch merchandise",
            "Common scope: storefront, black paint, slatwall, flooring,",
            " fixtures, ceiling tiles, lights, baseboards, cashwrap, signage",
            "Store must be clean every morning",
            "Track mall access and security restrictions",
        ],
        "common_issues": [
            "merchandise accidentally moved or damaged",
            "mall security access issues",
            "morning cleanliness gaps",
        ],
        "escalation_triggers": [
            "merchandise damage",
            "mall management complaint",
            "missed opening time",
        ],
    },
    "target": {
        "strictness": "PLAYBOOK-STRICT",
        "environment": "big-box retail",
        "key_rules": [
            "Follow playbook STRICTLY — no improvising",
            "Daily reports mandatory",
            "Photos and sign-offs required at every milestone",
            "Inventory and fixture counts must be accurate",
            "Document check-in and check-out",
        ],
        "common_issues": [
            "missing daily report",
            "photo angles don't match playbook",
            "fixture count discrepancy",
        ],
        "escalation_triggers": [
            "missed daily report",
            "fixture/inventory count mismatch",
            "any deviation from playbook",
        ],
    },
    "cvs": {
        "strictness": "EXTRA-STRICT",
        "environment": "medical retail / pharmacy",
        "key_rules": [
            "Medical retail environment",
            "Pharmacy area requires extra protocol",
            "Specific cleanliness requirements",
            "No interference with pharmacy operations",
        ],
        "common_issues": [
            "pharmacy access issues",
            "contamination risk in clinical zones",
        ],
        "escalation_triggers": [
            "pharmacy operations affected",
            "any contamination risk",
        ],
    },
}
 
def get_protocol(client_name: str) -> dict:
    """
    Devuelve el protocolo de un cliente o un protocolo default si no se encuentra.
    """
    if not client_name:
        return _default_protocol()
    key = client_name.strip().lower()
    return PROTOCOLS.get(key, _default_protocol())
 
def _default_protocol() -> dict:
    return {
        "strictness": "STANDARD",
        "environment": "general retail",
        "key_rules": [
            "Default Fortune 500 expectations apply",
            "Cleanliness, quality, documentation",
            "Formal professional tone in drafts",
        ],
        "common_issues": [],
        "escalation_triggers": ["any client complaint"],
    }
