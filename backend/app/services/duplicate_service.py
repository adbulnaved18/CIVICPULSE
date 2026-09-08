import re
import unicodedata

# ============================================================
# DUPLICATE DETECTION CONFIGURATION
# ============================================================

# Normal text similarity threshold.
DUPLICATE_SIMILARITY_THRESHOLD = 0.45

# Used when category + location are both the same.
SAME_CONTEXT_THRESHOLD = 0.22

# Extremely similar descriptions can be duplicates even when
# location formatting differs.
HIGH_SIMILARITY_THRESHOLD = 0.72

# Strong contextual duplicate threshold.
CORE_ISSUE_CONTEXT_THRESHOLD = 0.15


# ============================================================
# STOP WORDS
# ============================================================

STOP_WORDS = {
    "a",
    "an",
    "the",
    "is",
    "are",
    "was",
    "were",
    "has",
    "have",
    "had",
    "near",
    "nearby",
    "at",
    "in",
    "on",
    "of",
    "for",
    "to",
    "from",
    "with",
    "and",
    "or",
    "this",
    "that",
    "there",
    "here",
    "very",
    "also",
    "into",
    "by",
    "as",
    "it",
    "its",
    "be",
    "been",
    "being",
    "due",
    "because",
    "which",
    "who",
    "where",
    "when",
    "close",
    "around",
    "through",
    "over",
    "under",
    "up",
    "down",
}


# ============================================================
# CIVIC SYNONYMS
# ============================================================

SYNONYM_MAP = {

    # --------------------------------------------------------
    # Roads / potholes
    # --------------------------------------------------------

    "potholes": "pothole",
    "pot hole": "pothole",
    "road damage": "pothole",
    "road damaged": "pothole",
    "damaged road": "pothole",
    "broken road": "pothole",
    "road crack": "pothole",
    "road cracks": "pothole",

    # --------------------------------------------------------
    # Junction / intersection
    # --------------------------------------------------------

    "junction": "intersection",
    "junctions": "intersection",
    "crossroad": "intersection",
    "crossroads": "intersection",
    "cross road": "intersection",
    "cross roads": "intersection",

    # --------------------------------------------------------
    # Vehicle terminology
    # --------------------------------------------------------

    "vehicles": "vehicle",
    "cars": "vehicle",
    "car": "vehicle",
    "automobiles": "vehicle",
    "automobile": "vehicle",
    "drivers": "driver",

    # --------------------------------------------------------
    # Pedestrians
    # --------------------------------------------------------

    "pedestrians": "pedestrian",
    "people walking": "pedestrian",
    "walkers": "pedestrian",

    # --------------------------------------------------------
    # Garbage / waste
    # --------------------------------------------------------

    "garbage": "waste",
    "trash": "waste",
    "rubbish": "waste",
    "wastes": "waste",
    "dumping": "waste",
    "waste disposal": "waste",
    "waste collection": "waste",

    # --------------------------------------------------------
    # Streetlights / electricity
    # --------------------------------------------------------

    "street light": "streetlight",
    "street lights": "streetlight",
    "street lighting": "streetlight",
    "lighting": "streetlight",
    "light pole": "streetlight",
    "light poles": "streetlight",

    "electricity": "power",
    "electrical": "power",
    "power supply": "power",
    "power outage": "outage",
    "blackout": "outage",

    # --------------------------------------------------------
    # Water
    # --------------------------------------------------------

    "water leakage": "water leak",
    "water leakages": "water leak",
    "pipe leakage": "water leak",
    "pipeline leakage": "water leak",
    "water shortage": "water shortage",

    # --------------------------------------------------------
    # Drainage
    # --------------------------------------------------------

    "water logging": "waterlogging",
    "waterlogged": "waterlogging",
    "flooding": "flood",
    "drain blockage": "blocked drain",
    "blocked drainage": "blocked drain",
    "drain blocked": "blocked drain",

    # --------------------------------------------------------
    # Public transport
    # --------------------------------------------------------

    "bus stop": "busstop",
    "bus stops": "busstop",
    "public transport": "transport",
    "public transportation": "transport",

    # --------------------------------------------------------
    # Cleanliness
    # --------------------------------------------------------

    "cleanliness": "clean",
    "cleaning": "clean",
    "dirty": "cleanliness",
    "hygiene": "cleanliness",

    # --------------------------------------------------------
    # Footpaths
    # --------------------------------------------------------

    "sidewalk": "footpath",
    "sidewalks": "footpath",
    "pavement": "footpath",
    "pavements": "footpath",

    # --------------------------------------------------------
    # Traffic
    # --------------------------------------------------------

    "traffic jam": "traffic",
    "traffic jams": "traffic",
    "congestion": "traffic",

    # --------------------------------------------------------
    # Animals
    # --------------------------------------------------------

    "stray dogs": "stray animal",
    "stray dog": "stray animal",
    "stray cattle": "stray animal",
    "stray cows": "stray animal",
}


# ============================================================
# CORE CIVIC ISSUE TERMS
#
# These are strong signals that two complaints are about
# the same underlying civic problem.
# ============================================================

CORE_ISSUE_TERMS = {
    "pothole",
    "intersection",
    "vehicle",
    "driver",
    "footpath",
    "pedestrian",
    "waste",
    "streetlight",
    "power",
    "outage",
    "water",
    "leak",
    "shortage",
    "waterlogging",
    "flood",
    "blocked",
    "drain",
    "busstop",
    "transport",
    "traffic",
    "cleanliness",
    "stray",
    "animal",
    "park",
    "pollution",
}


# ============================================================
# TEXT CLEANING
# ============================================================

def clean_text(text: str) -> str:
    """
    Normalize unicode, lowercase text, remove punctuation,
    and normalize whitespace.
    """

    if not text:
        return ""

    text = str(text)

    text = unicodedata.normalize(
        "NFKD",
        text,
    )

    text = text.encode(
        "ascii",
        "ignore",
    ).decode("ascii")

    text = text.lower()

    text = text.replace(
        "&",
        " and ",
    )

    text = re.sub(
        r"[^a-z0-9\s]",
        " ",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


# ============================================================
# SYNONYM NORMALIZATION
# ============================================================

def apply_synonyms(text: str) -> str:
    """
    Convert common civic phrases into canonical terms.

    Examples:

        junction -> intersection
        vehicles -> vehicle
        garbage -> waste
        sidewalk -> footpath
    """

    normalized = clean_text(text)

    if not normalized:
        return ""

    replacements = sorted(
        SYNONYM_MAP.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    )

    for source, target in replacements:

        normalized = re.sub(
            rf"\b{re.escape(source)}\b",
            target,
            normalized,
        )

    return normalized


# ============================================================
# TOKEN NORMALIZATION
# ============================================================

def normalize_tokens(text: str) -> set:
    """
    Convert text into meaningful canonical tokens.
    """

    normalized = apply_synonyms(text)

    if not normalized:
        return set()

    tokens = normalized.split()

    meaningful_tokens = set()

    for token in tokens:

        if token in STOP_WORDS:
            continue

        # Common plural normalization.
        if (
            len(token) > 4
            and token.endswith("ies")
        ):
            token = token[:-3] + "y"

        elif (
            len(token) > 4
            and token.endswith("es")
        ):
            token = token[:-2]

        elif (
            len(token) > 4
            and token.endswith("s")
        ):
            token = token[:-1]

        meaningful_tokens.add(token)

    return meaningful_tokens


# ============================================================
# CORE ISSUE EXTRACTION
# ============================================================

def extract_core_issues(text: str) -> set:
    """
    Extract strong civic-problem tokens from a description.
    """

    tokens = normalize_tokens(text)

    return {
        token
        for token in tokens
        if token in CORE_ISSUE_TERMS
    }


# ============================================================
# JACCARD SIMILARITY
# ============================================================

def jaccard_similarity(
    tokens1: set,
    tokens2: set,
) -> float:

    if not tokens1 or not tokens2:
        return 0.0

    intersection = tokens1.intersection(
        tokens2
    )

    union = tokens1.union(
        tokens2
    )

    if not union:
        return 0.0

    return (
        len(intersection) /
        len(union)
    )


# ============================================================
# CONTAINMENT SIMILARITY
# ============================================================

def containment_similarity(
    tokens1: set,
    tokens2: set,
) -> float:

    if not tokens1 or not tokens2:
        return 0.0

    smaller = min(
        len(tokens1),
        len(tokens2),
    )

    if smaller == 0:
        return 0.0

    intersection = len(
        tokens1.intersection(tokens2)
    )

    return intersection / smaller


# ============================================================
# PHRASE SIMILARITY
# ============================================================

def phrase_similarity(
    text1: str,
    text2: str,
) -> float:
    """
    Compare canonical two-word phrases.
    """

    normalized1 = apply_synonyms(text1)
    normalized2 = apply_synonyms(text2)

    if not normalized1 or not normalized2:
        return 0.0

    words1 = normalized1.split()
    words2 = normalized2.split()

    if len(words1) < 2 or len(words2) < 2:
        return 0.0

    bigrams1 = {
        f"{words1[i]} {words1[i + 1]}"
        for i in range(len(words1) - 1)
    }

    bigrams2 = {
        f"{words2[i]} {words2[i + 1]}"
        for i in range(len(words2) - 1)
    }

    return jaccard_similarity(
        bigrams1,
        bigrams2,
    )


# ============================================================
# TEXT SIMILARITY
# ============================================================

def text_similarity(
    text1: str,
    text2: str,
) -> float:
    """
    Combined lightweight similarity score.

    Uses:
        - Jaccard token similarity
        - containment similarity
        - phrase similarity
    """

    tokens1 = normalize_tokens(text1)
    tokens2 = normalize_tokens(text2)

    if not tokens1 or not tokens2:
        return 0.0

    jaccard = jaccard_similarity(
        tokens1,
        tokens2,
    )

    containment = containment_similarity(
        tokens1,
        tokens2,
    )

    phrase = phrase_similarity(
        text1,
        text2,
    )

    score = (
        jaccard * 0.45
        + containment * 0.40
        + phrase * 0.15
    )

    return round(
        min(
            max(score, 0.0),
            1.0,
        ),
        4,
    )


# ============================================================
# CATEGORY NORMALIZATION
# ============================================================

def normalize_category(
    category: str,
) -> str:

    value = clean_text(
        category
    )

    if not value:
        return ""

    if (
        "road" in value
        or "pothole" in value
        or "footpath" in value
        or "pedestrian" in value
    ):
        return "road"

    if (
        "drainage" in value
        or "waterlogging" in value
        or "flood" in value
    ):
        return "drainage"

    if (
        "water supply" in value
        or value == "water"
    ):
        return "water"

    if (
        "streetlight" in value
        or "electricity" in value
        or "electric" in value
        or "power" in value
    ):
        return "electric"

    if (
        "sanitation" in value
        or "waste" in value
        or "garbage" in value
        or "hygiene" in value
    ):
        return "sanitation"

    if (
        "environment" in value
        or "pollution" in value
    ):
        return "environment"

    if (
        "park" in value
        or "public space" in value
    ):
        return "parks"

    if (
        "traffic" in value
        or "transport" in value
    ):
        return "traffic"

    if "animal" in value:
        return "animals"

    if "health" in value:
        return "health"

    if "infrastructure" in value:
        return "infrastructure"

    return value


# ============================================================
# LOCATION NORMALIZATION
# ============================================================

def normalize_location(
    location: str,
) -> str:

    normalized = clean_text(
        location
    )

    if not normalized:
        return ""

    normalized = apply_synonyms(
        normalized
    )

    filler_words = {
        "near",
        "nearby",
        "at",
        "opposite",
        "beside",
        "behind",
        "outside",
        "front",
        "road",
        "street",
    }

    tokens = [
        token
        for token in normalized.split()
        if token not in filler_words
    ]

    return " ".join(
        tokens
    ).strip()


# ============================================================
# LOCATION SIMILARITY
# ============================================================

def location_similarity(
    location1: str,
    location2: str,
) -> float:

    normalized1 = normalize_location(
        location1
    )

    normalized2 = normalize_location(
        location2
    )

    if not normalized1 or not normalized2:
        return 0.0

    if normalized1 == normalized2:
        return 1.0

    tokens1 = set(
        normalized1.split()
    )

    tokens2 = set(
        normalized2.split()
    )

    jaccard = jaccard_similarity(
        tokens1,
        tokens2,
    )

    containment = containment_similarity(
        tokens1,
        tokens2,
    )

    return round(
        (
            jaccard * 0.5
            + containment * 0.5
        ),
        4,
    )


# ============================================================
# DUPLICATE SCORE
# ============================================================

def calculate_duplicate_score_legacy(
    new_description: str,
    existing_description: str,
    new_category: str,
    existing_category: str,
    new_location: str,
    existing_location: str,
) -> dict:

    # --------------------------------------------------------
    # TEXT
    # --------------------------------------------------------

    text_score = text_similarity(
        new_description,
        existing_description,
    )

    # --------------------------------------------------------
    # CATEGORY
    # --------------------------------------------------------

    category1 = normalize_category(
        new_category
    )

    category2 = normalize_category(
        existing_category
    )

    same_category = (
        bool(category1)
        and bool(category2)
        and category1 == category2
    )

    # --------------------------------------------------------
    # LOCATION
    # --------------------------------------------------------

    location_score = location_similarity(
        new_location,
        existing_location,
    )

    same_location = (
        location_score >= 0.75
    )

    # --------------------------------------------------------
    # CORE ISSUE
    # --------------------------------------------------------

    core_issues1 = extract_core_issues(
        new_description
    )

    core_issues2 = extract_core_issues(
        existing_description
    )

    shared_core_issues = (
        core_issues1.intersection(
            core_issues2
        )
    )

    has_shared_core_issue = (
        len(shared_core_issues) > 0
    )

    # --------------------------------------------------------
    # CONTEXT SCORE
    # --------------------------------------------------------

    score = text_score

    if same_category:
        score += 0.15

    if same_location:
        score += 0.20

    if has_shared_core_issue:
        score += 0.15

    score = min(
        max(score, 0.0),
        1.0,
    )

    # --------------------------------------------------------
    # DUPLICATE DECISION
    # --------------------------------------------------------

    is_duplicate = False

    # CASE 1:
    # Same category + same location + same core issue.
    #
    # This is our strongest civic-context rule.
    #
    # Example:
    #
    # Complaint A:
    # "Large pothole near busy intersection..."
    #
    # Complaint B:
    # "Deep pothole near main junction..."
    #
    # Both:
    #   category = Roads & Potholes
    #   location = same
    #   core issue = pothole
    #
    # => duplicate
    #
    if (
        same_category
        and same_location
        and has_shared_core_issue
    ):
        is_duplicate = True

    # CASE 2:
    # Same category + same location with reasonable text
    # similarity.
    elif (
        same_category
        and same_location
        and text_score >= SAME_CONTEXT_THRESHOLD
    ):
        is_duplicate = True

    # CASE 3:
    # Very strong text similarity even when location wording
    # differs slightly.
    elif text_score >= HIGH_SIMILARITY_THRESHOLD:
        is_duplicate = True

    # CASE 4:
    # General weighted score.
    elif score >= DUPLICATE_SIMILARITY_THRESHOLD:
        is_duplicate = True

    return {
        "score": round(
            score,
            2,
        ),

        "text_similarity": round(
            text_score,
            2,
        ),

        "location_similarity": round(
            location_score,
            2,
        ),

        "same_category": same_category,

        "same_location": same_location,

        "shared_core_issues": sorted(
            shared_core_issues
        ),

        "is_duplicate": is_duplicate,
    }


# ============================================================
# PRIORITY
# ============================================================

def calculate_priority(
    votes,
    status,
):

    if status == "Resolved":
        return 0

    if status == "In Progress":
        return votes + 5

    return votes


# ============================================================
# FIND DUPLICATE COMPLAINTS
# ============================================================

def find_duplicate_matches_legacy(
    db,
    category: str,
    location: str,
    description: str,
):
    cursor = db.cursor()

    cursor.execute(
        """
        SELECT
            c.id,
            c.description,
            c.category,
            c.state,
            c.location,
            c.language,
            c.status,
            COUNT(v.id) AS votes
        FROM complaints c
        LEFT JOIN complaint_votes v
            ON c.id = v.complaint_id
        GROUP BY
            c.id,
            c.description,
            c.category,
            c.state,
            c.location,
            c.language,
            c.status
        ORDER BY c.id DESC
        """
    )

    rows = cursor.fetchall()

    matches = []

    for row in rows:

        existing_id = row[0]
        existing_description = row[1]
        existing_category = row[2]
        existing_state = row[3]
        existing_location = row[4]
        existing_language = row[5]
        existing_status = row[6]
        votes = row[7] or 0

        duplicate_score = calculate_duplicate_score_legacy(
            new_description=description,
            existing_description=existing_description,
            new_category=category,
            existing_category=existing_category,
            new_location=location,
            existing_location=existing_location,
        )

        if duplicate_score["is_duplicate"]:

            matches.append({
                "id": existing_id,

                "description": existing_description,

                "category": existing_category,

                "state": existing_state,

                "location": existing_location,

                "language": existing_language,

                "status": existing_status,

                "votes": votes,

                "similarity": duplicate_score[
                    "score"
                ],

                "text_similarity": duplicate_score[
                    "text_similarity"
                ],

                "location_similarity": duplicate_score[
                    "location_similarity"
                ],

                "same_category": duplicate_score[
                    "same_category"
                ],

                "same_location": duplicate_score[
                    "same_location"
                ],

                "shared_core_issues": duplicate_score[
                    "shared_core_issues"
                ],
            })

    # --------------------------------------------------------
    # SORT
    #
    # 1. Unresolved complaints first
    # 2. Highest similarity
    # 3. Highest support
    # 4. Newest complaint
    # --------------------------------------------------------

    matches.sort(
        key=lambda complaint: (
            1
            if complaint["status"] == "Resolved"
            else 0,

            -complaint["similarity"],

            -complaint["votes"],

            -complaint["id"],
        )
    )

    return matches


import json as _json_mod
import logging
import os

logger = logging.getLogger(__name__)

# ============================================================
# VECTOR DUPLICATE DETECTION CONFIG
# ============================================================

VECTOR_SIMILARITY_THRESHOLD: float = float(os.environ.get("VECTOR_SIMILARITY_THRESHOLD", "0.80"))
VECTOR_TOP_K: int = int(os.environ.get("VECTOR_TOP_K", "20"))
GEO_RADIUS_METERS: int = int(os.environ.get("DUPLICATE_SEARCH_RADIUS_METERS", "500"))
LLM_VERIFY_LOW: float = float(os.environ.get("LLM_VERIFY_LOW", "0.75"))
LLM_VERIFY_HIGH: float = float(os.environ.get("LLM_VERIFY_HIGH", "0.90"))
W_SEMANTIC = 0.60
W_GEO      = 0.25
W_CATEGORY = 0.10
W_RECENCY  = 0.05
DUPLICATE_USE_VECTOR: bool = os.environ.get("DUPLICATE_USE_VECTOR", "false").lower() == "true"
DUPLICATE_SHADOW_MODE: bool = os.environ.get("DUPLICATE_SHADOW_MODE", "false").lower() == "true"


def _cosine_similarity(a: list, b: list) -> float:
    try:
        dot = sum(x * y for x, y in zip(a, b))
        mag_a = sum(x * x for x in a) ** 0.5
        mag_b = sum(x * x for x in b) ** 0.5
        if mag_a == 0 or mag_b == 0:
            return 0.0
        return dot / (mag_a * mag_b)
    except Exception:
        return 0.0


def _recency_score(created_at_str) -> float:
    try:
        from datetime import datetime
        if created_at_str is None:
            return 0.5
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            try:
                dt = datetime.strptime(str(created_at_str)[:19], fmt)
                break
            except ValueError:
                continue
        else:
            return 0.5
        age_days = max((datetime.now() - dt).days, 0)
        return max(0.0, 1.0 - age_days / 90.0)
    except Exception:
        return 0.5


def calculate_hybrid_score(semantic_sim, geo_score, same_category, recency_score) -> float:
    score = (
        semantic_sim  * W_SEMANTIC
        + geo_score   * W_GEO
        + (1.0 if same_category else 0.0) * W_CATEGORY
        + recency_score * W_RECENCY
    )
    return round(min(max(score, 0.0), 1.0), 4)


# ============================================================
# VECTOR SEARCH PIPELINE
# ============================================================

def find_duplicate_matches_vector(db, category, location, description, latitude=None, longitude=None):
    """
    Multi-stage vector duplicate search.
    Falls back to legacy on any failure.
    """
    try:
        from backend.app.services.embedding_service import build_complaint_text, generate_embedding
        text = build_complaint_text(category, description)
        embedding = generate_embedding(text)
        if embedding is None:
            return find_duplicate_matches_legacy(db, category, location, description)

        cursor = db.cursor()
        is_sqlite = "sqlite3" in type(db).__module__ or hasattr(db, "row_factory")

        if is_sqlite:
            cursor.execute(
                """
                SELECT c.id, c.description, c.category, c.state, c.location,
                       c.language, c.status, c.created_at, c.embedding_json,
                       COUNT(v.id) AS votes
                FROM complaints c
                LEFT JOIN complaint_votes v ON c.id = v.complaint_id
                WHERE c.status != 'Resolved'
                GROUP BY c.id ORDER BY c.id DESC LIMIT 500
                """
            )
            rows = cursor.fetchall()
            candidates = []
            for row in rows:
                emb_json = row[8]
                if emb_json is None:
                    continue
                try:
                    sim = _cosine_similarity(embedding, _json_mod.loads(emb_json))
                    if sim >= VECTOR_SIMILARITY_THRESHOLD:
                        candidates.append((row, sim))
                except Exception:
                    continue
        else:
            vec_str = "[" + ",".join(str(v) for v in embedding) + "]"
            if latitude is not None and longitude is not None:
                cursor.execute(
                    """
                    SELECT c.id, c.description, c.category, c.state, c.location,
                           c.language, c.status, c.created_at,
                           1 - (c.embedding <=> %s::vector) AS sem,
                           COUNT(v.id) AS votes
                    FROM complaints c
                    LEFT JOIN complaint_votes v ON c.id = v.complaint_id
                    WHERE c.status != 'Resolved' AND c.embedding IS NOT NULL
                      AND ST_DWithin(c.location_point,
                          ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography, %s)
                    GROUP BY c.id ORDER BY sem DESC LIMIT %s
                    """,
                    (vec_str, longitude, latitude, GEO_RADIUS_METERS, VECTOR_TOP_K),
                )
            else:
                cursor.execute(
                    """
                    SELECT c.id, c.description, c.category, c.state, c.location,
                           c.language, c.status, c.created_at,
                           1 - (c.embedding <=> %s::vector) AS sem,
                           COUNT(v.id) AS votes
                    FROM complaints c
                    LEFT JOIN complaint_votes v ON c.id = v.complaint_id
                    WHERE c.status != 'Resolved' AND c.embedding IS NOT NULL
                    GROUP BY c.id ORDER BY sem DESC LIMIT %s
                    """,
                    (vec_str, VECTOR_TOP_K),
                )
            rows = cursor.fetchall()
            candidates = [(row, row[8]) for row in rows if row[8] >= VECTOR_SIMILARITY_THRESHOLD]

        matches = []
        for row, sem_sim in candidates:
            eid, edesc, ecat, estate, eloc, elang, estatus, ecreated = row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7]
            votes = row[-1] or 0
            geo = 1.0 if (latitude is not None and longitude is not None) else 0.0
            same_cat = normalize_category(category) == normalize_category(ecat or "")
            rec = _recency_score(ecreated)
            hybrid = calculate_hybrid_score(sem_sim, geo, same_cat, rec)
            is_dup = hybrid >= VECTOR_SIMILARITY_THRESHOLD

            if not is_dup and LLM_VERIFY_LOW <= hybrid < LLM_VERIFY_HIGH:
                try:
                    from backend.app.ai.duplicate_verifier import verify_duplicate_pair
                    verdict = verify_duplicate_pair(
                        {"description": description, "category": category, "location": location},
                        {"description": edesc, "category": ecat, "location": eloc},
                    )
                    is_dup = verdict.get("same_incident", False)
                except Exception:
                    pass

            if is_dup:
                loc_sim = round(location_similarity(location, eloc or ""), 2)
                matches.append({
                    "id": eid, "description": edesc, "category": ecat,
                    "state": estate, "location": eloc, "language": elang,
                    "status": estatus, "votes": votes,
                    "similarity": hybrid, "text_similarity": round(sem_sim, 2),
                    "location_similarity": loc_sim, "same_category": same_cat,
                    "same_location": loc_sim >= 0.75,
                    "shared_core_issues": sorted(
                        extract_core_issues(description) & extract_core_issues(edesc or "")
                    ),
                })

        matches.sort(key=lambda c: (
            1 if c["status"] == "Resolved" else 0,
            -c["similarity"], -c["votes"], -c["id"],
        ))
        return matches

    except Exception as exc:
        logger.warning("Vector duplicate search failed (%s), falling back to legacy.", exc)
        return find_duplicate_matches_legacy(db, category, location, description)


# ============================================================
# SHADOW MODE
# ============================================================

def find_duplicate_matches_shadow(db, category, location, description, latitude=None, longitude=None):
    """Run both pipelines for comparison logging; return legacy result."""
    legacy = find_duplicate_matches_legacy(db, category, location, description)
    try:
        vector = find_duplicate_matches_vector(db, category, location, description, latitude, longitude)
        only_legacy = {m["id"] for m in legacy} - {m["id"] for m in vector}
        only_vector = {m["id"] for m in vector} - {m["id"] for m in legacy}
        logger.info(
            "SHADOW | legacy=%d vector=%d only_legacy=%s only_vector=%s",
            len(legacy), len(vector), sorted(only_legacy), sorted(only_vector),
        )
    except Exception as exc:
        logger.warning("Shadow vector check failed: %s", exc)
    return legacy


# ============================================================
# UNIFIED ENTRY POINT
# ============================================================

def find_duplicate_matches(db, category, location, description, latitude=None, longitude=None):
    """
    Routes call this function.
    Strategy controlled by env vars:
      DUPLICATE_SHADOW_MODE=true → run both, return legacy
      DUPLICATE_USE_VECTOR=true  → vector pipeline
      (default)                  → legacy deterministic
    """
    if DUPLICATE_SHADOW_MODE:
        return find_duplicate_matches_shadow(db, category, location, description, latitude, longitude)
    if DUPLICATE_USE_VECTOR:
        return find_duplicate_matches_vector(db, category, location, description, latitude, longitude)
    return find_duplicate_matches_legacy(db, category, location, description)
