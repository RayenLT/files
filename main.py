from flask import Flask, render_template, request, redirect, url_for, jsonify
import json
import os
import requests
import mimetypes
from datetime import datetime
import hashlib
import urllib.parse
from dotenv import load_dotenv
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import re

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'your-secret-key-change-this-in-production')

# Configuration validation
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
GITHUB_OWNER = os.getenv('GITHUB_OWNER')
GITHUB_REPO = os.getenv('GITHUB_REPO')

if not all([GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO]):
    print("ERROR: Missing required environment variables:")
    if not GITHUB_TOKEN: print("- GITHUB_TOKEN")
    if not GITHUB_OWNER: print("- GITHUB_OWNER") 
    if not GITHUB_REPO: print("- GITHUB_REPO")
    print("Please set these in your environment or .env file")
    exit(1)

# File to store link mappings
LINKS_FILE = 'links.json'

# Simple session configuration for maximum reliability
session = requests.Session()
session.headers.update({
    'Authorization': f'token {GITHUB_TOKEN}',
    'Accept': 'application/vnd.github.v3+json',
    'User-Agent': 'Replit-File-Storage/1.0'
})

# Simple adapter with basic retry logic
adapter = requests.adapters.HTTPAdapter(
    pool_connections=5,
    pool_maxsize=10,
    max_retries=requests.adapters.Retry(
        total=2,
        read=1,
        connect=1,
        backoff_factor=1.0,
        status_forcelist=(500, 502, 503, 504)
    )
)
session.mount('https://', adapter)
session.mount('http://', adapter)

@app.after_request
def after_request(response):
    if request.endpoint == 'static':
        response.headers['Cache-Control'] = 'public, max-age=86400'
    response.headers.update({
        'X-Content-Type-Options': 'nosniff',
        'X-Frame-Options': 'DENY',
        'X-XSS-Protection': '1; mode=block'
    })
    return response

@app.template_filter('filesizeformat')
def filesizeformat(num_bytes):
    if not num_bytes:
        return 'Unknown'
    try:
        num_bytes = int(num_bytes)
        for unit in ['bytes', 'KB', 'MB', 'GB', 'TB']:
            if num_bytes < 1024.0:
                return f"{num_bytes} {unit}" if unit == 'bytes' else f"{num_bytes:.1f} {unit}"
            num_bytes /= 1024.0
        return f"{num_bytes:.1f} PB"
    except (ValueError, TypeError):
        return 'Unknown'

def load_links():
    if not os.path.exists(LINKS_FILE):
        return {}
    try:
        with open(LINKS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, IOError) as e:
        print(f"Warning: Error reading {LINKS_FILE}: {e}")
        backup_name = f"{LINKS_FILE}.backup.{int(time.time())}"
        try:
            os.rename(LINKS_FILE, backup_name)
            print(f"Corrupted file backed up as: {backup_name}")
        except:
            pass
        return {}

def save_links(links):
    try:
        with open(LINKS_FILE, 'w', encoding='utf-8') as f:
            json.dump(links, f, indent=2, ensure_ascii=False)
    except IOError as e:
        print(f"Error saving links: {e}")
        raise

def get_next_consecutive_id(links):
    numeric_ids = []
    for link_id in links.keys():
        try:
            numeric_ids.append(int(link_id))
        except ValueError:
            continue

    next_id = 0
    for existing_id in sorted(numeric_ids):
        if existing_id == next_id:
            next_id += 1
        elif existing_id > next_id:
            break
    return str(next_id)

def validate_custom_name(name):
    if not name:
        return True
    if not re.match(r'^[a-zA-Z0-9-_]+$', name):
        return False
    if len(name) > 50 or len(name) < 1:
        return False
    if name.startswith('-') or name.endswith('-'):
        return False
    return True

def create_github_release(tag_name, name, description="File storage"):
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases"
    data = {
        'tag_name': tag_name,
        'name': name,
        'body': description,
        'draft': False,
        'prerelease': False
    }

    try:
        print(f"Creating GitHub release: {name}")
        response = session.post(url, json=data)
        
        if response.status_code == 422:
            # Tag already exists, try with timestamp
            print("Tag exists, creating unique tag...")
            tag_name = f"{tag_name}-{int(time.time() * 1000)}"
            data['tag_name'] = tag_name
            response = session.post(url, json=data)
        
        if response.status_code == 401:
            raise Exception("GitHub authentication failed - check your token")
        elif response.status_code == 403:
            raise Exception("GitHub access forbidden - check token permissions")
        elif response.status_code == 404:
            raise Exception("GitHub repository not found - check GITHUB_OWNER and GITHUB_REPO")
        elif response.status_code == 422:
            error_detail = "Unknown validation error"
            try:
                error_data = response.json()
                error_detail = error_data.get('message', error_detail)
            except:
                pass
            raise Exception(f"GitHub validation error: {error_detail}")
        
        response.raise_for_status()
        print(f"GitHub release created successfully (ID: {response.json().get('id')})")
        return response.json()
    except requests.exceptions.RequestException as e:
        status_code = getattr(e.response, 'status_code', 'unknown') if hasattr(e, 'response') and e.response else 'unknown'
        raise Exception(f"GitHub release creation failed: {str(e)} (Status: {status_code})")

def upload_file_to_release(release_id, filename, file_content, content_type):
    url = f"https://uploads.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/{release_id}/assets"
    params = {'name': filename}

    try:
        print(f"Uploading file to GitHub: {filename} ({len(file_content)} bytes)")
        
        # Simple direct upload without complex session handling
        headers = {
            'Authorization': f'token {GITHUB_TOKEN}',
            'Content-Type': content_type,
            'Accept': 'application/vnd.github.v3+json'
        }
        
        print("Starting upload...")
        
        # Direct upload using requests.post
        response = requests.post(
            url, 
            params=params, 
            data=file_content, 
            headers=headers
        )
        
        print(f"Upload completed with status: {response.status_code}")
        
        if response.status_code == 401:
            raise Exception("GitHub authentication failed during upload")
        elif response.status_code == 403:
            raise Exception("GitHub upload forbidden - check token permissions")
        elif response.status_code == 422:
            error_detail = "Unknown error"
            try:
                error_data = response.json()
                error_detail = error_data.get('message', 'File may already exist or be invalid')
            except:
                pass
            raise Exception(f"GitHub upload failed: {error_detail}")
        elif response.status_code == 413:
            raise Exception("File too large for GitHub (max 2GB)")
        elif response.status_code >= 500:
            raise Exception("GitHub server error - please try again later")
        
        response.raise_for_status()
        print(f"File uploaded successfully to GitHub")
        return response.json()
        
    except requests.exceptions.RequestException as e:
        status_code = getattr(e.response, 'status_code', 'unknown') if hasattr(e, 'response') and e.response else 'unknown'
        raise Exception(f"GitHub upload failed: {str(e)} (Status: {status_code})")
    except Exception as e:
        raise Exception(f"Unexpected upload error: {str(e)}")

def extract_filename_from_url(url, response_headers, content_type):
    filename = None

    # Try Content-Disposition header
    content_disposition = response_headers.get('content-disposition', '')
    if 'filename=' in content_disposition:
        patterns = [
            r'filename\*=UTF-8\'\'(.+)',
            r'filename\*=utf-8\'\'(.+)', 
            r'filename="([^"]+)"',
            r'filename=([^;,\s]+)'
        ]
        for pattern in patterns:
            match = re.search(pattern, content_disposition, re.IGNORECASE)
            if match:
                filename = urllib.parse.unquote(match.group(1).strip('\'"'))
                if filename:
                    break

    # Try URL path
    if not filename:
        parsed_url = urllib.parse.urlparse(url)
        url_path = urllib.parse.unquote(parsed_url.path)
        if url_path and url_path != '/':
            path_parts = url_path.strip('/').split('/')
            for part in reversed(path_parts):
                if part and '.' in part:
                    filename = part
                    break

    # Try query parameters
    if not filename:
        parsed_url = urllib.parse.urlparse(url)
        query_params = urllib.parse.parse_qs(parsed_url.query)
        for param in ['filename', 'name', 'file', 'title']:
            if param in query_params and query_params[param]:
                potential = query_params[param][0]
                if potential and len(potential) > 2:
                    filename = urllib.parse.unquote(potential)
                    break

    # Generate fallback filename
    if not filename:
        base_name = "file"
        parsed_url = urllib.parse.urlparse(url)
        if parsed_url.path and parsed_url.path != '/':
            path_parts = [p for p in parsed_url.path.split('/') if p]
            if path_parts:
                base_name = re.sub(r'\.[^.]+$', '', path_parts[-1])[:20] or "file"

        # Determine extension from content-type
        extension_map = {
            'video/mp4': '.mp4', 'video/webm': '.webm', 'video/avi': '.avi',
            'audio/mpeg': '.mp3', 'audio/wav': '.wav', 'audio/ogg': '.ogg',
            'image/jpeg': '.jpg', 'image/png': '.png', 'image/gif': '.gif',
            'application/pdf': '.pdf', 'application/zip': '.zip',
            'text/plain': '.txt', 'application/json': '.json'
        }

        extension = extension_map.get(content_type.lower(), '')
        if not extension:
            if 'video' in content_type.lower(): extension = '.mp4'
            elif 'audio' in content_type.lower(): extension = '.mp3'
            elif 'image' in content_type.lower(): extension = '.jpg'
            elif 'text' in content_type.lower(): extension = '.txt'
            else: extension = '.bin'

        filename = f"{base_name}{extension}"

    # Clean filename
    filename = re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f-\x9f]', '_', filename)
    filename = filename.replace('..', '_')

    if len(filename) > 100:
        name, ext = os.path.splitext(filename)
        filename = name[:90] + ext

    if not filename or filename.startswith('.'):
        filename = f"file{filename}" if filename.startswith('.') else "file.bin"

    return filename

def download_and_upload_to_github(url, file_id):
    try:
        print(f"Starting download from: {url}")
        # Download file with no timeout restrictions
        response = session.get(url, stream=True)
        response.raise_for_status()

        content_type = response.headers.get('content-type', 'application/octet-stream')
        filename = extract_filename_from_url(url, response.headers, content_type)
        print(f"Detected filename: {filename}")

        # Get file size if available
        content_length = response.headers.get('content-length')
        if content_length:
            total_size = int(content_length)
            print(f"Expected file size: {total_size} bytes ({total_size / (1024*1024):.1f} MB)")
        else:
            total_size = None
            print("File size unknown")

        # Download content with minimal progress reporting to avoid blocking
        file_content = b''
        downloaded_size = 0
        chunk_size = 1024 * 1024  # 1MB chunks for better performance
        last_report = 0
        
        print("Downloading file...")
        for chunk in response.iter_content(chunk_size=chunk_size):
            if chunk:
                file_content += chunk
                downloaded_size += len(chunk)
                
                # Only report progress every 10MB to reduce console spam
                if downloaded_size - last_report >= 10 * 1024 * 1024:
                    mb_downloaded = downloaded_size / (1024 * 1024)
                    if total_size:
                        progress = (downloaded_size / total_size) * 100
                        print(f"Downloaded: {mb_downloaded:.1f} MB ({progress:.1f}%)")
                    else:
                        print(f"Downloaded: {mb_downloaded:.1f} MB")
                    last_report = downloaded_size

        print(f"Download complete: {len(file_content)} bytes ({len(file_content) / (1024*1024):.1f} MB)")

        # Check file size limits (GitHub has 2GB limit)
        if len(file_content) > 2 * 1024 * 1024 * 1024:  # 2GB
            raise Exception("File too large for GitHub (maximum 2GB)")

        # Create GitHub release and upload
        tag_name = f"f{file_id}-{int(time.time())}"
        release_name = f"File-{filename[:30]}"

        print("Creating GitHub release...")
        release = create_github_release(tag_name, release_name)
        
        print("Uploading file to GitHub...")
        asset = upload_file_to_release(release['id'], filename, file_content, content_type)

        print("Upload complete!")
        return {
            'filename': filename,
            'content_type': content_type,
            'file_size': len(file_content),
            'github_release_id': release['id'],
            'github_asset_id': asset['id'],
            'download_url': asset['browser_download_url'],
            'release_url': release['html_url']
        }

    except requests.exceptions.RequestException as e:
        print(f"Request error: {str(e)}")
        raise Exception(f"Request failed: {str(e)}")
    except Exception as e:
        print(f"Error in download_and_upload_to_github: {str(e)}")
        raise Exception(f"Processing failed: {str(e)}")

def delete_github_release(release_id):
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/{release_id}"
    response = session.delete(url)
    response.raise_for_status()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/create', methods=['POST'])
def create_permanent_link():
    try:
        temp_url = request.form.get('temp_url', '').strip()
        custom_name = request.form.get('custom_name', '').strip()

        if not temp_url:
            return jsonify({'error': 'No URL provided'}), 400

        # Accept any URL format - remove validation restrictions

        # Accept any custom name (no restrictions)

        links = load_links()

        # Generate unique ID
        link_id = custom_name if custom_name else get_next_consecutive_id(links)

        if link_id in links:
            return jsonify({'error': 'Custom name already exists'}), 400

        # Process file
        try:
            print(f"Processing file for link_id: {link_id}")
            file_info = download_and_upload_to_github(temp_url, link_id)
            print(f"File processing completed successfully")
        except Exception as e:
            print(f"File processing failed: {str(e)}")
            return jsonify({'error': f'Processing failed: {str(e)}'}), 500

        # Store mapping
        links[link_id] = {
            'original_url': temp_url,
            'created_at': datetime.now().isoformat(),
            'access_count': 0,
            'file_info': file_info
        }

        save_links(links)

        permanent_url = f"{request.host_url}download/{link_id}"

        return jsonify({
            'permanent_url': permanent_url,
            'link_id': link_id,
            'original_url': temp_url,
            'filename': file_info['filename'],
            'file_size': file_info['file_size'],
            'github_download_url': file_info['download_url']
        })

    except Exception as e:
        print(f"Error in create_permanent_link: {str(e)}")
        return jsonify({'error': f'Server error: {str(e)}'}), 500

@app.route('/download/<link_id>')
def download_file(link_id):
    links = load_links()

    if link_id not in links:
        return render_template('error.html', message='Link not found'), 404

    link_data = links[link_id]

    # Increment access count
    links[link_id]['access_count'] += 1
    save_links(links)

    try:
        download_url = link_data['file_info']['download_url']
        return redirect(download_url)
    except KeyError:
        return render_template('error.html', message='Download URL not found'), 500

@app.route('/link/<link_id>')
def redirect_to_download(link_id):
    return redirect(url_for('download_file', link_id=link_id))

@app.route('/stats/<link_id>')
def link_stats(link_id):
    links = load_links()
    if link_id not in links:
        return render_template('error.html', message='Link not found'), 404
    return render_template('stats.html', link_id=link_id, link_data=links[link_id])

@app.route('/api/links')
def list_links():
    return jsonify(load_links())

@app.route('/admin')
def admin_panel():
    return render_template('admin.html', links=load_links())

@app.route('/admin/edit/<link_id>', methods=['PUT'])
def edit_link(link_id):
    links = load_links()

    if link_id not in links:
        return jsonify({'error': 'Link not found'}), 404

    try:
        data = request.get_json()
        new_link_id = data.get('new_link_id', '').strip()

        if not new_link_id:
            return jsonify({'error': 'New link ID is required'}), 400

        # Accept any link ID format (no restrictions)

        if new_link_id in links and new_link_id != link_id:
            return jsonify({'error': 'Link ID already exists'}), 400

        if new_link_id == link_id:
            return jsonify({'success': True})

        # Move data to new ID
        links[new_link_id] = links[link_id]
        del links[link_id]
        save_links(links)

        return jsonify({'success': True})

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/delete/<link_id>', methods=['DELETE'])
def delete_link(link_id):
    links = load_links()

    if link_id not in links:
        return jsonify({'error': 'Link not found'}), 404

    try:
        link_data = links[link_id]

        # Delete GitHub release
        if 'file_info' in link_data and 'github_release_id' in link_data['file_info']:
            try:
                delete_github_release(link_data['file_info']['github_release_id'])
            except Exception as e:
                print(f"Warning: Failed to delete GitHub release: {e}")

        del links[link_id]
        save_links(links)

        return jsonify({'success': True})

    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)