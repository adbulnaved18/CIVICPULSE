from collections import OrderedDict

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from backend.app.auth.dependencies import get_current_user
from backend.app.services.database import get_db
from backend.app.services import db_compat


router = APIRouter(
    prefix="/participatory-budgeting",
    tags=["Participatory Budgeting"],
)


# ============================================================
# REQUEST MODEL
# ============================================================

class PrioritySubmission(BaseModel):
    issue_ids: list[int]


# ============================================================
# HEALTH CHECK
# ============================================================

@router.get("/health")
def participatory_budgeting_health():
    return {
        "message": "Participatory Budgeting API is running"
    }


# ============================================================
# TEXT NORMALIZATION
# ============================================================

def normalize_text(value):
    if not value:
        return ""

    return " ".join(
        str(value)
        .strip()
        .lower()
        .split()
    )


# ============================================================
# CURRENT USER ID
# ============================================================

def get_user_id(current_user):
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated.",
        )

    user_id = current_user.get("id")

    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authenticated user.",
        )

    try:
        return int(user_id)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authenticated user.",
        )


# ============================================================
# GET COMMUNITY PRIORITIES
# ============================================================

@router.get("/priorities")
def get_priorities(
    state: str = Query(default=None, description="Filter priorities by state"),
    category: str = Query(default=None, description="Filter priorities by category"),
    search: str = Query(default=None, description="Search priorities by keyword"),
):
    """
    Returns all civic issues with their current
    participatory-budgeting support count.

    IMPORTANT:
    Support is counted from:

        participatory_priorities

    NOT:

        complaint_votes
        participatory_budget_votes
    """

    db = get_db()

    try:

        # ----------------------------------------------------
        # GET COMPLAINTS + PB SUPPORT COUNT WITH FILTERS
        # ----------------------------------------------------

        query = """
            SELECT
                c.id,
                c.description,
                c.category,
                c.state,
                c.location,
                c.status,
                COUNT(DISTINCT pp.id) AS supports

            FROM complaints c

            LEFT JOIN participatory_priorities pp
                ON c.id = pp.issue_id

            WHERE 1=1
        """
        params = []

        if state and state.strip():
            query += " AND c.state = ?"
            params.append(state.strip())

        if category and category.strip() and category.strip().lower() != "all":
            query += " AND LOWER(c.category) = LOWER(?)"
            params.append(category.strip())

        if search and search.strip():
            query += " AND (LOWER(c.description) LIKE LOWER(?) OR LOWER(c.category) LIKE LOWER(?) OR LOWER(c.location) LIKE LOWER(?))"
            search_pattern = f"%{search.strip()}%"
            params.extend([search_pattern, search_pattern, search_pattern])

        query += """
            GROUP BY
                c.id,
                c.description,
                c.category,
                c.state,
                c.location,
                c.status

            ORDER BY
                supports DESC,
                c.id ASC
        """

        cursor = db_compat.execute(db, query, params)

        rows = cursor.fetchall()

        # ----------------------------------------------------
        # GROUP SIMILAR ISSUES
        # ----------------------------------------------------

        grouped = OrderedDict()

        for row in rows:

            complaint_id = int(row["id"])

            description = (
                row["description"]
                or "Civic Issue"
            )

            category = (
                row["category"]
                or "General"
            )

            state = (
                row["state"]
                or "Other"
            )

            location = (
                row["location"]
                or "Location not specified"
            )

            status_value = (
                row["status"]
                or "Pending"
            )

            supports = int(
                row["supports"] or 0
            )

            normalized_description = normalize_text(
                description
            )

            normalized_category = normalize_text(
                category
            )

            normalized_location = normalize_text(
                location
            )

            # ------------------------------------------------
            # GROUP BY CATEGORY + DESCRIPTION
            # ------------------------------------------------

            group_key = (
                normalized_category,
                normalized_description,
            )

            if group_key not in grouped:

                grouped[group_key] = {
                    "id": complaint_id,
                    "title": description,
                    "description": description,
                    "category": category,
                    "state": state,
                    "location": location,
                    "status": status_value,
                    "supports": 0,
                    "complaint_ids": [],
                    "locations": [],
                }

            group = grouped[group_key]

            # ------------------------------------------------
            # ADD SUPPORTS
            # ------------------------------------------------

            group["supports"] += supports

            # ------------------------------------------------
            # STORE COMPLAINT ID
            # ------------------------------------------------

            if complaint_id not in group["complaint_ids"]:

                group["complaint_ids"].append(
                    complaint_id
                )

            # ------------------------------------------------
            # STORE UNIQUE LOCATIONS
            # ------------------------------------------------

            existing_locations = [
                normalize_text(item)
                for item in group["locations"]
            ]

            if (
                normalized_location
                and normalized_location
                not in existing_locations
            ):
                group["locations"].append(
                    location
                )

            # ------------------------------------------------
            # STATUS PRIORITY
            # ------------------------------------------------

            current_status = group["status"]

            if status_value == "In Progress":

                group["status"] = "In Progress"

            elif (
                status_value == "Pending"
                and current_status == "Resolved"
            ):

                group["status"] = "Pending"

        # ----------------------------------------------------
        # CONVERT TO LIST
        # ----------------------------------------------------

        priorities = list(
            grouped.values()
        )

        # ----------------------------------------------------
        # SORT BY SUPPORT
        # ----------------------------------------------------

        priorities.sort(
            key=lambda issue: (
                -int(issue["supports"]),
                int(issue["id"]),
            )
        )

        # ----------------------------------------------------
        # CLEAN LOCATION DATA
        # ----------------------------------------------------

        for issue in priorities:

            locations = issue.get(
                "locations",
                []
            )

            if len(locations) > 1:

                issue["location"] = (
                    " • ".join(locations)
                )

            elif len(locations) == 1:

                issue["location"] = (
                    locations[0]
                )

            issue.pop(
                "locations",
                None
            )

        return priorities

    finally:
        db.close()


# ============================================================
# SUBMIT PARTICIPATORY PRIORITIES
# ============================================================

@router.post("/priorities")
def submit_priorities(
    payload: PrioritySubmission,
    current_user: dict = Depends(
        get_current_user
    ),
):
    """
    Save authenticated user's selected
    participatory-budgeting priorities.

    Maximum 3 issues per submission.

    One user can support each issue only once.

    Database table:

        participatory_priorities

    Columns:

        user_id
        issue_id
    """

    # ========================================================
    # AUTHENTICATION
    # ========================================================

    user_id = get_user_id(
        current_user
    )

    # ========================================================
    # VALIDATE PAYLOAD
    # ========================================================

    if not payload.issue_ids:

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Please select at least one "
                "civic issue."
            ),
        )

    # --------------------------------------------------------
    # REMOVE DUPLICATES
    # --------------------------------------------------------

    issue_ids = list(
        dict.fromkeys(
            payload.issue_ids
        )
    )

    # --------------------------------------------------------
    # MAXIMUM 3
    # --------------------------------------------------------

    if len(issue_ids) > 3:

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "You can prioritize up to "
                "3 civic issues."
            ),
        )

    # ========================================================
    # CLEAN IDS
    # ========================================================

    cleaned_issue_ids = []

    for issue_id in issue_ids:

        try:

            numeric_id = int(issue_id)

        except (
            TypeError,
            ValueError,
        ):

            continue

        if numeric_id > 0:

            cleaned_issue_ids.append(
                numeric_id
            )

    if not cleaned_issue_ids:

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "No valid civic issues "
                "were selected."
            ),
        )

    # ========================================================
    # DATABASE
    # ========================================================

    db = get_db()

    try:

        # ====================================================
        # VERIFY USER
        # ====================================================

        cursor = db_compat.execute(
            db,
            """
            SELECT id
            FROM users
            WHERE id = ?
            """,
            (user_id,),
        )

        user_row = cursor.fetchone()

        if user_row is None:

            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=(
                    "Authenticated user "
                    "does not exist."
                ),
            )

        # ====================================================
        # VERIFY COMPLAINTS
        # ====================================================

        valid_ids = []

        for issue_id in cleaned_issue_ids:

            cursor = db_compat.execute(
                db,
                """
                SELECT id
                FROM complaints
                WHERE id = ?
                """,
                (issue_id,),
            )

            row = cursor.fetchone()

            if row:

                valid_ids.append(
                    int(row["id"])
                )

        # ----------------------------------------------------
        # NO VALID ISSUES
        # ----------------------------------------------------

        if not valid_ids:

            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    "No valid civic issues "
                    "were selected."
                ),
            )

        # ====================================================
        # CHECK EXISTING PRIORITIES
        # ====================================================

        already_supported = []
        new_ids = []

        for issue_id in valid_ids:

            cursor = db_compat.execute(
                db,
                """
                SELECT id
                FROM participatory_priorities
                WHERE user_id = ?
                  AND issue_id = ?
                """,
                (
                    user_id,
                    issue_id,
                ),
            )

            existing = cursor.fetchone()

            if existing:

                already_supported.append(
                    issue_id
                )

            else:

                new_ids.append(
                    issue_id
                )

        # ====================================================
        # INSERT NEW PRIORITIES
        # ====================================================

        inserted_ids = []

        for issue_id in new_ids:

            db_compat.execute(
                db,
                """
                INSERT INTO participatory_priorities (
                    user_id,
                    issue_id
                )
                VALUES (?, ?)
                """,
                (
                    user_id,
                    issue_id,
                ),
            )

            inserted_ids.append(
                issue_id
            )

        # ====================================================
        # COMMIT
        # ====================================================

        db.commit()

        # ====================================================
        # MESSAGE
        # ====================================================

        if (
            not inserted_ids
            and already_supported
        ):

            message = (
                "You have already submitted "
                "these community priorities."
            )

        elif already_supported:

            message = (
                "Your new community priorities "
                "have been recorded. Some selected "
                "issues were already supported by you."
            )

        else:

            message = (
                "Your community priorities "
                "have been recorded successfully."
            )

        # ====================================================
        # RETURN
        # ====================================================

        return {
            "message": message,

            "selected_issue_ids": valid_ids,

            "newly_supported_issue_ids": (
                inserted_ids
            ),

            "already_supported_issue_ids": (
                already_supported
            ),

            "new_support_count": len(
                inserted_ids
            ),

            "count": len(
                valid_ids
            ),

            "note": (
                "These priorities represent "
                "community preference. Final "
                "budget allocation and implementation "
                "decisions remain with the authorized "
                "authority."
            ),
        }

    except HTTPException:

        db.rollback()
        raise

    except Exception as error:

        db.rollback()

        print(
            "Participatory budgeting submission error:",
            error,
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Failed to save community "
                "priorities."
            ),
        )

    finally:

        db.close()