"""Yanlış Bilinenler Uploader: complete, working upload script.

This is the YouTube part of the Yanlış Bilinenler Uploader, extracted into one
standalone file for the YouTube API Services audit. It does exactly what the tool
does after the channel owner approves a video in the review step:

  1. Authorizes with the owner's own Google account (OAuth 2.0, installed app).
  2. Uploads the approved video with videos.insert (resumable upload).
  3. Optionally sets the custom thumbnail with thumbnails.set.
  4. Reads the video's statistics with videos.list (owner's own video only).

Only the owner's own channel is accessed. No data is sent anywhere else.

Requirements:
    pip install google-api-python-client google-auth-oauthlib

Usage:
    python yukleme_betigi.py VIDEO.mp4 --title "Title" --description "Text" \
        [--tags a,b] [--thumbnail cover.jpg] [--privacy private|unlisted|public]

client_secret.json (Desktop app OAuth client) must be next to this file. The token is
saved to token.json on the same computer and reused on later runs.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]
HERE = Path(__file__).resolve().parent
CLIENT_SECRET = HERE / "client_secret.json"
TOKEN = HERE / "token.json"


def get_service():
    """Returns an authorized YouTube Data API v3 client for the owner's account."""
    creds = None
    if TOKEN.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
        creds = flow.run_local_server(port=0, prompt="select_account consent")
    TOKEN.write_text(creds.to_json(), encoding="utf-8")
    return build("youtube", "v3", credentials=creds)


def upload(service, video: Path, title: str, description: str, tags: list[str],
           privacy: str) -> str:
    """Uploads the video with videos.insert and returns the new video ID."""
    if "#shorts" not in description.lower():
        description = f"{description.strip()}\n\n#Shorts"
    body = {
        "snippet": {
            "title": title.strip()[:100],
            "description": description[:5000],
            "tags": tags[:15],
            "categoryId": "27",  # Education
            "defaultLanguage": "tr",
            "defaultAudioLanguage": "tr",
        },
        "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False},
    }
    media = MediaFileUpload(str(video), chunksize=4 * 1024 * 1024, resumable=True,
                            mimetype="video/mp4")
    request = service.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"Uploading: {int(status.progress() * 100)}%")
    return response["id"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Upload an approved video to our channel.")
    parser.add_argument("video", type=Path)
    parser.add_argument("--title", required=True)
    parser.add_argument("--description", default="")
    parser.add_argument("--tags", default="")
    parser.add_argument("--thumbnail", type=Path)
    parser.add_argument("--privacy", default="private",
                        choices=["private", "unlisted", "public"])
    args = parser.parse_args()

    if not args.video.exists():
        print(f"Video not found: {args.video}")
        return 1

    service = get_service()
    tags = [t.strip() for t in args.tags.split(",") if t.strip()]
    video_id = upload(service, args.video, args.title, args.description, tags, args.privacy)
    print(f"Uploaded: https://www.youtube.com/shorts/{video_id}")

    if args.thumbnail and args.thumbnail.exists():
        service.thumbnails().set(
            videoId=video_id, media_body=MediaFileUpload(str(args.thumbnail))
        ).execute()
        print("Thumbnail set.")

    resp = service.videos().list(part="status,statistics", id=video_id).execute()
    item = resp["items"][0]
    print(f"Privacy status: {item['status']['privacyStatus']}")
    print(f"Views: {item['statistics'].get('viewCount', '0')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
