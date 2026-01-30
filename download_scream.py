"""
Download and extract Scream virtual audio driver from GitHub
"""
import urllib.request
import zipfile
import os
import json

# Scream latest release info
SCREAM_RELEASE_URL = "https://api.github.com/repos/duncanthrax/scream/releases/latest"
DOWNLOAD_DIR = "downloaded_drivers"

def download_scream():
    print("Fetching Scream latest release info...")
    
    # Get release info from GitHub API
    with urllib.request.urlopen(SCREAM_RELEASE_URL) as response:
        release_data = json.loads(response.read())
    
    print(f"Latest version: {release_data['tag_name']}")
    print(f"Published: {release_data['published_at']}")
    
    # Find x64 installer
    x64_asset = None
    for asset in release_data['assets']:
        if 'x64' in asset['name'] and asset['name'].endswith('.zip'):
            x64_asset = asset
            break
    
    if not x64_asset:
        print("ERROR: Could not find x64 installer!")
        return
    
    download_url = x64_asset['browser_download_url']
    filename = x64_asset['name']
    
    print(f"\nDownloading: {filename}")
    print(f"Size: {x64_asset['size'] / 1024 / 1024:.2f} MB")
    print(f"URL: {download_url}")
    
    # Create download directory
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    
    # Download file
    zip_path = os.path.join(DOWNLOAD_DIR, filename)
    print(f"\nDownloading to: {zip_path}")
    
    urllib.request.urlretrieve(download_url, zip_path)
    print("Download complete!")
    
    # Extract
    extract_dir = os.path.join(DOWNLOAD_DIR, "scream_extracted")
    os.makedirs(extract_dir, exist_ok=True)
    
    print(f"\nExtracting to: {extract_dir}")
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extract_dir)
    
    print("\nExtracted files:")
    for root, dirs, files in os.walk(extract_dir):
        for file in files:
            file_path = os.path.join(root, file)
            rel_path = os.path.relpath(file_path, extract_dir)
            size = os.path.getsize(file_path)
            print(f"  - {rel_path} ({size:,} bytes)")
    
    print(f"\n✅ Scream driver downloaded and extracted to: {extract_dir}")
    return extract_dir

if __name__ == "__main__":
    try:
        extract_dir = download_scream()
        if extract_dir:
            print("\n" + "="*60)
            print("NEXT STEPS:")
            print("="*60)
            print("1. Navigate to the extracted folder")
            print("2. Look for .sys, .inf, and .cat files")
            print("3. Use DevCon or Device Manager to install the driver")
            print("="*60)
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
