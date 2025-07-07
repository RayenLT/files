from flask import Flask, render_template, request, redirect, url_for, jsonify
import json
import os
import requests
import mimetypes
from datetime import datetime, timedelta
from urllib.parse import urlparse
import hashlib
import urllib.parse
from dotenv import load_dotenv
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import asyncio
import aiohttp
import aiofiles
import gzip
from flask import Response

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'your-secret-key-change-this-in-production')

# Enable compression for better performance
@app.after_request
def after_request(response):
    # Add caching headers for static content
    if request.endpoint == 'static':
        response.headers['Cache-Control'] = 'public, max-age=86400'  # 24 hours

    # Add security headers
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'

    return response

@app.template_filter('filesizeformat')
def filesizeformat(num_bytes):
    """Format a file size in bytes as a human readable string"""
    if num_bytes is None:
        return 'Unknown'

    try:
        num_bytes = int(num_bytes)
    except (ValueError, TypeError):
        return 'Unknown'

    for unit in ['bytes', 'KB', 'MB', 'GB', 'TB']:
        if num_bytes < 1024.0:
            if unit == 'bytes':
                return f"{num_bytes} {unit}"
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} PB"

# File to store link mappings
LINKS_FILE = 'links.json'

# GitHub configuration from environment variables
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
GITHUB_OWNER = os.getenv('GITHUB_OWNER')
GITHUB_REPO = os.getenv('GITHUB_REPO')

# Global session with optimized connection pooling for maximum performance
github_session = requests.Session()
github_session.headers.update({
    'Authorization': f'token {GITHUB_TOKEN}' if GITHUB_TOKEN else '',
    'Accept': 'application/vnd.github.v3+json'
})

# Download session with maximum optimizations
download_session = requests.Session()
download_session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
})

# Configure ultra-aggressive connection pooling for maximum speed
adapter = requests.adapters.HTTPAdapter(
    pool_connections=50,  # Increased from 20
    pool_maxsize=100,     # Increased from 50
    max_retries=1,        # Reduced for faster failures
    pool_block=False
)
github_session.mount('https://', adapter)
download_session.mount('https://', adapter)
download_session.mount('http://', adapter)

# Keep connections alive longer
github_session.keep_alive = True
download_session.keep_alive = True

if not all([GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO]):
    print("Warning: GitHub configuration missing. Please set GITHUB_TOKEN, GITHUB_OWNER, and GITHUB_REPO environment variables.")



def load_links():
    """Load links from JSON file"""
    if os.path.exists(LINKS_FILE):
        try:
            with open(LINKS_FILE, 'r') as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
                else:
                    print(f"Warning: {LINKS_FILE} contains invalid data format, resetting to empty dict")
                    return {}
        except json.JSONDecodeError as e:
            print(f"Warning: {LINKS_FILE} contains invalid JSON: {e}, creating backup and resetting")
            # Create backup of corrupted file
            backup_name = f"{LINKS_FILE}.backup.{int(datetime.now().timestamp())}"
            try:
                os.rename(LINKS_FILE, backup_name)
                print(f"Corrupted file backed up as: {backup_name}")
            except:
                pass
            return {}
        except Exception as e:
            print(f"Warning: Error reading {LINKS_FILE}: {e}")
            return {}
    return {}

def save_links(links):
    """Save links to JSON file"""
    with open(LINKS_FILE, 'w') as f:
        json.dump(links, f, indent=2)

def get_next_consecutive_id(links):
    """Get the next consecutive integer ID"""
    # Get all existing numeric IDs
    numeric_ids = []
    for link_id in links.keys():
        try:
            numeric_ids.append(int(link_id))
        except ValueError:
            # Skip non-numeric IDs
            continue

    # Find the next available consecutive ID starting from 0
    next_id = 0
    numeric_ids.sort()
    for existing_id in numeric_ids:
        if existing_id == next_id:
            next_id += 1
        elif existing_id > next_id:
            break

    return str(next_id)

def create_github_release(tag_name, name, description="File storage"):
    """Ultra-fast GitHub release creation"""
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases"
    data = {
        'tag_name': tag_name,
        'name': name,
        'body': description,
        'draft': False,
        'prerelease': False
    }

    try:
        print(f"Creating release: {tag_name}")
        start_time = time.time()

        response = github_session.post(url, json=data, timeout=(5, 30))
        elapsed_time = time.time() - start_time
        print(f"Release: {elapsed_time:.2f}s - {response.status_code}")

        if response.status_code != 201:
            raise Exception(f"API error: {response.status_code}")

        result = response.json()
        print(f"✅ Release: {result['id']}")
        return result
    except Exception as e:
        print(f"Release error: {str(e)}")
        raise Exception(f"GitHub API failed: {str(e)}")

def upload_file_to_release(release_id, filename, file_content, content_type):
    """Ultra-fast upload to GitHub release"""
    url = f"https://uploads.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/{release_id}/assets"

    # Reuse github_session for upload to avoid session overhead
    headers = {
        'Authorization': f'token {GITHUB_TOKEN}',
        'Content-Type': content_type,
        'Accept': 'application/vnd.github.v3+json'
    }

    params = {'name': filename}

    try:
        print(f"Uploading: {filename} ({len(file_content)/1024/1024:.1f} MB)")
        start_time = time.time()

        # Use github_session with custom headers for this request
        response = requests.post(url, params=params, data=file_content, headers=headers, timeout=(10, 300))

        elapsed_time = time.time() - start_time
        upload_speed = (len(file_content)/1024/1024) / elapsed_time if elapsed_time > 0 else 0
        print(f"Upload: {elapsed_time:.2f}s ({upload_speed:.1f} MB/s)")

        if response.status_code != 201:
            raise Exception(f"Upload error: {response.status_code}")

        result = response.json()
        print(f"✅ Uploaded: {result['id']}")
        return result
    except Exception as e:
        print(f"Upload error: {str(e)}")
        raise Exception(f"GitHub upload failed: {str(e)}")

def download_and_upload_to_github(url, file_id):
    """Ultra-optimized download and upload with maximum parallelization"""
    try:
        print(f"Starting ultra-fast download from: {url}")
        start_total = time.time()

        # Skip HEAD request for speed - go straight to download
        response = download_session.get(url, stream=True, timeout=(5, 30))
        response.raise_for_status()
        print(f"Download started - Status: {response.status_code}")

        # Get file info quickly
        content_length = response.headers.get('content-length')
        total_size = int(content_length) if content_length else None
        content_type = response.headers.get('content-type', 'application/octet-stream')

        if total_size:
            print(f"File size: {total_size / 1024 / 1024:.1f} MB")

        # Enhanced filename extraction to preserve original download filename
        filename = None
        import re

        # Try Content-Disposition header first (most reliable for original filename)
        content_disposition = response.headers.get('content-disposition', '')
        if 'filename=' in content_disposition:
            # Try different Content-Disposition formats
            patterns = [
                r'filename\*=UTF-8\'\'(.+)',  # RFC 5987 format
                r'filename\*=utf-8\'\'(.+)',  # Alternative UTF-8 format
                r'filename="([^"]+)"',        # Quoted filename
                r'filename=([^;,\s]+)'        # Unquoted filename
            ]

            for pattern in patterns:
                match = re.search(pattern, content_disposition, re.IGNORECASE)
                if match:
                    extracted_filename = urllib.parse.unquote(match.group(1).strip())
                    # Remove any remaining quotes or whitespace
                    extracted_filename = extracted_filename.strip('\'"')
                    if extracted_filename and len(extracted_filename) > 0:
                        filename = extracted_filename
                        print(f"✅ Filename from Content-Disposition: {filename}")
                        break

        # If not found, try URL path (preserve exact filename from URL)
        if not filename:
            parsed_url = urlparse(url)
            url_path = urllib.parse.unquote(parsed_url.path)
            if url_path and url_path != '/':
                # Get the last part of the path that looks like a filename
                path_parts = url_path.strip('/').split('/')
                for part in reversed(path_parts):
                    if part and ('.' in part):  # Must have extension to be a filename
                        filename = part
                        print(f"✅ Filename from URL path: {filename}")
                        break

        # Try query parameters for filename
        if not filename:
            parsed_url = urlparse(url)
            from urllib.parse import parse_qs
            query_params = parse_qs(parsed_url.query)

            # Common filename parameters
            filename_params = ['filename', 'name', 'file', 'title', 'download', 'f']
            for param in filename_params:
                if param in query_params and query_params[param]:
                    potential_filename = query_params[param][0]
                    if potential_filename and len(potential_filename) > 2:
                        filename = urllib.parse.unquote(potential_filename)
                        print(f"✅ Filename from query parameter '{param}': {filename}")
                        break

        # Only create fallback if we absolutely can't determine the original filename
        if not filename:
            print("⚠️ Could not determine original filename, creating fallback...")

            # Try to get a meaningful base name from URL path
            parsed_url = urlparse(url)
            base_name = "file"

            if parsed_url.path and parsed_url.path != '/':
                path_parts = [p for p in parsed_url.path.split('/') if p and not p.isdigit()]
                if path_parts:
                    # Use the last meaningful part
                    last_part = path_parts[-1]
                    # Remove common file extensions to get base name
                    base_name = re.sub(r'\.[^.]+$', '', last_part)[:20]
                    if not base_name or len(base_name) < 2:
                        base_name = "file"

            # Determine extension from content-type
            extension = ''
            content_type_lower = content_type.lower()

            # Map content types to extensions
            content_type_extensions = {
                'video/mp4': '.mp4',
                'video/webm': '.webm',
                'video/avi': '.avi',
                'video/quicktime': '.mov',
                'audio/mpeg': '.mp3',
                'audio/mp3': '.mp3',
                'audio/wav': '.wav',
                'audio/ogg': '.ogg',
                'image/jpeg': '.jpg',
                'image/jpg': '.jpg',
                'image/png': '.png',
                'image/gif': '.gif',
                'image/webp': '.webp',
                'application/pdf': '.pdf',
                'application/zip': '.zip',
                'application/x-rar-compressed': '.rar',
                'text/plain': '.txt',
                'application/json': '.json',
                'application/xml': '.xml',
                'text/html': '.html'
            }

            # Try exact match first
            extension = content_type_extensions.get(content_type_lower, '')

            # If no exact match, try partial matches
            if not extension:
                if 'video' in content_type_lower:
                    extension = '.mp4'
                elif 'audio' in content_type_lower:
                    extension = '.mp3'
                elif 'image' in content_type_lower:
                    extension = '.jpg'
                elif 'pdf' in content_type_lower:
                    extension = '.pdf'
                elif 'zip' in content_type_lower:
                    extension = '.zip'
                elif 'text' in content_type_lower:
                    extension = '.txt'
                else:
                    # Try to guess from URL path
                    if parsed_url.path:
                        url_ext = os.path.splitext(parsed_url.path)[1]
                        if url_ext and len(url_ext) <= 5:
                            extension = url_ext
                        else:
                            extension = '.bin'
                    else:
                        extension = '.bin'

            filename = f"{base_name}{extension}"
            print(f"⚠️ Using fallback filename: {filename}")

        # Clean and validate filename (preserve original name as much as possible)
        if filename:
            # Only replace truly problematic characters, preserve original as much as possible
            original_filename = filename
            filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
            filename = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', filename)  # Remove control characters
            filename = filename.replace('..', '_')  # Prevent directory traversal

            # Ensure filename isn't too long
            if len(filename) > 100:
                name, ext = os.path.splitext(filename)
                filename = name[:90] + ext

            # Ensure filename isn't empty or just extension
            if not filename or filename.startswith('.'):
                filename = f"file{filename}" if filename.startswith('.') else "file.bin"

            if filename != original_filename:
                print(f"📝 Cleaned filename: {original_filename} → {filename}")
            else:
                print(f"✅ Final filename: {filename}")
        else:
            filename = "file.bin"
            print(f"⚠️ Emergency fallback filename: {filename}")

        # Pre-create GitHub release info
        tag_name = f"f{file_id}{int(time.time())}"  # Shorter tag
        release_name = f"File-{filename[:30]}"  # Shorter name

        # Maximum parallelization with 4 workers
        with ThreadPoolExecutor(max_workers=4) as executor:
            # Start release creation immediately
            release_future = executor.submit(create_github_release, tag_name, release_name, "File storage")

            # Ultra-fast download with 5MB chunks
            file_content = b''
            chunk_size = 5 * 1024 * 1024  # 5MB chunks for maximum speed
            downloaded_size = 0
            download_start = time.time()

            # Download with minimal progress tracking for speed
            chunks = []
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    chunks.append(chunk)
                    downloaded_size += len(chunk)

            # Combine chunks in parallel
            file_content = b''.join(chunks)

            download_time = time.time() - download_start
            download_speed = (downloaded_size/1024/1024) / download_time if download_time > 0 else 0
            print(f"Download: {downloaded_size / 1024 / 1024:.1f} MB in {download_time:.2f}s ({download_speed:.1f} MB/s)")

            # Wait for release and upload in parallel
            release = release_future.result()

        # Ultra-fast upload
        print(f"Ultra-fast uploading...")
        try:
            asset = upload_file_to_release(release['id'], filename, file_content, content_type)

            total_time = time.time() - start_total
            print(f"⚡ COMPLETE! Total: {total_time:.2f}s")

            return {
                'filename': filename,
                'content_type': content_type,
                'file_size': len(file_content),
                'github_release_id': release['id'],
                'github_asset_id': asset['id'],
                'download_url': asset['browser_download_url'],
                'release_url': release['html_url']
            }
        except Exception as upload_error:
            try:
                delete_github_release(release['id'])
            except:
                pass
            raise upload_error

    except Exception as e:
        print(f"Error: {str(e)}")
        raise Exception(f"Processing failed: {str(e)}")

def delete_github_release(release_id):
    """Delete a GitHub release using optimized session"""
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/{release_id}"
    response = github_session.delete(url)
    response.raise_for_status()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/create', methods=['POST'])
def create_permanent_link():
    """Create a permanent link from a temporary one"""
    try:
        temp_url = request.form.get('temp_url')
        custom_name = request.form.get('custom_name', '').strip()

        if not temp_url:
            return jsonify({'error': 'No URL provided'}), 400

        if not all([GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO]):
            return jsonify({'error': 'GitHub configuration missing. Please set GITHUB_TOKEN, GITHUB_OWNER, and GITHUB_REPO environment variables.'}), 500

        # Load existing links first
        links = load_links()

        # Generate unique ID
        if custom_name:
            link_id = custom_name
        else:
            link_id = get_next_consecutive_id(links)

        # Check if custom name already exists
        if custom_name and link_id in links:
            return jsonify({'error': 'Custom name already exists'}), 400

        print(f"Processing upload for URL: {temp_url}")
        print(f"Generated link_id: {link_id}")

        # Download and upload to GitHub
        file_info = download_and_upload_to_github(temp_url, link_id)

        print(f"Upload successful: {file_info}")

        # Store the mapping
        links[link_id] = {
            'original_url': temp_url,
            'created_at': datetime.now().isoformat(),
            'access_count': 0,
            'file_info': file_info
        }

        save_links(links)

        permanent_url = f"{request.host_url}download/{link_id}"

        response_data = {
            'permanent_url': permanent_url,
            'link_id': link_id,
            'original_url': temp_url,
            'filename': file_info['filename'],
            'file_size': file_info['file_size'],
            'github_download_url': file_info['download_url']
        }

        print(f"Sending success response: {response_data}")
        response = jsonify(response_data)
        response.headers['Content-Type'] = 'application/json'
        return response

    except Exception as e:
        error_msg = str(e)
        print(f"Error in create_permanent_link: {error_msg}")
        print(f"Error type: {type(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")

        # Ensure we always return JSON
        error_response = jsonify({'error': f'Server error: {error_msg}'})
        error_response.headers['Content-Type'] = 'application/json'
        print(f"Sending error response: {error_msg}")
        return error_response, 500

@app.route('/download/<link_id>')
def download_file(link_id):
    """Redirect to the GitHub download URL"""
    links = load_links()

    if link_id not in links:
        return jsonify({'error': 'Link not found'}), 404

    link_data = links[link_id]

    # Increment access count
    links[link_id]['access_count'] += 1
    save_links(links)

    try:
        file_info = link_data['file_info']
        download_url = file_info['download_url']

        # Redirect to GitHub download URL
        return redirect(download_url)

    except Exception as e:
        return jsonify({'error': f'Error accessing file: {str(e)}'}), 500

# Keep the old redirect route for backwards compatibility
@app.route('/link/<link_id>')
def redirect_to_download(link_id):
    """Redirect old links to download endpoint"""
    return redirect(url_for('download_file', link_id=link_id))

@app.route('/api/links')
def list_links():
    """API endpoint to list all links"""
    links = load_links()
    return jsonify(links)

@app.route('/admin')
def admin_panel():
    """Admin panel to manage links"""
    import re
    
    def natural_sort_key(item):
        """Convert a string into a list of string and number chunks for natural sorting"""
        link_id = item[0]  # Get the link_id from the tuple
        # Split the string into text and number parts
        parts = re.split(r'(\d+)', link_id)
        # Convert number parts to integers for proper numerical comparison
        return [(int(part) if part.isdigit() else part.lower()) for part in parts]
    
    links = load_links()
    # Sort the links using natural sorting
    sorted_links = dict(sorted(links.items(), key=natural_sort_key))
    return render_template('admin.html', links=sorted_links)



@app.route('/admin/edit/<link_id>', methods=['PUT'])
def edit_link(link_id):
    """Edit a link's ID/name"""
    links = load_links()

    if link_id not in links:
        return jsonify({'error': 'Link not found'}), 404

    try:
        data = request.get_json()
        new_link_id = data.get('new_link_id', '').strip()

        if not new_link_id:
            return jsonify({'error': 'New link ID is required'}), 400

        # Validate new link ID format
        import re
        if not re.match(r'^[a-zA-Z0-9-_]+$', new_link_id):
            return jsonify({'error': 'Link ID can only contain letters, numbers, hyphens, and underscores'}), 400

        if len(new_link_id) > 50:
            return jsonify({'error': 'Link ID must be 50 characters or less'}), 400

        if new_link_id.startswith('-') or new_link_id.endswith('-'):
            return jsonify({'error': 'Link ID cannot start or end with a hyphen'}), 400

        # Check if new link ID already exists
        if new_link_id in links and new_link_id != link_id:
            return jsonify({'error': 'Link ID already exists'}), 400

        # If the new ID is the same as the old one, no changes needed
        if new_link_id == link_id:
            return jsonify({'success': True})

        # Move the link data to the new ID
        link_data = links[link_id]
        links[new_link_id] = link_data
        del links[link_id]

        save_links(links)

        return jsonify({'success': True})

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/delete/<link_id>', methods=['DELETE'])
def delete_link(link_id):
    """Delete a link and its associated GitHub release"""
    links = load_links()

    if link_id not in links:
        return jsonify({'error': 'Link not found'}), 404

    try:
        # Delete the GitHub release if it exists
        link_data = links[link_id]
        if 'file_info' in link_data and 'github_release_id' in link_data['file_info']:
            release_id = link_data['file_info']['github_release_id']
            try:
                delete_github_release(release_id)
            except Exception as e:
                print(f"Warning: Failed to delete GitHub release {release_id}: {str(e)}")

        # Remove from links database
        del links[link_id]
        save_links(links)

        return jsonify({'success': True})

    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)