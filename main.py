from fastapi import FastAPI, UploadFile, File, HTTPException, Request, Header, Depends, Form
from fastapi.responses import StreamingResponse
import zipfile
import asyncio
import concurrent.futures
from fastapi.middleware.cors import CORSMiddleware
import os
from pydantic import BaseModel
import pandas as pd
import io
import uuid
import random
import string
from database import supabase
from PIL import Image
from typing import List

SCHEMA_KEY = "__bizera_column_schema"

FIELD_MAP = {
    # ── Name ──
    "name": "name",
    "student name": "name",
    "student's name": "name",
    "students name": "name",
    "full name": "name",
    "pupil name": "name",
    # ── Class / Section ──
    "class": "class",
    "grade": "class",
    "std": "class",
    "section": "section",
    "sec": "section",
    # ── Roll Number ──
    "roll number": "roll_number",
    "roll no": "roll_number",
    "roll no.": "roll_number",
    "roll_number": "roll_number",
    "roll": "roll_number",
    # ── Admission Number ──
    "admission number": "admission_number",
    "admission no": "admission_number",
    "admission no.": "admission_number",
    "admission_number": "admission_number",
    "adm no": "admission_number",
    "adm no.": "admission_number",
    "adm number": "admission_number",
    # ── Date of Birth ──
    "dob": "dob",
    "date of birth": "dob",
    "birth date": "dob",
    "d.o.b": "dob",
    "d.o.b.": "dob",
    # ── Parents ──
    "father name": "fathers_name",
    "fathers name": "fathers_name",
    "father's name": "fathers_name",
    "fathers_name": "fathers_name",
    "mother name": "mothers_name",
    "mothers name": "mothers_name",
    "mother's name": "mothers_name",
    "mothers_name": "mothers_name",
    # ── Health ──
    "blood group": "blood_group",
    "blood_group": "blood_group",
    "height": "height",
    "weight": "weight",
    # ── Misc ──
    "house": "house",
    "address": "address",
    # ── Phone ──
    "phone": "phone",
    "phone number": "phone",
    "phone no": "phone",
    "phone no.": "phone",
    "mobile": "phone",
    "mobile no": "phone",
    "mobile no.": "phone",
    "mobile number": "phone",
    "contact": "phone",
    "contact no": "phone",
    "contact no.": "phone",
    "contact number": "phone",
    # ── Aadhar ──
    "aadhar": "aadhar_number",
    "aadhar number": "aadhar_number",
    "aadhar_number": "aadhar_number",
    "aadhar no": "aadhar_number",
    "aadhar no.": "aadhar_number",
    "aadhaar": "aadhar_number",
    "aadhaar number": "aadhar_number",
    "aadhaar no": "aadhar_number",
    "aadhaar no.": "aadhar_number",
    # ── Photo ──
    "photo": "photo",
    "photo no": "photo",
    "photo no.": "photo",
}

CORE_EXPORT_FIELDS = [
    "name",
    "class",
    "section",
    "roll_number",
    "admission_number",
    "dob",
    "fathers_name",
    "mothers_name",
    "blood_group",
    "phone",
    "aadhar_number",
    "address",
    "house",
    "height",
    "weight",
]

DISPLAY_LABELS = {
    "name": "Name",
    "class": "Class",
    "section": "Section",
    "roll_number": "Roll Number",
    "admission_number": "Admission Number",
    "dob": "Date of Birth",
    "fathers_name": "Father's Name",
    "mothers_name": "Mother's Name",
    "blood_group": "Blood Group",
    "phone": "Phone",
    "aadhar_number": "Aadhar Number",
    "address": "Address",
    "house": "House",
    "height": "Height",
    "weight": "Weight",
    "photo": "Photo",
}

def display_header_for_key(key):
    return DISPLAY_LABELS.get(
        key,
        str(key).replace("_", " ").title()
    )

def format_dob_for_frontend(student):
    """Converts DB YYYY-MM-DD to DD-MM-YYYY for display/export"""
    dob = student.get("dob")
    if dob and str(dob).strip():
        try:
            student["dob"] = pd.to_datetime(str(dob)).strftime("%d-%m-%Y")
        except Exception:
            pass
    return student

def format_dob_for_db(student_data):
    """Converts User DD-MM-YYYY back to YYYY-MM-DD for Postgres"""
    dob = student_data.get("dob")
    if dob and str(dob).strip():
        try:
            student_data["dob"] = pd.to_datetime(str(dob), dayfirst=True).strftime("%Y-%m-%d")
        except Exception:
            pass
    return student_data

def normalize_header(header):
    return str(header).strip()

def normalize_header_key(header):
    return normalize_header(header).lower().strip()

def build_column_schema(headers, df=None):
    """Build schema from headers. If a DataFrame is provided, skip columns
    that are entirely empty so they never appear in the dashboard."""
    schema = []
    seen_headers = set()
    for header in headers:
        clean_header = normalize_header(header)
        if not clean_header or clean_header in seen_headers:
            continue

        # Skip columns that start with "Unnamed" (phantom Excel columns)
        if clean_header.lower().startswith("unnamed"):
            continue

        # If a DataFrame is provided, skip columns where every value is empty
        if df is not None:
            col_values = df[header]
            if col_values.isna().all():
                continue
            non_null = col_values.dropna().astype(str).str.strip()
            if (non_null == "").all() or len(non_null) == 0:
                continue

        normalized = normalize_header_key(clean_header)
        field_key = FIELD_MAP.get(normalized, clean_header)
        schema.append({
            "header": DISPLAY_LABELS.get(field_key, clean_header),
            "key": field_key,
            "is_custom": field_key not in CORE_EXPORT_FIELDS and field_key != "photo",
            "is_photo": field_key == "photo",
        })
        seen_headers.add(clean_header)
    return schema

def get_schema_from_students(students):
    for student in students:
        custom_data = student.get("custom_data") or {}
        schema = custom_data.get(SCHEMA_KEY)
        if isinstance(schema, list) and schema:
            return schema

    inferred = []
    seen = set()
    for field in CORE_EXPORT_FIELDS:
        if any(student.get(field) not in (None, "") for student in students):
            inferred.append({
                "header": DISPLAY_LABELS.get(field, field),
                "key": field,
                "is_custom": False,
                "is_photo": False,
            })
            seen.add(field)

    custom_keys = []
    for student in students:
        for key in (student.get("custom_data") or {}).keys():
            if key != SCHEMA_KEY and key not in seen and key not in custom_keys:
                custom_keys.append(key)

    for key in custom_keys:
        inferred.append({
            "header": key,
            "key": key,
            "is_custom": True,
            "is_photo": False,
        })

    return inferred

def strip_internal_custom_data(student):
    custom_data = student.get("custom_data")
    if isinstance(custom_data, dict) and SCHEMA_KEY in custom_data:
        student["custom_data"] = {k: v for k, v in custom_data.items() if k != SCHEMA_KEY}
    return student

def photo_export_name(student):
    if not student.get("photo_url"):
        return ""
    adm = str(student.get("admission_number") or student.get("roll_number") or "").strip()
    if adm:
        safe_adm = "".join(c for c in adm if c.isalnum() or c in ('-', '_', ' '))
        return f"{safe_adm}.jpg"

    safe_name = "".join(c for c in str(student.get("name") or "Unknown") if c.isalnum() or c in ('-', '_', ' '))
    return f"{safe_name}_{student['id'][-4:]}.jpg"

def schema_value(student, field):
    if field.get("is_photo") or field.get("key") == "photo":
        return photo_export_name(student)

    key = field.get("key")
    if field.get("is_custom"):
        return (student.get("custom_data") or {}).get(key, "")
    return student.get(key, "")

def preserve_schema_in_custom_data(update_data, existing_custom_data):
    if "custom_data" not in update_data:
        return update_data

    custom_data = update_data.get("custom_data") or {}
    if not isinstance(custom_data, dict):
        custom_data = {}

    if isinstance(existing_custom_data, dict) and SCHEMA_KEY in existing_custom_data and SCHEMA_KEY not in custom_data:
        custom_data[SCHEMA_KEY] = existing_custom_data[SCHEMA_KEY]

    update_data["custom_data"] = custom_data
    return update_data

def ensure_unique_admission_number(data, school_id, current_student_id=None):
    admission_number = str(data.get("admission_number") or "").strip()
    if not admission_number:
        return

    query = supabase.table("students").select("id, name").eq("school_id", school_id).eq("admission_number", admission_number)
    response = query.execute()
    matches = response.data or []
    if current_student_id:
        matches = [student for student in matches if student.get("id") != current_student_id]

    if matches:
        existing_name = matches[0].get("name") or "another student"
        raise HTTPException(
            status_code=409,
            detail=f"Admission number {admission_number} is already used by {existing_name}. Use a unique admission number or leave it blank.",
        )

def friendly_db_error(error):
    message = str(error)
    lower_message = message.lower()
    if "duplicate" in lower_message and "admission" in lower_message:
        return "This admission number is already used. Use a unique admission number or leave it blank."
    if "date/time field value out of range" in lower_message or ("invalid input syntax" in lower_message and "date" in lower_message):
        return "Date of birth is not in a valid format. Use DD-MM-YYYY, for example 05-12-1974."
    return message

app = FastAPI()

# 1. CORS Setup: Allow Next.js to talk to FastAPI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

ADMIN_SECRET = os.getenv("ADMIN_SECRET")
if not ADMIN_SECRET:
    raise ValueError("ADMIN_SECRET env var not set!")

def verify_admin(request: Request):
    token = request.headers.get("X-Admin-Secret")
    if token != ADMIN_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")

def verify_school_user(authorization: str = Header(...)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid token")

    token = authorization.split(" ")[1]

    try:
        user_resp = supabase.auth.get_user(token)
        if not user_resp or not user_resp.user:
            raise HTTPException(status_code=401, detail="Unauthorized")

        metadata = user_resp.user.user_metadata
        school_id = metadata.get("school_id")

        if not school_id:
            raise HTTPException(status_code=403, detail="No school assigned")

        return school_id
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

class SchoolCreate(BaseModel):
    name: str

class BulkDeleteRequest(BaseModel):
    ids: List[str]

def generate_password(length=10):
    """Generates a random 10-character password"""
    chars = string.ascii_letters + string.digits + "@#$%"
    return ''.join(random.choice(chars) for _ in range(length))

@app.post("/create-school")
async def create_school(school: SchoolCreate, request: Request):
    verify_admin(request)
    try:
        clean_name = "".join(e for e in school.name if e.isalnum()).lower()
        email = f"admin@{clean_name}.com"
        
        # 0. Cleanup any orphaned user with this email to avoid collision
        try:
            users = supabase.auth.admin.list_users()
            for u in users:
                if getattr(u, 'email', '') == email:
                    supabase.auth.admin.delete_user(u.id)
        except Exception:
            pass

        # 1. Create the school in the Database
        db_response = supabase.table("schools").insert({"name": school.name}).execute()
        school_data = db_response.data[0]
        school_id = school_data["id"]

        # 2. Generate Login Credentials for the Mobile App
        password = generate_password()

        # 3. Create the User in Supabase Auth (Using the Admin API)
        try:
            supabase.auth.admin.create_user({
                "email": email,
                "password": password,
                "email_confirm": True, # Auto-confirm so they don't need an email link
                "user_metadata": {
                    "school_id": school_id, # Tie this login to their specific school
                    "role": "school_admin"
                }
            })
        except Exception as e:
            supabase.table("schools").delete().eq("id", school_id).execute()
            raise HTTPException(status_code=400, detail=f"User creation failed: {str(e)}")

        return {
            "message": "School and credentials created", 
            "data": school_data,
            "credentials": {
                "email": email,
                "password": password
            }
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
def read_root():
    return {"status": "Backend is running!"}

# Fetch all schools for the dropdown
@app.get("/schools")
async def get_schools(request: Request):
    verify_admin(request)
    try:
        # We order by created_at descending so the newest schools are at the top
        response = supabase.table("schools").select("id, name").order("created_at", desc=True).execute()
        schools_data = response.data
        
        try:
            users = supabase.auth.admin.list_users()
            email_map = {}
            for u in users:
                metadata = getattr(u, 'user_metadata', {})
                if metadata and metadata.get("school_id"):
                    email_map[metadata["school_id"]] = getattr(u, 'email', None)
            
            for school in schools_data:
                school['login_email'] = email_map.get(school['id'], 'Not set')
        except Exception as e:
            for school in schools_data:
                school['login_email'] = 'Unknown'
                
        return {"data": schools_data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/schools/{school_id}/reset-password")
async def reset_password(school_id: str, request: Request):
    verify_admin(request)
    try:
        users = supabase.auth.admin.list_users()
        target_user = None
        for u in users:
            metadata = getattr(u, 'user_metadata', {})
            if metadata and metadata.get("school_id") == school_id:
                target_user = u
                break
        
        if not target_user:
            raise HTTPException(status_code=404, detail="Auth user not found for this school")
            
        new_password = generate_password()
        supabase.auth.admin.update_user_by_id(target_user.id, {"password": new_password})
        
        return {"message": "Password reset successfully", "new_password": new_password, "email": target_user.email}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Fetch all students for a specific school
@app.get("/students/{school_id}")
async def get_students(school_id: str, request: Request):
    verify_admin(request)
    try:
        # We filter by the active school_id and order alphabetically by name
        response = supabase.table("students").select("*").eq("school_id", school_id).order("name").execute()
        students = [format_dob_for_frontend(s) for s in response.data]
        column_schema = get_schema_from_students(students)
        students = [strip_internal_custom_data(s) for s in students]
        return {"data": students, "column_schema": column_schema}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/upload-excel/{school_id}")
async def upload_excel(school_id: str, file: UploadFile = File(...), request: Request = None):
    verify_admin(request)
    if not file.filename.endswith(('.xlsx', '.xls', '.csv')):
        raise HTTPException(status_code=400, detail="Only Excel or CSV files are allowed")

    try:
        contents = await file.read()
        
        # Support both Excel and CSV uploads
        if file.filename.endswith('.csv'):
            df = pd.read_csv(io.BytesIO(contents))
        else:
            df = pd.read_excel(io.BytesIO(contents))
        
        # Drop columns that are entirely empty (e.g. trailing Excel columns)
        df = df.dropna(axis=1, how="all")
        # Also drop columns whose header starts with "Unnamed"
        df = df[[c for c in df.columns if not str(c).lower().startswith("unnamed")]]
        # Clean the dataframe (replace NaN with None)
        df = df.where(pd.notnull(df), None)
        records = df.to_dict(orient="records")
        
        column_schema = build_column_schema(df.columns, df)

        student_data = []
        for row in records:
            row_keys_lower = {str(k).lower().strip(): k for k in row.keys()}
            
            student = {
                "school_id": school_id,
                "custom_data": {
                    SCHEMA_KEY: column_schema
                }
            }

            for normalized, original_key in row_keys_lower.items():
                value = row.get(original_key)
                if value is None or str(value).strip() == "" or str(value) == "nan":
                    continue
                
                if isinstance(value, float) and value.is_integer():
                    value = int(value)
                
                if normalized in FIELD_MAP:
                    # Maps to a real DB column
                    col_name = FIELD_MAP[normalized]
                    val_str = str(value).strip()
                    
                    if col_name == "photo":
                        continue
                    elif col_name == "dob" and val_str:
                        try:
                            # Pass dayfirst=True to handle DD-MM-YYYY natively
                            parsed_date = pd.to_datetime(val_str, dayfirst=True).strftime("%Y-%m-%d")
                            student[col_name] = parsed_date
                        except Exception:
                            student["_invalid_dob"] = val_str
                    else:
                        student[col_name] = val_str
                else:
                    # Truly unknown column — goes to custom_data
                    student["custom_data"][original_key] = str(value).strip()

            # Ensure name exists
            if "name" not in student:
                student["name"] = "Unknown"
            
            # class has NOT NULL — default to empty string if missing
            if "class" not in student:
                student["class"] = ""

            student_data.append(student)

        # Check for duplicates and data validity in the Excel sheet before processing
        seen_admissions = {}
        seen_rolls = {} # (class, section) -> {roll: name}
        validation_errors = []
        valid_blood_groups = {"A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"}

        for idx, student in enumerate(student_data):
            name = student.get("name", "Unknown")
            identifier = name if name != "Unknown" else f"Row {idx+2}"

            # 1. Missing Name
            if name == "Unknown":
                validation_errors.append(f"Row {idx+2} is missing a student name")

            # 2. Duplicate Admission Number
            adm = student.get("admission_number")
            if adm:
                if adm in seen_admissions:
                    validation_errors.append(f"Duplicate Admission No. '{adm}': {identifier} & {seen_admissions[adm]}")
                else:
                    seen_admissions[adm] = identifier

            # 3. Duplicate Roll Number in same Class & Section
            roll = student.get("roll_number")
            cls = student.get("class", "").strip()
            sec = student.get("section", "").strip()
            if roll and cls:
                key = (cls, sec)
                if key not in seen_rolls:
                    seen_rolls[key] = {}
                if roll in seen_rolls[key]:
                    validation_errors.append(f"Duplicate Roll No. '{roll}' in Class {cls} Sec {sec}: {identifier} & {seen_rolls[key][roll]}")
                else:
                    seen_rolls[key][roll] = identifier

            # 4. Invalid Phone Number
            phone = student.get("phone")
            if phone:
                digits = "".join(filter(str.isdigit, str(phone)))
                if len(digits) == 12 and digits.startswith("91"):
                    digits = digits[2:]
                elif len(digits) == 11 and digits.startswith("0"):
                    digits = digits[1:]
                
                if len(digits) != 10:
                    validation_errors.append(f"Invalid Phone '{phone}' for {identifier}. Must be 10 digits.")
                else:
                    student["phone"] = digits

            # 5. Invalid Blood Group
            bg = student.get("blood_group")
            if bg:
                clean_bg = str(bg).strip().upper().replace(" ", "")
                if clean_bg not in valid_blood_groups:
                    validation_errors.append(f"Invalid Blood Group '{bg}' for {identifier}.")
                else:
                    student["blood_group"] = clean_bg

            # 6. Invalid DOB
            if "_invalid_dob" in student:
                validation_errors.append(f"Invalid Date of Birth '{student['_invalid_dob']}' for {identifier}. Use DD-MM-YYYY.")
                del student["_invalid_dob"]

        if validation_errors:
            error_msg = "Validation failed: " + " | ".join(validation_errors[:5])
            if len(validation_errors) > 5:
                error_msg += f" ...and {len(validation_errors) - 5} more issues."
            raise HTTPException(
                status_code=400,
                detail=error_msg
            )

        # ── Safe Upsert Strategy ──────────────────────────────────────────
        # Split students into those with an admission_number (can be matched)
        # and those without (must be inserted fresh).
        #
        # For students WITH admission_number:
        #   - If the school already has a matching record → UPDATE it (keeps photo!)
        #   - If no match → INSERT as new
        # For students WITHOUT admission_number → INSERT as new
        #
        # ── Bulletproof Overwrite Strategy ────────────────────────────────
        # Fetch existing students for this school
        existing = supabase.table("students").select("id, name, class, admission_number, photo_url").eq("school_id", school_id).execute()
        existing_data = existing.data or []
        
        # Build lookup maps
        by_adm = {r["admission_number"]: r for r in existing_data if r.get("admission_number")}
        by_name_class = {f"{str(r['name']).lower().strip()}|{str(r['class']).lower().strip()}": r for r in existing_data}

        inserted = 0
        updated = 0
        current_sheet_ids = set()

        for student in student_data:
            match = None
            adm = student.get("admission_number")
            name_key = f"{str(student.get('name')).lower().strip()}|{str(student.get('class')).lower().strip()}"
            
            # 1. Match by Admission Number (Highest priority)
            if adm and adm in by_adm:
                match = by_adm[adm]
            # 2. Fallback: Match by Name + Class
            elif name_key in by_name_class:
                match = by_name_class[name_key]
            
            if match:
                # OVERWRITE / UPDATE
                student.pop("school_id", None) # Security
                supabase.table("students").update(student).eq("id", match["id"]).execute()
                current_sheet_ids.add(match["id"])
                updated += 1
            else:
                # INSERT NEW
                student["school_id"] = school_id
                res = supabase.table("students").insert(student).execute()
                if res.data:
                    current_sheet_ids.add(res.data[0]["id"])
                inserted += 1

        # 3. CLEANUP: Delete students who are NOT in the latest sheet
        all_existing_ids = {r["id"] for r in existing_data}
        ids_to_remove = all_existing_ids - current_sheet_ids
        
        removed = 0
        if ids_to_remove:
            for rid in ids_to_remove:
                supabase.table("students").delete().eq("id", rid).execute()
                removed += 1

        return {
            "message": f"Sync complete: {updated} updated, {inserted} added, {removed} removed.",
            "inserted": inserted,
            "updated": updated,
            "removed": removed,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/upload-photo/{student_id}")
async def upload_photo(student_id: str, file: UploadFile = File(...), request: Request = None):
    verify_admin(request)
    # 1. Validate that it is actually an image
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    try:
        raw_contents = await file.read()
        contents = compress_image_to_target(raw_contents, target_kb=100)

        # 2. Delete old photo from storage to avoid orphan accumulation
        try:
            existing = supabase.table("students").select("photo_url").eq("id", student_id).single().execute()
            old_url = existing.data.get("photo_url") if existing.data else None
            if old_url:
                # Extract just the filename from the public URL
                old_filename = old_url.split("/")[-1].split("?")[0]
                supabase.storage.from_("student-photos").remove([old_filename])
        except Exception:
            pass  # If old photo cleanup fails, still proceed with upload
        
        # 3. Generate a unique filename
        file_extension = file.filename.split(".")[-1] if "." in file.filename else "jpg"
        unique_filename = f"{student_id}_{uuid.uuid4().hex}.{file_extension}"
        
        # 4. Upload the new image bytes to Supabase Storage
        supabase.storage.from_("student-photos").upload(
            file=contents,
            path=unique_filename,
            file_options={"content-type": file.content_type}
        )
        
        # 5. Get the public URL and update the student row
        public_url = supabase.storage.from_("student-photos").get_public_url(unique_filename)
        supabase.table("students").update({"photo_url": public_url}).eq("id", student_id).execute()
        
        return {
            "message": "Photo uploaded successfully!", 
            "photo_url": public_url
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------------------------------------------
# BULK PHOTO UPLOAD  (Admin Dashboard)
# ---------------------------------------------------------

def compress_image_to_target(image_bytes: bytes, target_kb: int = 100) -> bytes:
    """Compress an image to be under target_kb using Pillow.
    Progressively reduces quality and resolution until under budget."""
    img = Image.open(io.BytesIO(image_bytes))

    # Convert RGBA/P to RGB for JPEG
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    # Cap initial dimensions
    max_dim = 1024
    img.thumbnail((max_dim, max_dim), Image.LANCZOS)

    # Try progressively lower quality
    for quality in range(85, 5, -5):
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        if buf.tell() <= target_kb * 1024:
            return buf.getvalue()

    # Still too large — shrink dimensions further
    for dim in [800, 600, 400]:
        img.thumbnail((dim, dim), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=30, optimize=True)
        if buf.tell() <= target_kb * 1024:
            return buf.getvalue()

    # Return whatever we have
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=15, optimize=True)
    return buf.getvalue()


@app.post("/upload-photos/{school_id}")
async def upload_bulk_photos(
    school_id: str,
    match_column: str = Form(...),
    files: List[UploadFile] = File(...),
    request: Request = None,
):
    """Upload a batch of student photos.
    Each file's name (without extension) is matched against `match_column`
    of the students belonging to `school_id`.
    Images are compressed to < 100 KB before uploading to Supabase Storage.
    """
    verify_admin(request)

    # Fetch all students for this school
    resp = supabase.table("students").select("*").eq("school_id", school_id).execute()
    all_students = resp.data or []

    if not all_students:
        raise HTTPException(status_code=400, detail="No students found for this school")

    # Build a lookup: column_value -> student record
    # Supports core columns AND custom_data keys
    CORE_COLUMNS = ["name", "class", "section", "roll_number", "admission_number",
                    "dob", "fathers_name", "mothers_name", "blood_group",
                    "phone", "aadhar_number", "address", "house", "height", "weight"]

    student_lookup = {}
    for s in all_students:
        value = None
        if match_column in CORE_COLUMNS:
            value = s.get(match_column)
        else:
            # Check in custom_data
            value = (s.get("custom_data") or {}).get(match_column)

        if value:
            # Normalize: strip whitespace, lowercase for matching
            student_lookup[str(value).strip().lower()] = s

    matched = 0
    skipped = 0
    errors = []

    for f in files:
        # Extract the filename without extension for matching
        original_name = f.filename or ""
        # Handle nested folder paths (browser sends "subfolder/image.jpg")
        base_name = original_name.rsplit("/", 1)[-1]  # get last part
        base_name = base_name.rsplit("\\", 1)[-1]  # handle windows paths too
        name_without_ext = base_name.rsplit(".", 1)[0].strip().lower()

        if not name_without_ext:
            skipped += 1
            continue

        # Do we have a matching student?
        student = student_lookup.get(name_without_ext)
        if not student:
            skipped += 1
            errors.append(f"No match for '{base_name}'")
            continue

        try:
            contents = await f.read()

            # Compress to under 100 KB
            compressed = compress_image_to_target(contents, target_kb=100)

            # Delete old photo if exists
            old_url = student.get("photo_url")
            if old_url:
                try:
                    old_filename = old_url.split("/")[-1].split("?")[0]
                    supabase.storage.from_("student-photos").remove([old_filename])
                except Exception:
                    pass

            # Upload compressed image
            unique_filename = f"{student['id']}_{uuid.uuid4().hex}.jpg"
            supabase.storage.from_("student-photos").upload(
                file=compressed,
                path=unique_filename,
                file_options={"content-type": "image/jpeg"},
            )

            public_url = supabase.storage.from_("student-photos").get_public_url(unique_filename)
            supabase.table("students").update({"photo_url": public_url}).eq("id", student["id"]).execute()

            matched += 1
        except Exception as e:
            errors.append(f"Error processing '{base_name}': {str(e)}")
            skipped += 1

    return {
        "message": f"Bulk upload complete: {matched} matched, {skipped} skipped.",
        "matched": matched,
        "skipped": skipped,
        "errors": errors[:20],  # Cap error list so response isn't huge
    }

# ---------------------------------------------------------
# MOBILE APP ROUTES (Protected by Supabase JWT)
# ---------------------------------------------------------

@app.get("/mobile/students")
async def get_students_mobile(school_id: str = Depends(verify_school_user)):
    try:
        # Get student list
        response = supabase.table("students").select("*").eq("school_id", school_id).order("name").execute()
        students = [format_dob_for_frontend(s) for s in response.data]
        column_schema = get_schema_from_students(students)
        students = [strip_internal_custom_data(s) for s in students]
        
        # Get school name
        school_res = supabase.table("schools").select("name").eq("id", school_id).single().execute()
        school_name = school_res.data.get("name") if school_res.data else "Unknown School"

        return {
            "data": students,
            "school_name": school_name,
            "column_schema": column_schema,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/mobile/student/{student_id}")
async def delete_student_mobile(student_id: str, school_id: str = Depends(verify_school_user)):
    try:
        # Extra security: delete ONLY if the student belongs to the passed in school_id! (RLS usually does this, but safely fallback)
        response = supabase.table("students").delete().eq("id", student_id).eq("school_id", school_id).execute()
        
        # If response data is empty, either the student didn't exist or didn't belong to the school
        if not response.data:
            raise HTTPException(status_code=404, detail="Student not found or unauthorized")
        
        return {"message": "Student deleted successfully"}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/mobile/students/bulk-delete")
async def bulk_delete_students_mobile(payload: BulkDeleteRequest, school_id: str = Depends(verify_school_user)):
    student_ids = list(dict.fromkeys([sid for sid in payload.ids if sid]))
    if not student_ids:
        raise HTTPException(status_code=400, detail="No student IDs provided")

    try:
        deleted = 0
        for student_id in student_ids:
            response = supabase.table("students").delete().eq("id", student_id).eq("school_id", school_id).execute()
            if response.data:
                deleted += len(response.data)

        return {
            "message": f"{deleted} students deleted successfully",
            "deleted": deleted,
            "requested": len(student_ids),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/mobile/update-student/{student_id}")
async def update_student_mobile(student_id: str, update_data: dict, school_id: str = Depends(verify_school_user)):
    try:
        # First, ensure this student actually belongs to the caller's school
        check = supabase.table("students").select("school_id").eq("id", student_id).single().execute()
        if not check.data or check.data["school_id"] != school_id:
            raise HTTPException(status_code=403, detail="Unauthorized access to student")

        # Security: Prevent them from accidentally updating the ID or School ID
        update_data.pop("id", None)
        update_data.pop("school_id", None)
        update_data = format_dob_for_db(update_data)
        ensure_unique_admission_number(update_data, school_id, current_student_id=student_id)
        existing = supabase.table("students").select("custom_data").eq("id", student_id).single().execute()
        update_data = preserve_schema_in_custom_data(update_data, (existing.data or {}).get("custom_data"))

        # Push the changes directly to Supabase
        response = supabase.table("students").update(update_data).eq("id", student_id).execute()
        
        return {
            "message": "Student updated successfully", 
            "data": response.data
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/mobile/upload-photo/{student_id}")
async def upload_photo_mobile(student_id: str, file: UploadFile = File(...), school_id: str = Depends(verify_school_user)):
    # 1. Ensure ownership
    check = supabase.table("students").select("school_id").eq("id", student_id).single().execute()
    if not check.data or check.data["school_id"] != school_id:
        raise HTTPException(status_code=403, detail="Unauthorized access to student")

    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    try:
        raw_contents = await file.read()
        contents = compress_image_to_target(raw_contents, target_kb=100)

        # Delete old photo from storage to avoid orphan accumulation
        try:
            old_check = supabase.table("students").select("photo_url").eq("id", student_id).single().execute()
            old_url = old_check.data.get("photo_url") if old_check.data else None
            if old_url:
                old_filename = old_url.split("/")[-1].split("?")[0]
                supabase.storage.from_("student-photos").remove([old_filename])
        except Exception:
            pass  # Cleanup failure shouldn't block the upload

        file_extension = file.filename.split(".")[-1] if "." in file.filename else "jpg"
        unique_filename = f"{student_id}_{uuid.uuid4().hex}.{file_extension}"
        
        supabase.storage.from_("student-photos").upload(
            file=contents,
            path=unique_filename,
            file_options={"content-type": file.content_type}
        )
        
        public_url = supabase.storage.from_("student-photos").get_public_url(unique_filename)
        supabase.table("students").update({"photo_url": public_url}).eq("id", student_id).execute()
        
        return {"message": "Photo uploaded successfully!", "photo_url": public_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/mobile/sync")
async def sync_data(payload: dict, school_id: str = Depends(verify_school_user)):
    updates = payload.get("updates", [])
    creates = payload.get("creates", [])
    deletes = payload.get("deletes", [])

    try:
        for u in updates:
            # Pop the ID for the update body, but keep it for the filter
            student_id = u.pop("id", None)
            if not student_id: continue
            
            u = format_dob_for_db(u)
            existing = supabase.table("students").select("custom_data").eq("id", student_id).single().execute()
            u = preserve_schema_in_custom_data(u, (existing.data or {}).get("custom_data"))
            supabase.table("students") \
                .update(u) \
                .eq("id", student_id) \
                .eq("school_id", school_id) \
                .execute()

        schema_source = supabase.table("students").select("custom_data").eq("school_id", school_id).limit(1).execute()
        schema_rows = schema_source.data or []
        existing_schema_custom_data = (schema_rows[0] or {}).get("custom_data") if schema_rows else None

        for c in creates:
            c["school_id"] = school_id
            # Remove ID if present in creation to let DB generate it
            c.pop("id", None) 
            c = format_dob_for_db(c)
            if "custom_data" not in c:
                c["custom_data"] = {}
            ensure_unique_admission_number(c, school_id)
            c = preserve_schema_in_custom_data(c, existing_schema_custom_data)
            supabase.table("students").insert(c).execute()

        for d in deletes:
            student_id = d.get("id")
            if not student_id: continue
            
            supabase.table("students") \
                .delete() \
                .eq("id", student_id) \
                .eq("school_id", school_id) \
                .execute()

        return {"message": "Sync complete"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/mobile/student")
async def create_student_mobile(data: dict, school_id: str = Depends(verify_school_user)):
    try:
        # Assign the school ID from the token
        data["school_id"] = school_id
        
        # Remove None and empty string values so DB defaults kick in
        clean_data = {k: v for k, v in data.items() if v is not None and v != ""}
        clean_data = format_dob_for_db(clean_data)
        
        if "custom_data" not in clean_data:
            clean_data["custom_data"] = {}
        ensure_unique_admission_number(clean_data, school_id)
        schema_source = supabase.table("students").select("custom_data").eq("school_id", school_id).limit(1).execute()
        schema_rows = schema_source.data or []
        if schema_rows:
            clean_data = preserve_schema_in_custom_data(clean_data, (schema_rows[0] or {}).get("custom_data"))

        response = supabase.table("students").insert(clean_data).execute()
        return {"message": "Student created", "data": response.data}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=friendly_db_error(e))

# ---------------------------------------------------------
# SUPER ADMIN ROUTES
# ---------------------------------------------------------

# 1. Wipe all students for a school (The "Delete Excel" feature)
@app.delete("/students/school/{school_id}")
async def wipe_students(school_id: str, request: Request):
    verify_admin(request)
    try:
        # This deletes all students matching the school_id
        response = supabase.table("students").delete().eq("school_id", school_id).execute()
        return {"message": "All student records wiped successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 2. Delete a School entirely
@app.delete("/schools/{school_id}")
async def delete_school(school_id: str, request: Request):
    verify_admin(request)
    try:
        # Because we used "ON DELETE CASCADE" in our SQL earlier, 
        # deleting the school will automatically delete all its students too!
        response = supabase.table("schools").delete().eq("id", school_id).execute()
        
        # Clean up the associated user in Auth as well
        try:
            users = supabase.auth.admin.list_users()
            for u in users:
                metadata = getattr(u, 'user_metadata', {})
                if metadata and metadata.get("school_id") == school_id:
                    supabase.auth.admin.delete_user(u.id)
        except Exception:
            pass
            
        return {"message": "School deleted successfully."}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------------------------------------------
# INDIVIDUAL STUDENT OPERATIONS (Dashboard)
# ---------------------------------------------------------

# 1. Update Student Details (or Remove Photo by sending {"photo_url": None})
@app.put("/student/{student_id}")
async def update_student(student_id: str, update_data: dict, request: Request):
    verify_admin(request)
    try:
        # Security: Prevent changing core IDs
        update_data.pop("id", None)
        update_data.pop("school_id", None)
        update_data = format_dob_for_db(update_data)
        existing_school = supabase.table("students").select("school_id").eq("id", student_id).single().execute()
        if existing_school.data and existing_school.data.get("school_id"):
            ensure_unique_admission_number(update_data, existing_school.data["school_id"], current_student_id=student_id)
        existing = supabase.table("students").select("custom_data").eq("id", student_id).single().execute()
        update_data = preserve_schema_in_custom_data(update_data, (existing.data or {}).get("custom_data"))
        
        response = supabase.table("students").update(update_data).eq("id", student_id).execute()
        return {"message": "Student updated successfully", "data": response.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 2. Delete a Single Student
@app.delete("/student/{student_id}")
async def delete_student(student_id: str, request: Request):
    verify_admin(request)
    try:
        response = supabase.table("students").delete().eq("id", student_id).execute()
        return {"message": "Student deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/students/bulk-delete")
async def bulk_delete_students(payload: BulkDeleteRequest, request: Request):
    verify_admin(request)
    student_ids = list(dict.fromkeys([sid for sid in payload.ids if sid]))
    if not student_ids:
        raise HTTPException(status_code=400, detail="No student IDs provided")

    try:
        deleted = 0
        for student_id in student_ids:
            response = supabase.table("students").delete().eq("id", student_id).execute()
            if response.data:
                deleted += len(response.data)

        return {
            "message": f"{deleted} students deleted successfully",
            "deleted": deleted,
            "requested": len(student_ids),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 3. Create a Single Student
@app.post("/student")
async def create_student(data: dict, request: Request):
    verify_admin(request)
    try:
        if not data.get("school_id"):
            raise HTTPException(status_code=400, detail="school_id required")
        
        # Remove None and empty string values so DB defaults kick in
        clean_data = {k: v for k, v in data.items() if v is not None and v != ""}
        clean_data = format_dob_for_db(clean_data)
        
        # Make sure custom_data exists
        if "custom_data" not in clean_data:
            clean_data["custom_data"] = {}
        ensure_unique_admission_number(clean_data, clean_data["school_id"])
        schema_source = supabase.table("students").select("custom_data").eq("school_id", clean_data["school_id"]).limit(1).execute()
        schema_rows = schema_source.data or []
        if schema_rows:
            clean_data = preserve_schema_in_custom_data(clean_data, (schema_rows[0] or {}).get("custom_data"))

        response = supabase.table("students").insert(clean_data).execute()
        return {"message": "Student created", "data": response.data}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=friendly_db_error(e))

@app.get("/export/{school_id}")
async def export_students(school_id: str, request: Request):
    verify_admin(request)
    try:
        response = supabase.table("students").select("*").eq("school_id", school_id).order("class").execute()
        students = [format_dob_for_frontend(s) for s in response.data]
        column_schema = get_schema_from_students(students)

        # Flatten only the columns that belong to this school's uploaded sheet.
        flattened = []
        for s in students:
            row = {}
            for field in column_schema:
                header = field.get("header") or DISPLAY_LABELS.get(field.get("key"), field.get("key"))
                if not header:
                    continue
                row[header] = schema_value(s, field)
            flattened.append(row)

        return {"school_id": school_id, "total": len(flattened), "data": flattened, "column_schema": column_schema}
    except Exception as e:
        print(f"Export Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to export student data. Please try again.")

@app.get("/download-photos/{school_id}")
async def download_photos(school_id: str, request: Request, filename_column: str = None):
    """Download a ZIP file of all photos for a school"""
    verify_admin(request)
    try:
        response = supabase.table("students").select("*").eq("school_id", school_id).execute()
        students = response.data or []

        def zip_photo_name(s):
            if filename_column:
                if filename_column in CORE_EXPORT_FIELDS:
                    requested_value = s.get(filename_column)
                elif filename_column == "photo":
                    requested_value = photo_export_name(s).rsplit(".", 1)[0]
                else:
                    requested_value = (s.get("custom_data") or {}).get(filename_column)

                if requested_value:
                    safe_value = "".join(c for c in str(requested_value).strip() if c.isalnum() or c in ('-', '_', ' '))
                    if safe_value:
                        return f"{safe_value}.jpg"

            return photo_export_name(s)

        def download_single_photo(s):
            url = s.get("photo_url")
            if not url: return None
            filename_in_db = url.split("/")[-1].split("?")[0]
            try:
                photo_bytes = supabase.storage.from_("student-photos").download(filename_in_db)
                return (zip_photo_name(s), photo_bytes)
            except Exception as e:
                print(f"Error downloading {filename_in_db}: {e}")
                return None

        # Execute 10 at a time to scale for large schools without timing out
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            results = await loop.run_in_executor(
                None,
                lambda: list(executor.map(download_single_photo, students))
            )

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for res in results:
                if res is not None:
                    zip_file.writestr(res[0], res[1])
                        
        zip_buffer.seek(0)
        return StreamingResponse(
            zip_buffer, 
            media_type="application/zip", 
            headers={"Content-Disposition": f"attachment; filename=photos_{school_id}.zip"}
        )
    except Exception as e:
        print(f"Download Photos Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to securely package your photos. Please try again.")
