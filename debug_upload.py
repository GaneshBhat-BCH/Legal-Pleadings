import asyncio
import os
import sys
sys.path.append(os.getcwd())

from backend.routers.upload import upload_file, UploadRequest
from backend.database import database

async def test_upload():
    print("Connecting to DB...")
    await database.connect()
    
    req = UploadRequest(
        file_name="test_doc.pdf",
        pdf_text="This is a test document content. The researcher is Dr. Smith.",
        user_text="Is there any COI?"
    )
    
    # Mocking 'db' dependency manually since we call the function directly
    # The function expects 'db' as a parameter if not injected by Depends?
    # Wait, upload_file uses `db = Depends(get_db)`.
    # When calling directly, we must pass it.
    
    print("Calling upload_file...")
    try:
        result = await upload_file(request=req, db=database)
        print("Upload Result:", result)
    except Exception as e:
        print(f"Upload FAILED: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await database.disconnect()

if __name__ == "__main__":
    try:
        asyncio.run(test_upload())
    except Exception as e:
         print(f"Runner failed: {e}")
