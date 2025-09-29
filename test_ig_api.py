import requests
import json
from termcolor import colored

def test_instagram_api(sessionid, threadid=None):
    """Test different Instagram API endpoints to see what works"""
    
    print(colored("\n=== Instagram API Diagnostic Tool ===\n", "cyan"))
    
    # Test different header configurations
    header_configs = {
        "Mobile App Style": {
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.9",
            "user-agent": "Instagram 275.0.0.27.98 Android (33/13; 420dpi; 1080x2340; samsung; SM-G991B; o1s; exynos2100; en_US; 458229237)",
            "x-ig-app-id": "567067343352427",
        },
        "Web Browser Style": {
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.9",
            "referer": "https://www.instagram.com/",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "x-asbd-id": "129477",
            "x-csrftoken": sessionid[:32],  # Use part of session as csrf
            "x-ig-app-id": "936619743392459",
            "x-ig-www-claim": "0",
            "x-requested-with": "XMLHttpRequest",
        },
        "Minimal Headers": {
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }
    }
    
    cookies = {"sessionid": sessionid}
    
    # Test 1: Check if session is valid
    print(colored("TEST 1: Validating Session ID...", "yellow"))
    test_url = "https://www.instagram.com/api/v1/users/web_profile_info/?username=instagram"
    
    for name, headers in header_configs.items():
        try:
            r = requests.get(test_url, headers=headers, cookies=cookies, timeout=10)
            status = colored(f"✓ {r.status_code}", "green") if r.status_code == 200 else colored(f"✗ {r.status_code}", "red")
            print(f"  {name}: {status}")
            
            if r.status_code == 200:
                print(colored(f"    → This header config works for basic requests!", "green"))
                working_headers = headers
                break
        except Exception as e:
            print(f"  {name}: {colored(f'✗ Error: {str(e)}', 'red')}")
    else:
        print(colored("\n❌ All header configurations failed. Your session may be invalid.", "red"))
        print(colored("\nTroubleshooting steps:", "yellow"))
        print("1. Open Instagram in a browser (NOT incognito)")
        print("2. Make sure you're fully logged in")
        print("3. Open DevTools (F12) → Application → Cookies")
        print("4. Copy the ENTIRE sessionid value (should be 30-50 characters)")
        print("5. Also copy these cookies if available: csrftoken, ds_user_id")
        return
    
    print()
    
    # Test 2: Try to access inbox
    if threadid:
        print(colored("TEST 2: Checking Direct Message Access...", "yellow"))
        
        # Try different API endpoints
        endpoints = [
            f"https://i.instagram.com/api/v1/direct_v2/threads/{threadid}/",
            f"https://www.instagram.com/api/v1/direct_v2/threads/{threadid}/",
            f"https://i.instagram.com/api/v1/direct_v2/threads/{threadid}/?visual_message_return_type=unseen",
        ]
        
        for endpoint in endpoints:
            try:
                r = requests.get(endpoint, headers=working_headers, cookies=cookies, timeout=10)
                print(f"\n  Endpoint: {endpoint}")
                print(f"  Status: {r.status_code}")
                
                if r.status_code == 200:
                    print(colored("  ✓ SUCCESS! This endpoint works!", "green"))
                    data = r.json()
                    if "thread" in data:
                        thread = data["thread"]
                        print(colored(f"  → Thread found: {thread.get('thread_title', 'DM')}", "cyan"))
                        print(colored(f"  → Messages available: {len(thread.get('items', []))}", "cyan"))
                    print(f"\n  Working configuration found!")
                    print(f"  Endpoint: {endpoint}")
                    print(f"  Headers: {json.dumps(working_headers, indent=2)}")
                    return
                else:
                    print(colored(f"  ✗ Failed: {r.status_code}", "red"))
                    try:
                        error_data = r.json()
                        if "message" in error_data:
                            print(colored(f"  → Instagram says: {error_data['message']}", "yellow"))
                        print(f"  → Response preview: {str(error_data)[:200]}")
                    except:
                        print(f"  → Response preview: {r.text[:200]}")
                        
            except Exception as e:
                print(colored(f"  ✗ Error: {str(e)}", "red"))
        
        print(colored("\n❌ All DM endpoints failed.", "red"))
        print(colored("\nPossible issues:", "yellow"))
        print("1. Thread ID is incorrect")
        print("2. You don't have access to this thread")
        print("3. Instagram requires additional authentication (CSRF token, etc.)")
        print("4. Instagram has deprecated this API")
    
    # Test 3: Try inbox listing
    print(colored("\nTEST 3: Attempting to List Inbox...", "yellow"))
    inbox_endpoints = [
        "https://i.instagram.com/api/v1/direct_v2/inbox/?persistentBadging=true&folder=&limit=20",
        "https://www.instagram.com/api/v1/direct_v2/inbox/?persistentBadging=true&limit=20",
    ]
    
    for endpoint in inbox_endpoints:
        try:
            r = requests.get(endpoint, headers=working_headers, cookies=cookies, timeout=10)
            print(f"\n  Endpoint: {endpoint}")
            print(f"  Status: {r.status_code}")
            
            if r.status_code == 200:
                print(colored("  ✓ SUCCESS!", "green"))
                data = r.json()
                if "inbox" in data and "threads" in data["inbox"]:
                    threads = data["inbox"]["threads"]
                    print(colored(f"  → Found {len(threads)} conversations", "cyan"))
                    print(colored("\n  Your conversations:", "green"))
                    for i, thread in enumerate(threads[:20]):  # Show first 5
                        name = thread.get('thread_title') if thread.get('is_group') else thread.get('users', [{}])[0].get('full_name', 'Unknown')
                        tid = thread.get('thread_id')
                        print(f"    {i+1}. {name} [ID: {tid}]")
                    if len(threads) > 5:
                        print(f"    ... and {len(threads) - 5} more")
                return
            else:
                print(colored(f"  ✗ Failed: {r.status_code}", "red"))
                try:
                    error_data = r.json()
                    if "message" in error_data:
                        print(colored(f"  → {error_data['message']}", "yellow"))
                except:
                    print(f"  → Response: {r.text[:200]}")
                    
        except Exception as e:
            print(colored(f"  ✗ Error: {str(e)}", "red"))
    
    print(colored("\n\n=== DIAGNOSIS COMPLETE ===", "cyan"))
    print(colored("\nRecommendations:", "yellow"))
    print("1. Instagram may have changed their API authentication")
    print("2. Try using browser automation (Selenium) instead")
    print("3. Consider using unofficial Instagram API libraries like 'instagrapi'")
    print("4. Export your DMs manually from Instagram's data download feature")


if __name__ == "__main__":
    print(colored("Instagram API Diagnostic Tool", "cyan"))
    print()
    sessionid = input("Enter your sessionid: ").strip()
    
    test_with_thread = input("Do you have a thread ID to test? (y/N): ").lower()
    threadid = None
    if test_with_thread == 'y':
        threadid = input("Enter thread ID: ").strip()
    
    test_instagram_api(sessionid, threadid)