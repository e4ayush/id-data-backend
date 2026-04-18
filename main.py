from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
import os
from pydantic import BaseModel
import pandas as pd
import io
import uuid
import random
import string
from database import supabase

app = FastAPI()

# 1. CORS Setup: Allow Next.js to talk to FastAPI
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        os.getenv("FRONTEND_URL", "")
    ], 
    allow_credentials=True,
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

class SchoolCreate(BaseModel):
    name: str

def generate_password(length=10):
    """Generates a random 10-character password"""
    chars = string.ascii_letters + string.digits + "@#$%"
    return ''.join(random.choice(chars) for _ in range(length))

@app.post("/create-school")
async def create_school(school: SchoolCreate, request: Request):
    verify_admin(request)
    try:
        # 1. Create the school in the Database
        db_response = supabase.table("schools").insert({"name": school.name}).execute()
        school_data = db_response.data[0]
        school_id = school_data["id"]

        # 2. Generate Login Credentials for the Mobile App
        # Removes spaces to make a clean email (e.g., "DPS Patna" -> "admin@dpspatna.com")
        clean_name = "".join(e for e in school.name if e.isalnum()).lower()
        email = f"admin@{clean_name}.com"
        password = generate_password()

        # 3. Create the User in Supabase Auth (Using the Admin API)
        supabase.auth.admin.create_user({
            "email": email,
            "password": password,
            "email_confirm": True, # Auto-confirm so they don't need an email link
            "user_metadata": {
                "school_id": school_id, # Tie this login to their specific school
                "role": "school_admin"
            }
        })

        return {
            "message": "School and credentials created", 
            "data": school_data,
            "credentials": {
                "email": email,
                "password": password
            }
        }
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
        return {"data": response.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Fetch all students for a specific school
@app.get("/students/{school_id}")
async def get_students(school_id: str, request: Request):
    verify_admin(request)
    try:
        # We filter by the active school_id and order alphabetically by name
        response = supabase.table("students").select("*").eq("school_id", school_id).order("name").execute()
        return {"data": response.data}
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
        
        # Clean the dataframe (replace NaN with None)
        df = df.where(pd.notnull(df), None)
        records = df.to_dict(orient="records")
        
        # Extended core field mapping — covers your actual schema
        field_map = {
            "name": "name",
            "class": "class",
            "section": "section",
            "roll number": "roll_number",
            "roll": "roll_number",
            "admission number": "admission_number",
            "admission no": "admission_number",
            "dob": "dob",
            "date of birth": "dob",
            "father name": "fathers_name",
            "fathers name": "fathers_name",
            "father's name": "fathers_name",
            "mother name": "mothers_name",
            "mothers name": "mothers_name",
            "mother's name": "mothers_name",
            "blood group": "blood_group",
            "height": "height",
            "weight": "weight",
            "house": "house",
            "address": "address",
            "phone": "phone",
            "phone number": "phone",
            "aadhar": "aadhar_number",
            "aadhar number": "aadhar_number",
        }

        student_data = []
        for row in records:
            row_keys_lower = {str(k).lower().strip(): k for k in row.keys()}
            
            student = {
                "school_id": school_id,
                "custom_data": {}
            }

            for normalized, original_key in row_keys_lower.items():
                value = row.get(original_key)
                if value is None or str(value).strip() == "" or str(value) == "nan":
                    continue
                
                if normalized in field_map:
                    # Maps to a real DB column
                    student[field_map[normalized]] = str(value).strip()
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

        # Wipe existing students for this school first, then insert fresh
        supabase.table("students").delete().eq("school_id", school_id).execute()
        response = supabase.table("students").insert(student_data).execute()

        return {"message": f"Dynamically uploaded {len(student_data)} students!", "data": response.data}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/upload-photo/{student_id}")
async def upload_photo(student_id: str, file: UploadFile = File(...), request: Request = None):
    verify_admin(request)
    # 1. Validate that it is actually an image
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    try:
        contents = await file.read()
        
        # 2. Generate a unique filename so photos don't overwrite each other
        file_extension = file.filename.split(".")[-1]
        unique_filename = f"{student_id}_{uuid.uuid4().hex}.{file_extension}"
        
        # 3. Upload the raw image bytes to your Supabase Storage bucket
        supabase.storage.from_("student-photos").upload(
            file=contents,
            path=unique_filename,
            file_options={"content-type": file.content_type}
        )
        
        # 4. Get the public URL for that newly uploaded image
        public_url = supabase.storage.from_("student-photos").get_public_url(unique_filename)
        
        # 5. Update the student's database row with the new photo_url
        supabase.table("students").update({"photo_url": public_url}).eq("id", student_id).execute()
        
        return {
            "message": "Photo uploaded successfully!", 
            "photo_url": public_url
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# We accept a raw dictionary so the Flutter app can send 1 field or 10 fields to update
# TODO: add JWT verification from Supabase Auth before Flutter launch
@app.put("/mobile/update-student/{student_id}")
async def update_student_mobile(student_id: str, update_data: dict):
    try:
        # Example flutter request body: {"name": "Ayush Verman", "roll_number": "42"}
        
        # Security: Prevent them from accidentally updating the ID or School ID
        if "id" in update_data: del update_data["id"]
        if "school_id" in update_data: del update_data["school_id"]

        # Push the changes directly to Supabase
        response = supabase.table("students").update(update_data).eq("id", student_id).execute()
        
        return {
            "message": "Student updated successfully", 
            "data": response.data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
        return {"message": "School deleted successfully."}
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

# 3. Create a Single Student
@app.post("/student")
async def create_student(data: dict, request: Request):
    verify_admin(request)
    try:
        if not data.get("school_id"):
            raise HTTPException(status_code=400, detail="school_id required")
        
        # Remove None and empty string values so DB defaults kick in
        clean_data = {k: v for k, v in data.items() if v is not None and v != ""}
        
        # Make sure custom_data exists
        if "custom_data" not in clean_data:
            clean_data["custom_data"] = {}

        response = supabase.table("students").insert(clean_data).execute()
        return {"message": "Student created", "data": response.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/export/{school_id}")
async def export_students(school_id: str, request: Request):
    verify_admin(request)
    try:
        response = supabase.table("students").select("*").eq("school_id", school_id).order("class").execute()
        students = response.data

        # Flatten custom_data into the main row so Datrix gets clean columns
        flattened = []
        for s in students:
            row = {
                "name": s.get("name"),
                "class": s.get("class"),
                "section": s.get("section"),
                "roll_number": s.get("roll_number"),
                "admission_number": s.get("admission_number"),
                "photo_url": s.get("photo_url"),
            }
            # Merge custom_data fields into the flat row
            if s.get("custom_data"):
                row.update(s["custom_data"])
            flattened.append(row)

        return {"school_id": school_id, "total": len(flattened), "data": flattened}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))