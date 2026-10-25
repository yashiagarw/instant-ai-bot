"""Car features that some faults need (a start-stop battery fault needs start-stop). The catalogue records them per
model or variant as true / false; a feature missing from the file is unknown, and unknown never changes a ranking.

Fuel and gearbox needs use the variant's own fuel and transmission, not this list.
"""

# code -> how a customer reads it ("Your car doesn't have <label>")
FEATURES: dict[str, str] = {
    "start_stop": "automatic engine start-stop",
    "mild_hybrid": "a mild-hybrid starter-generator",
    "smart_key": "a smart key with push-button start",
    "epb": "an electronic parking brake",
    "auto_hold": "hill-hold or auto-hold",
    "turbo": "a turbo engine",
    "esp": "electronic stability control (ESP)",
    "tpms": "tyre pressure monitoring (TPMS)",
    "direct_injection": "a direct-injection petrol engine",
    "plug_in": "plug-in charging",
}

FUEL_LABELS = {"petrol": "petrol", "diesel": "diesel", "cng": "CNG", "hybrid": "hybrid", "ev": "electric"}
TRANSMISSION_LABELS = {
    "mt": "a manual gearbox",
    "amt": "an AMT gearbox",
    "cvt": "a CVT automatic",
    "dct": "a DCT automatic",
    "at": "an automatic gearbox",
}


def requirement_label(kind: str, values: list[str] | str) -> str:
    """What a fault needs, in words: "automatic engine start-stop", "a diesel engine", "an automatic gearbox"."""
    if kind == "feature":
        return FEATURES.get(str(values), str(values).replace("_", " "))
    vals = [values] if isinstance(values, str) else list(values)
    if kind == "fuel":
        return " or ".join(FUEL_LABELS.get(v, v) for v in vals) + (" engine" if vals != ["ev"] else " drive")
    if kind == "transmission":
        if set(vals) >= {"amt", "cvt", "dct", "at"}:
            return "an automatic or AMT gearbox"
        return " or ".join(TRANSMISSION_LABELS.get(v, v) for v in vals)
    return kind
