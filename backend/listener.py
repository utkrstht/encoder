from fastapi import FastAPI, UploadFile, Form
import uvicorn, os, shutil
import tempfile

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

def get_service():
    creds = Credentials(
        None,
        refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["YOUTUBE_CLIENT_ID"],
        client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
        scopes=SCOPES,
    )
    creds.refresh(Request())
    return build("youtube", "v3", credentials=creds)

def get_service():
    creds = Credentials(
        None,
        refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["YOUTUBE_CLIENT_ID"],
        client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
        scopes=SCOPES,
    )
    creds.refresh(Request())
    return build("youtube", "v3", credentials=creds)

def upload_to_youtube(path, title, description):
    youtube = get_service()

    request_body = {
        "snippet": {"title": title, "description": description},
        "status": {"privacyStatus": "unlisted", "selfDeclaredMadeForKids": False},
    }

    media = MediaFileUpload(path, chunksize=-1, resumable=True)
    request = youtube.videos().insert(
        part="snippet,status",
        body=request_body,
        media_body=media,
    )

    while True:
        status, response = request.next_chunk()
        if response:
            return response["id"]

app = FastAPI()

@app.post("/upload")
async def upload_endpoint(
    video: UploadFile,
    title: str = Form(...),
    description: str = Form(""),
):
    tmp_path = os.path.join(tempfile.gettempdir(), video.filename)

    with open(tmp_path, "wb") as f:
        shutil.copyfileobj(video.file, f)

    video_id = upload_to_youtube(tmp_path, title, description)

    os.remove(tmp_path)
    return {"video_id": video_id}

if __name__ == "__main__":
    uvicorn.run("listener:app", host="localhost", port=8000)
