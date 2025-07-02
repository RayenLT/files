
import os
import requests
from dotenv import load_dotenv

# Load environment variables from .env file (fallback)
load_dotenv()

# Get environment variables (Replit secrets take precedence)
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
GITHUB_OWNER = os.getenv('GITHUB_OWNER') 
GITHUB_REPO = os.getenv('GITHUB_REPO')

print("=== GitHub Configuration Check ===")
print(f"GITHUB_OWNER: {GITHUB_OWNER}")
print(f"GITHUB_REPO: {GITHUB_REPO}")
print(f"GITHUB_TOKEN: {'Set (' + str(len(GITHUB_TOKEN)) + ' chars)' if GITHUB_TOKEN else 'Not set'}")

if not all([GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO]):
    print("\n❌ ERROR: Missing GitHub configuration!")
    print("Required environment variables:")
    if not GITHUB_TOKEN: print("  - GITHUB_TOKEN")
    if not GITHUB_OWNER: print("  - GITHUB_OWNER")
    if not GITHUB_REPO: print("  - GITHUB_REPO")
    print("\nPlease set these in your .env file or environment")
    exit(1)

# Configure session
session = requests.Session()
session.headers.update({
    'Authorization': f'token {GITHUB_TOKEN}',
    'Accept': 'application/vnd.github.v3+json',
    'User-Agent': 'Replit-Debug/1.0'
})

def test_repository_access():
    print("\n=== Testing Repository Access ===")
    repo_url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}"
    
    try:
        response = session.get(repo_url, timeout=10)
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            repo_data = response.json()
            print("✅ Repository accessible")
            print(f"   Name: {repo_data['full_name']}")
            print(f"   Private: {repo_data['private']}")
            print(f"   Permissions: {repo_data.get('permissions', {})}")
            return True
        elif response.status_code == 404:
            print("❌ Repository not found")
            print("   Create repository at: https://github.com/new")
        elif response.status_code == 403:
            print("❌ Access forbidden - check token permissions")
        else:
            print(f"❌ Error: {response.status_code}")
            print(f"   Response: {response.text[:200]}")
        return False
    except requests.exceptions.RequestException as e:
        print(f"❌ Request failed: {e}")
        return False

def test_token_permissions():
    print("\n=== Testing Token Permissions ===")
    try:
        response = session.get("https://api.github.com/user", timeout=10)
        
        if response.status_code == 200:
            user_data = response.json()
            print(f"✅ Token valid for user: {user_data['login']}")
            
            # Check token scopes
            scopes = response.headers.get('X-OAuth-Scopes', '').split(', ')
            print(f"   Scopes: {', '.join(scopes) if scopes != [''] else 'None'}")
            return True
        else:
            print(f"❌ Token validation failed: {response.status_code}")
            print(f"   Response: {response.text[:200]}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"❌ Request failed: {e}")
        return False

def test_releases_access():
    print("\n=== Testing Releases Access ===")
    releases_url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases"
    
    try:
        response = session.get(releases_url, timeout=10)
        
        if response.status_code == 200:
            releases = response.json()
            print(f"✅ Releases accessible ({len(releases)} found)")
            if releases:
                latest = releases[0]
                print(f"   Latest: {latest['name']} ({latest['created_at']})")
            return True
        else:
            print(f"❌ Cannot access releases: {response.status_code}")
            print(f"   Response: {response.text[:200]}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"❌ Request failed: {e}")
        return False

def test_rate_limits():
    print("\n=== Checking Rate Limits ===")
    try:
        response = session.get("https://api.github.com/rate_limit", timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            core = data['resources']['core']
            print(f"✅ Rate limit: {core['used']}/{core['limit']}")
            print(f"   Resets at: {core['reset']}")
            
            if core['remaining'] < 100:
                print("⚠️  Warning: Low rate limit remaining")
            return True
        else:
            print(f"❌ Rate limit check failed: {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"❌ Request failed: {e}")
        return False

# Run all tests
def main():
    tests = [
        test_repository_access,
        test_token_permissions,
        test_releases_access,
        test_rate_limits
    ]
    
    results = []
    for test in tests:
        results.append(test())
    
    print("\n=== Summary ===")
    passed = sum(results)
    total = len(results)
    
    if passed == total:
        print(f"✅ All tests passed ({passed}/{total})")
        print("🚀 GitHub integration ready!")
    else:
        print(f"❌ {total - passed} test(s) failed ({passed}/{total} passed)")
        print("🔧 Please fix the issues above before proceeding")
    
    return passed == total

if __name__ == "__main__":
    main()
