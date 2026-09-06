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
import logging

logger = logging.getLogger(__name__)

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        logger.debug("Could not switch the console to UTF-8", exc_info=True)

LOCAL_PDF_LAKE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "pdf_lake")
os.makedirs(LOCAL_PDF_LAKE, exist_ok=True)
TARGET_BCTC_FILE = os.path.join(LOCAL_PDF_LAKE, "extracted_bctc_lake.json")
TARGET_CORP_FILE = os.path.join(LOCAL_PDF_LAKE, "extracted_corporate_actions.json")


def sync_from_google_drive() -> bool:
    gdrive_dir = os.getenv("GOOGLE_DRIVE_DATA_DIR", "G:/My Drive/vnstock_data/pdf_lake")
    gdrive_bctc = os.path.join(gdrive_dir, "extracted_bctc_lake.json")
    gdrive_corp = os.path.join(gdrive_dir, "extracted_corporate_actions.json")
    synced_any = False

    if os.path.exists(gdrive_bctc):
        try:
            sz_mb = os.path.getsize(gdrive_bctc) / (1024 * 1024)
            shutil.copy2(gdrive_bctc, TARGET_BCTC_FILE)
            print(f"✅ Synced BCTC Lake ({round(sz_mb, 2)} MB) from Google Drive: {gdrive_bctc}")
            synced_any = True
        except Exception as e:
            print(f"Error copying BCTC from Drive: {e}")

    if os.path.exists(gdrive_corp):
        try:
            sz_mb = os.path.getsize(gdrive_corp) / (1024 * 1024)
            shutil.copy2(gdrive_corp, TARGET_CORP_FILE)
            print(f"✅ Synced Corporate Actions Lake ({round(sz_mb, 2)} MB) from Google Drive: {gdrive_corp}")
            synced_any = True
        except Exception as e:
            print(f"Error copying Corporate Actions from Drive: {e}")

    return synced_any


def main():
    print("🔄 Checking for newest BCTC & Corporate Actions lake files...")
    if sync_from_google_drive():
        print("🎉 Local Data Lakes are 100% up-to-date!")
    else:
        print("💡 Ensure Google Drive is mounted or download artifacts from GitHub Actions tab.")


if __name__ == "__main__":
    main()
