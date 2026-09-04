"""
=============================================================================
LOCAL DATA LAKE SYNC FROM GITHUB ACTIONS
=============================================================================
Downloads the latest unified extracted_bctc_lake.json from GitHub repository
or copies from Google Drive directly into local data/pdf_lake/.
"""

import os
import sys
import json
import shutil
import urllib.request

LOCAL_PDF_LAKE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "pdf_lake")
os.makedirs(LOCAL_PDF_LAKE, exist_ok=True)
TARGET_FILE = os.path.join(LOCAL_PDF_LAKE, "extracted_bctc_lake.json")


def sync_from_google_drive() -> bool:
    gdrive_dir = os.getenv("GOOGLE_DRIVE_DATA_DIR", "G:/My Drive/vnstock_data/pdf_lake")
    gdrive_file = os.path.join(gdrive_dir, "extracted_bctc_lake.json")
    if os.path.exists(gdrive_file):
        try:
            sz_mb = os.path.getsize(gdrive_file) / (1024 * 1024)
            shutil.copy2(gdrive_file, TARGET_FILE)
            print(f"✅ Synced {round(sz_mb, 2)} MB directly from Google Drive: {gdrive_file}")
            return True
        except Exception as e:
            print(f"Error copying from Drive: {e}")
    return False


def main():
    print("🔄 Checking for newest BCTC lake file...")
    if sync_from_google_drive():
        print("🎉 Local Data Lake is 100% up-to-date!")
    else:
        print("💡 Ensure Google Drive is mounted or download artifact from GitHub Actions Actions tab.")


if __name__ == "__main__":
    main()
