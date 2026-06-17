from config import PC_CRITICAL, PC_HIGH, PC_MEDIUM, MISS_HIGH_KM, MISS_MEDIUM_KM


def categorize_pc(pc, miss_distance_km: float) -> str:
    """Return risk level string. Falls back to miss distance if Pc is unavailable."""
    if pc is not None:
        if pc >= PC_CRITICAL:
            return "CRITICAL"
        if pc >= PC_HIGH:
            return "HIGH"
        if pc >= PC_MEDIUM:
            return "MEDIUM"
        return "LOW"
    # Pc not available — use miss distance proxy
    if miss_distance_km < MISS_HIGH_KM:
        return "HIGH"
    if miss_distance_km < MISS_MEDIUM_KM:
        return "MEDIUM"
    return "LOW"


def compute_risk_score(pc, miss_distance_km: float, relative_speed_km_s: float) -> float:
    """
    Deterministic 0–100 risk score.

    Component weights:
      Pc (or miss-distance proxy)  — 50 pts
      Miss distance                — 30 pts
      Relative speed               — 20 pts
    """
    # Pc component (50 pts)
    if pc is not None:
        if pc >= PC_CRITICAL:
            pc_pts = 50.0
        elif pc >= PC_HIGH:
            pc_pts = 40.0
        elif pc >= PC_MEDIUM:
            pc_pts = 25.0
        else:
            # Log-scale within LOW range: 0–15 pts
            import math
            if pc > 0:
                # map [1e-7, 1e-5) → [0, 15]
                pc_pts = max(0.0, min(15.0, 15.0 * (math.log10(pc) + 7) / 2.0))
            else:
                pc_pts = 0.0
    else:
        # Fallback from miss distance for Pc component
        if miss_distance_km < MISS_HIGH_KM:
            pc_pts = 35.0
        elif miss_distance_km < MISS_MEDIUM_KM:
            pc_pts = 20.0
        else:
            pc_pts = 5.0

    # Miss distance component (30 pts): 5 km = 0, 0 km = 30
    miss_pts = max(0.0, min(30.0, 30.0 * (1.0 - miss_distance_km / 5.0)))

    # Relative speed component (20 pts): collision energy ∝ v²
    # Typical LEO relative speeds 0–15 km/s; normalise at 15
    speed_pts = max(0.0, min(20.0, 20.0 * (relative_speed_km_s / 15.0)))

    return round(pc_pts + miss_pts + speed_pts, 1)


def format_pc(pc) -> str:
    """Human-readable Pc string."""
    if pc is None:
        return "N/A"
    if pc == 0.0:
        return "< 1×10⁻⁷"
    import math
    exp = int(math.floor(math.log10(pc)))
    mantissa = pc / (10 ** exp)
    return f"{mantissa:.1f}×10{superscript(exp)}"


def superscript(n: int) -> str:
    mapping = str.maketrans("-0123456789", "⁻⁰¹²³⁴⁵⁶⁷⁸⁹")
    return str(n).translate(mapping)


def risk_css_class(level: str) -> str:
    return {
        "CRITICAL": "risk-critical",
        "HIGH": "risk-high",
        "MEDIUM": "risk-medium",
        "LOW": "risk-low",
    }.get(level, "risk-low")


def object_type_label(obj_type: str) -> str:
    mapping = {
        "PAYLOAD": "Active Payload",
        "ROCKET BODY": "Rocket Body",
        "DEBRIS": "Debris",
        "UNKNOWN": "Unknown",
    }
    return mapping.get(obj_type.upper(), obj_type)
