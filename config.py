import os

# Space-Track credentials
SPACETRACK_USER = os.environ.get("SPACETRACK_USER", "")
SPACETRACK_PASS = os.environ.get("SPACETRACK_PASS", "")
SPACETRACK_BASE = "https://www.space-track.org"
SPACETRACK_LOGIN_URL = f"{SPACETRACK_BASE}/ajaxauth/login"
SPACETRACK_CDM_URL = f"{SPACETRACK_BASE}/basicspacedata/query/class/cdm_public"

# CelesTrak (backup TLE source, no auth)
CELESTRAK_ACTIVE_URL = "https://celestrak.org/SOCRATES/query.php"

# Anthropic
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-haiku-4-5-20251001"

# App mode
DEMO_MODE = os.environ.get("DEMO_MODE", "True").lower() == "true"

# CDM screening parameters
MISS_DISTANCE_THRESHOLD_KM = 5.0   # only fetch CDMs with miss distance < this
CONJUNCTION_WINDOW_HOURS = 72       # look-ahead window

# Probability of Collision thresholds (Space Force operational standards)
PC_CRITICAL = 1e-3    # extremely rare; immediate action
PC_HIGH = 1e-4        # maneuver consideration warranted (the "red line")
PC_MEDIUM = 1e-5      # elevated concern; coordination recommended
# Pc < PC_MEDIUM → LOW

# Miss-distance fallback thresholds when Pc is not available
MISS_HIGH_KM = 0.5
MISS_MEDIUM_KM = 2.0

# Orbital constants
EARTH_RADIUS_KM = 6371.0
MU_KM3_S2 = 398600.4418  # Earth gravitational parameter (km³/s²)

# Visualization
ORBITAL_TRACK_POINTS = 200   # points per object per orbital period shown
ORBITAL_TRACKS_PERIODS = 1.5 # how many periods to render per object

# PDF
PDF_WATERMARK = "DEMO"
