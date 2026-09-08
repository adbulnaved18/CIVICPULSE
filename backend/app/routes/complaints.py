from typing import Optional

from fastapi import (
    APIRouter,
    UploadFile,
    File,
    Form,
    HTTPException,
    Depends,
    Query,
)

import hashlib
import os
import re
import sqlite3
import unicodedata
import uuid

from backend.app.auth.dependencies import (
    get_current_user,
    require_admin,
)

from backend.app.models.complaint import Complaint

from backend.app.services.database import get_db
from backend.app.services.duplicate_service import (
    find_duplicate_matches,
    calculate_duplicate_score_legacy,
    calculate_priority,
)
from backend.app.services.embedding_service import embed_complaint


router = APIRouter(
    prefix="/complaints",
    tags=["Complaints"],
)



# ============================================================
# CREATE COMPLAINT
# ============================================================

@router.post("/")
def create_complaint(
    complaint: Complaint,
):

    db = get_db()
    cursor = db.cursor()

    try:

        # ----------------------------------------------------
        # SERVER-SIDE DUPLICATE PROTECTION
        # ----------------------------------------------------

        duplicate_matches = find_duplicate_matches(
            db=db,
            category=complaint.category,
            location=complaint.location,
            description=complaint.description,
            latitude=complaint.latitude,
            longitude=complaint.longitude,
        )

        if duplicate_matches:

            best_match = duplicate_matches[0]

            raise HTTPException(
                status_code=409,
                detail={
                    "message": (
                        "A similar complaint already exists."
                    ),

                    "is_duplicate": True,

                    "matches": duplicate_matches[:3],

                    "best_match": best_match,
                },
            )

        # ----------------------------------------------------
        # CREATE COMPLAINT
        # ----------------------------------------------------

        cursor.execute(
            """
            INSERT INTO complaints (
                description,
                category,
                state,
                location,
                language,
                status,
                latitude,
                longitude,
                location_accuracy,
                location_captured_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                complaint.description,
                complaint.category,
                complaint.state,
                complaint.location,
                complaint.language,
                complaint.status,
                complaint.latitude,
                complaint.longitude,
                complaint.location_accuracy,
                complaint.location_captured_at,
            ),
        )

        complaint_id = cursor.lastrowid

        db.commit()

        # Generate and store embedding (non-blocking; failure is ignored)
        try:
            embed_complaint(db, complaint_id, complaint.category, complaint.description)
        except Exception:
            pass

        return {
            "message": "Complaint saved successfully",

            "complaint_id": complaint_id,

            "complaint": {
                "id": complaint_id,

                "description": complaint.description,

                "category": complaint.category,

                "state": complaint.state,

                "location": complaint.location,

                "language": complaint.language,

                "status": complaint.status,

                "latitude": complaint.latitude,

                "longitude": complaint.longitude,

                "location_accuracy": (
                    complaint.location_accuracy
                ),

                "location_captured_at": (
                    complaint.location_captured_at
                ),
            },
        }

    except HTTPException:

        db.rollback()
        raise

    except Exception as error:

        db.rollback()

        print(
            "Failed to create complaint:",
            error,
        )

        raise HTTPException(
            status_code=500,
            detail="Failed to create complaint",
        )

    finally:
        db.close()


# ============================================================
# GET ALL COMPLAINTS
# ============================================================

@router.get("/")
def get_complaints(
    state: Optional[str] = Query(
        default=None,
        description="Filter complaints by state",
    ),

    region: Optional[str] = Query(
        default=None,
        description="Filter complaints by region/location",
    ),
):

    db = get_db()
    cursor = db.cursor()

    try:

        if state and state.strip():

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
                    COUNT(v.id) AS votes,
                    c.latitude,
                    c.longitude,
                    c.location_accuracy,
                    c.location_captured_at
                FROM complaints c
                LEFT JOIN complaint_votes v
                    ON c.id = v.complaint_id
                WHERE c.state = ?
                GROUP BY
                    c.id,
                    c.description,
                    c.category,
                    c.state,
                    c.location,
                    c.language,
                    c.status,
                    c.latitude,
                    c.longitude,
                    c.location_accuracy,
                    c.location_captured_at
                """,
                (
                    state.strip(),
                ),
            )

        elif region and region.strip():

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
                    COUNT(v.id) AS votes,
                    c.latitude,
                    c.longitude,
                    c.location_accuracy,
                    c.location_captured_at
                FROM complaints c
                LEFT JOIN complaint_votes v
                    ON c.id = v.complaint_id
                WHERE LOWER(c.location) LIKE LOWER(?)
                GROUP BY
                    c.id,
                    c.description,
                    c.category,
                    c.state,
                    c.location,
                    c.language,
                    c.status,
                    c.latitude,
                    c.longitude,
                    c.location_accuracy,
                    c.location_captured_at
                ORDER BY c.id DESC
                """,
                (
                    f"%{region.strip()}%",
                ),
            )

        else:

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
                    COUNT(v.id) AS votes,
                    c.latitude,
                    c.longitude,
                    c.location_accuracy,
                    c.location_captured_at
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
                    c.status,
                    c.latitude,
                    c.longitude,
                    c.location_accuracy,
                    c.location_captured_at
                ORDER BY c.id DESC
                """
            )

        rows = cursor.fetchall()

        complaints = []

        for row in rows:

            votes_count = (
                row[7]
                if row[7] is not None
                else 0
            )

            complaint_status = (
                row[6]
                or "Pending"
            )

            priority = calculate_priority(
                votes_count,
                complaint_status,
            )

            complaints.append({
                "id": row[0],

                "description": row[1],

                "category": row[2],

                "state": row[3],

                "location": row[4],

                "language": row[5],

                "status": complaint_status,

                "votes": votes_count,

                "priority": priority,

                "latitude": row[8],

                "longitude": row[9],

                "location_accuracy": row[10],

                "location_captured_at": row[11],
            })

        complaints.sort(
            key=lambda complaint: (
                -complaint["priority"],
                complaint["id"],
            )
        )

        return complaints

    except Exception as error:

        print(
            "Error fetching complaints:",
            error,
        )

        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve complaints.",
        )

    finally:
        db.close()


# ============================================================
# GET UNIQUE REGIONS
# ============================================================

@router.get("/regions")
def get_regions():

    db = get_db()
    cursor = db.cursor()

    try:

        cursor.execute(
            """
            SELECT DISTINCT state
            FROM complaints
            WHERE state IS NOT NULL
              AND TRIM(state) != ''
              AND state != 'Other'
            ORDER BY state COLLATE NOCASE ASC
            """
        )

        rows = cursor.fetchall()

        regions = [
            row[0].strip()
            for row in rows
            if row[0]
            and row[0].strip()
        ]

        return {
            "regions": regions
        }

    except Exception as error:

        print(
            "Error fetching regions:",
            error,
        )

        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve regions.",
        )

    finally:
        db.close()


# ============================================================
# GET GEO-LOCATED COMPLAINTS
# ============================================================

@router.get("/geo")
def get_geo_complaints(
    status: str = None,
    category: str = None,
    state: str = None,
):

    db = get_db()
    cursor = db.cursor()

    try:

        query = """
            SELECT
                c.id,
                c.description,
                c.category,
                c.state,
                c.location,
                c.status,
                COUNT(v.id) AS votes,
                c.latitude,
                c.longitude,
                c.location_accuracy,
                c.created_at
            FROM complaints c
            LEFT JOIN complaint_votes v
                ON c.id = v.complaint_id
            WHERE c.latitude IS NOT NULL
              AND c.longitude IS NOT NULL
        """

        params = []

        if state:

            query += """
                AND c.state = ?
            """

            params.append(
                state
            )

        if status:

            query += """
                AND c.status = ?
            """

            params.append(
                status
            )

        if category:

            query += """
                AND c.category = ?
            """

            params.append(
                category
            )

        query += """
            GROUP BY c.id
            ORDER BY c.id DESC
        """

        cursor.execute(
            query,
            params,
        )

        rows = cursor.fetchall()

        complaints = []

        for row in rows:

            priority = calculate_priority(
                row[6],
                row[5],
            )

            complaints.append({
                "id": row[0],

                "description": row[1],

                "category": row[2],

                "state": row[3],

                "location": row[4],

                "status": row[5],

                "votes": row[6],

                "latitude": row[7],

                "longitude": row[8],

                "location_accuracy": row[9],

                "created_at": row[10],

                "priority": priority,
            })

        return complaints

    finally:
        db.close()


# ============================================================
# UPDATE COMPLAINT STATUS
# ============================================================

@router.patch("/{complaint_id}/status")
def update_complaint_status(
    complaint_id: int,
    status: str,
    current_admin: dict = Depends(
        require_admin
    ),
):

    allowed_statuses = {
        "Pending",
        "In Progress",
        "Resolved",
    }

    if status not in allowed_statuses:

        raise HTTPException(
            status_code=400,
            detail={
                "message": "Invalid status",

                "allowed_statuses": list(
                    allowed_statuses
                ),
            },
        )

    db = get_db()
    cursor = db.cursor()

    try:

        cursor.execute(
            """
            UPDATE complaints
            SET status = ?
            WHERE id = ?
            """,
            (
                status,
                complaint_id,
            ),
        )

        if cursor.rowcount == 0:

            raise HTTPException(
                status_code=404,
                detail="Complaint not found",
            )

        db.commit()

        return {
            "message": (
                "Complaint status updated successfully"
            ),

            "complaint_id": complaint_id,

            "status": status,
        }

    except HTTPException:

        db.rollback()
        raise

    except Exception as error:

        db.rollback()

        print(
            "Failed to update complaint status:",
            error,
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "Failed to update complaint status"
            ),
        )

    finally:
        db.close()


# ============================================================
# VOTE FOR COMPLAINT
# ============================================================

@router.post("/{complaint_id}/vote")
def vote_complaint(
    complaint_id: int,
    current_user: dict = Depends(
        get_current_user
    ),
):

    voter_id = str(
        current_user["id"]
    )

    db = get_db()
    cursor = db.cursor()

    try:

        # ----------------------------------------------------
        # CHECK COMPLAINT EXISTS
        # ----------------------------------------------------

        cursor.execute(
            """
            SELECT id
            FROM complaints
            WHERE id = ?
            """,
            (
                complaint_id,
            ),
        )

        complaint = cursor.fetchone()

        if not complaint:

            raise HTTPException(
                status_code=404,
                detail="Complaint not found",
            )

        # ----------------------------------------------------
        # INSERT VOTE
        # ----------------------------------------------------

        try:

            cursor.execute(
                """
                INSERT INTO complaint_votes (
                    complaint_id,
                    voter_id
                )
                VALUES (?, ?)
                """,
                (
                    complaint_id,
                    voter_id,
                ),
            )

            db.commit()

        except sqlite3.IntegrityError as error:

            db.rollback()

            # Only treat the UNIQUE constraint as
            # an already-voted condition.
            if (
                "UNIQUE constraint failed"
                in str(error)
            ):
                return {
                    "message": (
                        "You have already voted "
                        "for this complaint"
                    )
                }

            raise

        return {
            "message": (
                "Vote added successfully"
            ),

            "complaint_id": complaint_id,

            "voter_id": voter_id,
        }

    except HTTPException:

        db.rollback()
        raise

    except Exception as error:

        db.rollback()

        print(
            "Failed to vote for complaint:",
            error,
        )

        raise HTTPException(
            status_code=500,
            detail="Failed to support complaint.",
        )

    finally:
        db.close()


# ============================================================
# CHECK DUPLICATE COMPLAINT
# ============================================================

@router.get("/check-duplicate")
def check_duplicate(
    category: str,
    location: str,
    description: str,
    latitude: Optional[float] = Query(default=None),
    longitude: Optional[float] = Query(default=None),
):

    db = get_db()

    try:

        matches = find_duplicate_matches(
            db=db,
            category=category,
            location=location,
            description=description,
            latitude=latitude,
            longitude=longitude,
        )

        if not matches:

            return {
                "is_duplicate": False,

                "matches": [],
            }

        return {
            "is_duplicate": True,

            "matches": matches[:3],
        }

    finally:
        db.close()


# ============================================================
# UPLOAD EVIDENCE / PHOTO
# ============================================================

@router.post("/{complaint_id}/evidence")
async def upload_evidence(
    complaint_id: int,
    file: UploadFile = File(...),
):

    db = get_db()
    cursor = db.cursor()

    try:

        # ----------------------------------------------------
        # CHECK COMPLAINT
        # ----------------------------------------------------

        cursor.execute(
            """
            SELECT id
            FROM complaints
            WHERE id = ?
            """,
            (
                complaint_id,
            ),
        )

        complaint = cursor.fetchone()

        if not complaint:

            raise HTTPException(
                status_code=404,
                detail="Complaint not found",
            )

        # ----------------------------------------------------
        # CHECK FILE
        # ----------------------------------------------------

        if not file.filename:

            raise HTTPException(
                status_code=400,
                detail="No file selected",
            )

        # ----------------------------------------------------
        # EVIDENCE DIRECTORY
        # ----------------------------------------------------

        evidence_folder = (
            "uploads/evidence"
        )

        os.makedirs(
            evidence_folder,
            exist_ok=True,
        )

        # ----------------------------------------------------
        # SAFE FILENAME
        # ----------------------------------------------------

        safe_filename = re.sub(
            r"[^a-zA-Z0-9._-]",
            "_",
            file.filename,
        )

        file_path = os.path.join(
            evidence_folder,
            f"{complaint_id}_{safe_filename}",
        ).replace("\\", "/")

        # ----------------------------------------------------
        # SAVE FILE
        # ----------------------------------------------------

        file_content = await file.read()

        with open(
            file_path,
            "wb",
        ) as buffer:

            buffer.write(
                file_content
            )

        # ----------------------------------------------------
        # SAVE DATABASE RECORD
        # ----------------------------------------------------

        cursor.execute(
            """
            INSERT INTO complaint_evidence (
                complaint_id,
                file_path,
                file_type
            )
            VALUES (?, ?, ?)
            """,
            (
                complaint_id,
                file_path,
                file.content_type,
            ),
        )

        db.commit()

        return {
            "message": (
                "Evidence uploaded successfully"
            ),

            "complaint_id": complaint_id,

            "file_path": file_path,

            "file_type": file.content_type,
        }

    except HTTPException:

        db.rollback()
        raise

    except Exception as error:

        db.rollback()

        print(
            "Failed to upload evidence:",
            error,
        )

        raise HTTPException(
            status_code=500,
            detail="Failed to upload evidence",
        )

    finally:
        db.close()


# ============================================================
# GET EVIDENCE FOR A COMPLAINT
# ============================================================

@router.get("/{complaint_id}/evidence")
def get_evidence(
    complaint_id: int,
):

    db = get_db()
    cursor = db.cursor()

    try:

        # ----------------------------------------------------
        # CHECK COMPLAINT
        # ----------------------------------------------------

        cursor.execute(
            """
            SELECT id
            FROM complaints
            WHERE id = ?
            """,
            (
                complaint_id,
            ),
        )

        complaint = cursor.fetchone()

        if not complaint:

            raise HTTPException(
                status_code=404,
                detail="Complaint not found",
            )

        # ----------------------------------------------------
        # GET EVIDENCE
        # ----------------------------------------------------

        cursor.execute(
            """
            SELECT
                id,
                complaint_id,
                file_path,
                file_type
            FROM complaint_evidence
            WHERE complaint_id = ?
            ORDER BY id DESC
            """,
            (
                complaint_id,
            ),
        )

        rows = cursor.fetchall()

        evidence = []

        for row in rows:

            evidence.append({
                "id": row[0],

                "complaint_id": row[1],

                "file_path": row[2],

                "file_type": row[3],
            })

        return {
            "complaint_id": complaint_id,

            "evidence": evidence,
        }

    finally:
        db.close()


# ============================================================
# UNIFIED AI-ASSISTED SUBMIT REPORT
# ============================================================
#
# This endpoint replaces the two-step (POST /complaints/ +
# POST /complaints/{id}/evidence) flow with a single multipart
# request.  The old endpoints remain available for backward
# compatibility.
#
# Accepts:
#   description       TEXT   required
#   category          TEXT   required (manual selection or AI-resolved)
#   state             TEXT   required
#   location          TEXT   required
#   language          TEXT   optional (en/hi)
#   analysis_id       TEXT   optional (UUID from POST /ai/analyze-report)
#   image             FILE   optional evidence photo
#   latitude          REAL   optional
#   longitude         REAL   optional
#   location_accuracy REAL   optional
#   location_captured_at TEXT optional
# ============================================================

@router.post("/submit-report")
async def submit_report(
    description: str = Form(...),
    category: str = Form(...),
    state: str = Form(...),
    location: str = Form(...),
    language: str = Form(default="en"),
    analysis_id: Optional[str] = Form(default=None),
    image: Optional[UploadFile] = File(default=None),
    latitude: Optional[float] = Form(default=None),
    longitude: Optional[float] = Form(default=None),
    location_accuracy: Optional[float] = Form(default=None),
    location_captured_at: Optional[str] = Form(default=None),
    current_user: dict = Depends(get_current_user),
):
    """
    Unified complaint submission endpoint that:
    1. Verifies the AI analysis record (if analysis_id provided)
    2. Applies confidence-based category policy
    3. Runs duplicate detection
    4. Creates the complaint + saves evidence in one transaction
    """

    # --------------------------------------------------------
    # Basic validation
    # --------------------------------------------------------
    description = description.strip()
    category = category.strip()
    state = state.strip()
    location = location.strip()

    if not description or not category or not state or not location:
        raise HTTPException(
            status_code=400,
            detail="description, category, state, and location are required.",
        )

    # --------------------------------------------------------
    # Read image bytes (if provided)
    # --------------------------------------------------------
    image_bytes: Optional[bytes] = None
    image_content_type: Optional[str] = None
    image_sha: Optional[str] = None

    if image and image.filename:
        image_bytes = await image.read()
        image_content_type = image.content_type or "image/jpeg"
        image_sha = hashlib.sha256(image_bytes).hexdigest()

    # --------------------------------------------------------
    # AI analysis verification
    # --------------------------------------------------------
    final_category = category
    category_source = "manual"
    ai_confidence: Optional[float] = None
    ai_needs_review: int = 0

    if analysis_id and analysis_id.strip():
        db_verify = get_db()
        try:
            cursor = db_verify.cursor()
            cursor.execute(
                """
                SELECT
                    user_id,
                    text_sha256,
                    image_sha256,
                    suggested_category,
                    confidence,
                    needs_review,
                    expires_at
                FROM report_ai_analyses
                WHERE id = ?
                """,
                (analysis_id.strip(),),
            )
            row = cursor.fetchone()
        finally:
            db_verify.close()

        if row is not None:
            # Confirm it belongs to this user.
            if row[0] == current_user["id"]:
                # Verify text hash matches current submission.
                text_sha = hashlib.sha256(
                    description.encode("utf-8")
                ).hexdigest()

                text_matches = row[1] == text_sha
                image_matches = (
                    row[2] is None
                    or image_sha is None
                    or row[2] == image_sha
                )

                if text_matches and image_matches:
                    ai_confidence = row[4]
                    ai_needs_review = row[5]

                    # Apply confidence policy:
                    # >= AUTO_ACCEPT  → use AI category
                    # 0.60-0.79       → use AI category (user confirmed)
                    # < 0.60          → keep manual category
                    AI_AUTO = float(
                        os.environ.get("AI_AUTO_ACCEPT_THRESHOLD", "0.80")
                    )
                    AI_REVIEW = float(
                        os.environ.get("AI_REVIEW_THRESHOLD", "0.60")
                    )

                    if ai_confidence is not None and ai_confidence >= AI_REVIEW:
                        final_category = row[3]
                        category_source = "ai"

    # --------------------------------------------------------
    # Duplicate detection (using resolved category)
    # --------------------------------------------------------
    db = get_db()
    cursor = db.cursor()

    try:
        duplicate_matches = find_duplicate_matches(
            db=db,
            category=final_category,
            location=location,
            description=description,
            latitude=latitude,
            longitude=longitude,
        )

        if duplicate_matches:
            best_match = duplicate_matches[0]
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "A similar complaint already exists.",
                    "is_duplicate": True,
                    "matches": duplicate_matches[:3],
                    "best_match": best_match,
                },
            )

        # --------------------------------------------------------
        # Create complaint
        # --------------------------------------------------------
        cursor.execute(
            """
            INSERT INTO complaints (
                description,
                category,
                state,
                location,
                language,
                status,
                latitude,
                longitude,
                location_accuracy,
                location_captured_at,
                created_by,
                user_selected_category,
                category_source,
                ai_confidence,
                ai_analysis_id,
                ai_needs_review
            )
            VALUES (?, ?, ?, ?, ?, 'Pending', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                description,
                final_category,
                state,
                location,
                language,
                latitude,
                longitude,
                location_accuracy,
                location_captured_at,
                current_user["id"],
                category,             # user_selected_category = original manual selection
                category_source,
                ai_confidence,
                analysis_id,
                ai_needs_review,
            ),
        )

        complaint_id = cursor.lastrowid

        # --------------------------------------------------------
        # Save evidence
        # --------------------------------------------------------
        saved_path: Optional[str] = None

        if image_bytes and image_content_type:
            upload_dir = "uploads/evidence"
            os.makedirs(upload_dir, exist_ok=True)

            ext = ".jpg"
            if image_content_type == "image/png":
                ext = ".png"
            elif image_content_type == "image/gif":
                ext = ".gif"
            elif image_content_type == "image/webp":
                ext = ".webp"

            file_name = f"complaint_{complaint_id}_{uuid.uuid4().hex}{ext}"
            file_path = os.path.join(upload_dir, file_name).replace("\\", "/")

            try:
                with open(file_path, "wb") as f:
                    f.write(image_bytes)

                cursor.execute(
                    """
                    INSERT INTO complaint_evidence (
                        complaint_id, file_path, file_type
                    ) VALUES (?, ?, ?)
                    """,
                    (complaint_id, file_path, image_content_type),
                )

                saved_path = file_path

            except Exception as img_err:
                # If file write fails, roll back everything.
                db.rollback()
                if saved_path and os.path.exists(saved_path):
                    os.remove(saved_path)
                raise HTTPException(
                    status_code=500,
                    detail="Failed to save evidence file.",
                )

        db.commit()

        # Generate and store embedding (non-blocking; failure is ignored)
        try:
            embed_complaint(db, complaint_id, final_category, description)
        except Exception:
            pass

        return {
            "message": "Complaint submitted successfully.",
            "complaint_id": complaint_id,
            "category_used": final_category,
            "category_source": category_source,
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception as error:
        db.rollback()
        print("Failed to submit report:", error)
        raise HTTPException(
            status_code=500,
            detail="Failed to submit complaint.",
        )

    finally:
        db.close()


# ============================================================
# GET MY COMPLAINTS
# ============================================================

@router.get("/my")
def get_my_complaints(current_user: dict = Depends(get_current_user)):
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute(
            """
            SELECT
                c.id, c.description, c.category, c.state, c.location,
                c.language, c.status, COUNT(v.id) AS votes,
                c.latitude, c.longitude, c.location_accuracy, c.location_captured_at
            FROM complaints c
            LEFT JOIN complaint_votes v ON c.id = v.complaint_id
            WHERE c.created_by = ?
            GROUP BY
                c.id, c.description, c.category, c.state, c.location,
                c.language, c.status, c.latitude, c.longitude,
                c.location_accuracy, c.location_captured_at
            ORDER BY c.id DESC
            """,
            (current_user['id'],)
        )
        rows = cursor.fetchall()
        complaints = []
        for row in rows:
            complaints.append({
                "id": row[0],
                "description": row[1],
                "category": row[2],
                "state": row[3],
                "location": row[4],
                "language": row[5],
                "status": row[6],
                "votes": row[7] if row[7] is not None else 0,
                "latitude": row[8],
                "longitude": row[9],
                "location_accuracy": row[10],
                "location_captured_at": row[11],
            })
        return complaints
    finally:
        db.close()

