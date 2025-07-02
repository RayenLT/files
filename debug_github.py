
import os
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
GITHUB_OWNER = os.getenv('GITHUB_OWNER')
GITHUB_REPO = os.getenv('GITHUB_REPO')

print(f"GITHUB_OWNER: {GITHUB_OWNER}")
print(f"GITHUB_REPO: {GITHUB_REPO}")
print(f"GITHUB_TOKEN: {'Set' if GITHUB_TOKEN else 'Not set'}")

if not all([GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO]):
    print("ERROR: Missing GitHub configuration!")
    exit(1)

# Test 1: Check if repository exists
print("\n=== Testing Repository Access ===")
repo_url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}"
headers = {
    'Authorization': f'token {GITHUB_TOKEN}',
    'Accept': 'application/vnd.github.v3+json'
}

try:
    response = requests.get(repo_url, headers=headers)
    print(f"Repository check status: {response.status_code}")
    
    if response.status_code == 200:
        print("✅ Repository exists and is accessible")
        repo_data = response.json()
        print(f"Repository: {repo_data['full_name']}")
        print(f"Private: {repo_data['private']}")
    elif response.status_code == 404:
        print("❌ Repository not found")
        print("Create the repository first: https://github.com/new")
    else:
        print(f"❌ Error accessing repository: {response.status_code}")
        print(response.text[:500])

except Exception as e:
    print(f"❌ Error: {e}")

# Test 2: Check token permissions
print("\n=== Testing Token Permissions ===")
try:
    user_url = "https://api.github.com/user"
    response = requests.get(user_url, headers=headers)
    
    if response.status_code == 200:
        user_data = response.json()
        print(f"✅ Token is valid for user: {user_data['login']}")
    else:
        print(f"❌ Token validation failed: {response.status_code}")
        print(response.text[:500])

except Exception as e:
    print(f"❌ Error: {e}")

# Test 3: List existing releases
print("\n=== Testing Releases Access ===")
try:
    releases_url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases"
    response = requests.get(releases_url, headers=headers)
    
    if response.status_code == 200:
        releases = response.json()
        print(f"✅ Can access releases. Found {len(releases)} releases")
    else:
        print(f"❌ Cannot access releases: {response.status_code}")
        print(response.text[:500])

except Exception as e:
    print(f"❌ Error: {e}")
