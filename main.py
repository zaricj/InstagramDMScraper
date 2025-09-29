import os
import sys
import threading
import time
import traceback
import json
from datetime import datetime
from turtle import color

import requests
from termcolor import colored
import argparse

# Working headers based on diagnostic test
headers = {
    "accept": "*/*",
    "accept-language": "en-US,en;q=0.9",
    "referer": "https://www.instagram.com/",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "x-asbd-id": "129477",
    "x-ig-app-id": "936619743392459",
    "x-ig-www-claim": "0",
    "x-requested-with": "XMLHttpRequest",
}

SESSIONID = None
THREADID = None
VERBOSE = False
FILE_PATH = None
PREV_CURSOR = ""
OLDEST_CURSOR = ""
USED_CURSORS: list = list()
LAST_RESPONSE = None
MESSAGES: list = list()
IS_WAITING = True
MEMBERS: dict = dict()
TOTAL_TIME = 0
RATE: list = [0]
LIMIT_DATE = None
REQUESTS_AMMOUNT = 0
STREAMED_MESSAGES: list = []
TO_STREAM: list = []
PARSER = argparse.ArgumentParser()
ARGS = None

# Creating args
PARSER.add_argument("-s", "--sessionid", dest="sessionid", type=str, help="Account's Sessionid")
PARSER.add_argument("-S", "--stream", dest="stream", action="store_true")
PARSER.add_argument("-t", "--threadid", dest="threadid", type=str, help="Chat's Threadid")  # Changed to str
PARSER.add_argument("-v", "--verbose", dest="verbose", action="store_true")
PARSER.add_argument("-o", "--output", dest="output", type=str, help="Output file")
PARSER.add_argument("-d", "--date", dest="date", type=str, help="Limit date")
PARSER.add_argument("-l", "--list", dest="list", action="store_true")

def force_exit():
    """Called when the program is abruptly terminated"""
    global IS_WAITING
    print(colored(f"\nProgram exit before time... Printing fetched messages... [{datetime.now().strftime('%d/%m/%Y @ %H:%M:%S')}]", "red"))
    IS_WAITING = False
    time.sleep(0.5)  # Give threads time to stop
    print_messages()
    sys.exit(1)


def rate_limit():
    global IS_WAITING
    IS_WAITING = False
    raise RuntimeError("You're being rate-limited (HTTP 429)")


def has_args():
    global ARGS
    return not (ARGS.date is None and ARGS.output is None and ARGS.sessionid is None 
                and ARGS.stream is False and ARGS.threadid is None and ARGS.verbose is False 
                and ARGS.list is False)


def parse_args():
    global SESSIONID, THREADID, VERBOSE, FILE_PATH, LIMIT_DATE
    
    if ARGS.sessionid is None:
        return (False, "No Sessionid was provided")
    SESSIONID = ARGS.sessionid
    
    if ARGS.list:
        return (True, "list")
    
    if ARGS.threadid is None:
        return (False, "No Threadid was provided")
    THREADID = str(ARGS.threadid)  # Ensure it's a string
    
    if ARGS.stream:
        return (True, "stream")

    VERBOSE = ARGS.verbose
    FILE_PATH = ARGS.output
    
    if ARGS.date is not None:
        if "@" in ARGS.date:
            LIMIT_DATE = datetime.strptime(ARGS.date, "%d/%m/%Y@%H:%M:%S")
        else:
            LIMIT_DATE = datetime.strptime(ARGS.date, "%d/%m/%Y")
    
    return (True, None)


def get_request(url: str, headers: dict, cookies: dict):
    """Make GET request with proper error handling"""
    try:
        r = requests.get(url, headers=headers, cookies=cookies, timeout=30)
        global REQUESTS_AMMOUNT
        REQUESTS_AMMOUNT += 1
        
        if VERBOSE:
            print(colored(f"[DEBUG] Request to: {url}", "cyan"))
            print(colored(f"[DEBUG] Status Code: {r.status_code}", "cyan"))
        
        if r.status_code == 429:
            rate_limit()
        elif r.status_code == 400:
            print(colored(f"\nError: HTTP 400 - Bad Request", "red"))
            print(colored("Possible causes:", "yellow"))
            print(colored("  1. Invalid Thread ID format", "yellow"))
            print(colored("  2. Session ID has incorrect format or expired", "yellow"))
            print(colored("  3. Instagram has updated their API requirements", "yellow"))
            if VERBOSE:
                print(colored(f"\nResponse: {r.text[:500]}", "cyan"))
            return None
        elif r.status_code == 401:
            print(colored(f"\nError: HTTP 401 - Unauthorized", "red"))
            print(colored("Your session ID is invalid or expired. Get a new one!", "yellow"))
            return None
        elif r.status_code != 200:
            print(colored(f"\nError: HTTP {r.status_code} - {r.reason}", "red"))
            if VERBOSE:
                print(colored(f"Response: {r.text[:500]}", "cyan"))
            return None
        
        res = r.json()
        global LAST_RESPONSE
        LAST_RESPONSE = res
        
        if VERBOSE:
            print(colored(f"[DEBUG] Response keys: {list(res.keys())}", "cyan"))
        
        return res
        
    except requests.exceptions.Timeout:
        print(colored("Error: Request timed out", "red"))
        return None
    except requests.exceptions.ConnectionError:
        print(colored("Error: Connection failed. Check your internet.", "red"))
        return None
    except json.JSONDecodeError:
        print(colored("Error: Invalid JSON response", "red"))
        if VERBOSE:
            print(colored(f"Response text: {r.text[:500]}", "cyan"))
        return None
    except Exception as e:
        print(colored(f"Error: {str(e)}", "red"))
        return None


def reverse_list(target_list):
    """Reverses the target list"""
    return list(reversed(target_list))


def get_messages(cursor: str = ""):
    """Request to get messages stored in that Cursor"""
    # Use www.instagram.com instead of i.instagram.com
    response = get_request(
        f"https://www.instagram.com/api/v1/direct_v2/threads/{THREADID}/?cursor={cursor}", 
        headers, 
        {"sessionid": SESSIONID}
    )
    
    if response is None:
        return []
    
    if "thread" not in response:
        print(colored("\nError: Invalid response - missing 'thread' key", "red"))
        if "message" in response:
            print(colored(f"Instagram says: {response['message']}", "yellow"))
        return []
    
    if "items" not in response["thread"]:
        return []
    
    return response["thread"]["items"]


def has_prev_cursor(cursor):
    """Check if there's a Cursor older than the given one"""
    return bool(LAST_RESPONSE.get("thread", {}).get("has_older", False))


def get_prev_cursor(cursor):
    """Get the most recent cursor older than the given one"""
    thread = LAST_RESPONSE.get("thread", {})
    return thread.get("prev_cursor") or thread.get("oldest_cursor")


def get_all_messages(thread):
    """Main loop to get all messages"""
    global MESSAGES, RATE, TOTAL_TIME
    
    current_cursor = thread.get('newest_cursor')
    passed_limit_date = False
    
    while True:
        start = round(time.time() * 1000)
        
        if current_cursor is None:
            break
        
        temp_messages = get_messages(current_cursor)
        if not temp_messages:
            break
            
        to_add: list = []
        
        for temp_message in temp_messages:
            if VERBOSE:
                print(colored(f"[*] Checking message with id {temp_message['item_id']}", 'yellow'))
            
            # Check limit date
            if LIMIT_DATE is not None:
                msg_timestamp = datetime.fromtimestamp(temp_message["timestamp"] / 1000000)
                if LIMIT_DATE > msg_timestamp:
                    passed_limit_date = True
                    if VERBOSE:
                        print(colored(f"[-] Reached limit date. Stopping...", "red"))
                    break
            
            # Check for duplicates
            if any(msg["item_id"] == temp_message["item_id"] for msg in MESSAGES):
                if VERBOSE:
                    print(colored(f"[-] Duplicate message, skipping...", "red"))
                continue
            
            to_add.append(temp_message)
            if VERBOSE:
                print(colored(f"[+] Valid message added", "green"))
        
        MESSAGES.extend(to_add)
        
        run_time = round(time.time() * 1000) - start
        rate = (1000 * len(to_add)) / run_time if run_time > 0 else RATE[-1]
        RATE.append(rate)
        TOTAL_TIME += run_time
        
        if has_prev_cursor(current_cursor) and not passed_limit_date:
            current_cursor = get_prev_cursor(current_cursor)
            time.sleep(1)  # Add delay to avoid rate limiting
        else:
            break


def start():
    """Main entry point for fetching messages"""
    global MEMBERS, MESSAGES, TOTAL_TIME
    
    print(colored("Connecting to Instagram...", "cyan"))
    # Use www.instagram.com instead of i.instagram.com
    resposta = get_request(
        f"https://www.instagram.com/api/v1/direct_v2/threads/{THREADID}/?cursor=", 
        headers, 
        {"sessionid": SESSIONID}
    )
    
    if resposta is None:
        print(colored("\nFailed to connect. Exiting...", "red"))
        return
    
    if "thread" not in resposta:
        print(colored("\nError: Unable to access thread", "red"))
        if "message" in resposta:
            print(colored(f"Instagram says: {resposta['message']}", "yellow"))
        return
    
    thread = resposta["thread"]
    
    # Get members
    for user in thread.get("users", []):
        MEMBERS[user["pk"]] = user["full_name"].split(" ")[0]
    
    # Get initial messages
    items = thread.get("items", [])
    MESSAGES = [items[0]] if items else []
    
    print(colored("Fetching messages...\n", "cyan"))
    get_all_messages(thread)
    print_messages()


def get_threads():
    """Get a list of all chats"""
    print(colored("Fetching your chats...", "cyan"))
    # Use www.instagram.com instead of i.instagram.com
    r = get_request(
        "https://www.instagram.com/api/v1/direct_v2/inbox/?persistentBadging=true&folder=&limit=200", 
        headers, 
        {"sessionid": SESSIONID}
    )
    
    if r is None:
        return
    
    if "inbox" not in r:
        print(colored("\nError: Could not fetch inbox", "red"))
        if "message" in r:
            print(colored(f"Instagram says: {r['message']}", "yellow"))
        return
    
    threads = r["inbox"]["threads"]
    threads_dict: dict = {}
    
    for thread in threads:
        thread_id = thread["thread_id"]
        
        if thread.get("is_group"):
            # For group chats, use the thread title
            name = thread.get('thread_title', "Unknown Group")
        else:
            # For 1-on-1 chats, safely get the first user's full name
            users = thread.get("users", [])
            # Check if the users list is not empty before indexing
            if users:
                # The user object in a deleted account thread will likely have 
                # '__deleted__' in the full_name, username, or just be missing data.
                name = users[0].get("full_name", "Unknown")
            else:
                name = "Unknown (No User Info)"
        
        # ----------------------------------------------------------------------
        # ADDED LOGIC TO FILTER OUT DELETED ACCOUNTS
        # ----------------------------------------------------------------------
        if "__deleted__" not in name:
            threads_dict[thread_id] = name
        else:
            print(colored(f"[INFO] Omitting deleted thread: {name} [{thread_id}]", "yellow"))
    
    # Print the available threads after successfully processing all of them
    print(colored("\n=== Available Threads ===", "green"))
    print(colored("\n|      Name         |       ID      |", "cyan"))
    for thread_id, name in threads_dict.items():
        print(f"{name} [{thread_id}]")
    print(colored(f"\nTotal: {len(threads_dict)} threads\n", "green"))
    

def print_messages(streaming: bool = False):
    """Print and export fetched messages"""
    global IS_WAITING
    
    if not streaming:
        IS_WAITING = False
        print("\n----------- Messages -----------")
        
        # 1. Prepare all output lines in memory
        output_lines = []
        
        for mensagem in reverse_list(MESSAGES):
            name = f"{MEMBERS.get(mensagem['user_id'], 'Unknown')}: " if mensagem.get("user_id") in MEMBERS else "You: "
            texto = format_message(mensagem)
            timestamp = datetime.fromtimestamp(float(mensagem["timestamp"]) / 1000000)
            
            output = f"{name}{texto} [{timestamp.strftime('%d/%m/%Y @ %H:%M:%S')}]"
            
            # Add to list for bulk writing
            output_lines.append(output)
            
            # Print to console
            if FILE_PATH is None or VERBOSE:
                print(f"{colored(name, 'yellow')}{texto} [{timestamp.strftime('%d/%m/%Y @ %H:%M:%S')}]")

        # 2. Write all messages to file in a single operation
        if FILE_PATH is not None:
            # Use 'w' mode here to overwrite the file with the complete, final list
            # Note: This relies on the file being cleaned up (or not) before start()
            with open(FILE_PATH, 'w', encoding="UTF-8") as f:
                f.write("\n".join(output_lines) + "\n")
            print(colored(f"Writing to file completed, file located at {FILE_PATH}", "green"))


def format_message(msg):
    """Format message based on type"""
    item_type = msg.get('item_type', '')
    
    if item_type == 'text':
        return msg.get('text', '')
    
    elif item_type == 'media':
        media_type = msg.get('media', {}).get('media_type')
        if media_type == 1:
            url = msg['media']['image_versions2']['candidates'][0]['url']
            return f"Photo: {url}"
        elif media_type == 2:
            url = msg['media']['video_versions'][0]['url']
            return f"Video: {url}"
    
    elif item_type == 'media_share':
        try:
            user = msg['media_share']['user']['username']
            name = msg['media_share']['user']['full_name']
            code = msg['media_share']['code']
            return f"Post share from {user} (A.K.A {name}): https://instagram.com/p/{code}/"
        except KeyError:
            return "Post share: Unable to get post"
    
    elif item_type == 'voice_media':
        url = msg['voice_media']['media']['audio']['audio_src']
        return f"Voice message: {url}"
    
    elif item_type == 'raven_media':
        media_type = msg.get('visual_media', {}).get('media', {}).get('media_type')
        if media_type == 1:
            try:
                url = msg['visual_media']['media']['image_versions2']['candidates'][0]['url']
                return f"Temporary photo: {url} (May be expired)"
            except KeyError:
                return "Temporary photo: Unable to fetch (Expired)"
        elif media_type == 2:
            try:
                url = msg['visual_media']['media']['video_versions'][0]['url']
                return f"Temporary video: {url} (May be expired)"
            except KeyError:
                return "Temporary video: Unable to fetch (Expired)"
    
    return item_type


def waiting():
    """Thread to show fetching progress"""
    try:
        while IS_WAITING:
            if not VERBOSE:
                hours = int(((TOTAL_TIME / 1000) / 3600) % 24)
                minutes = int(((TOTAL_TIME / 1000) / 60) % 60)
                seconds = int((TOTAL_TIME / 1000) % 60)
                dots = '.' * ((int(TOTAL_TIME / 1000) % 3) + 1)
                spaces = ' ' * (4 - len(dots))
                rate = RATE[-1] if RATE else 0
                print(f"Fetching messages{dots}{spaces}({hours}h{minutes}m{seconds}s) ({len(MESSAGES)} messages in {REQUESTS_AMMOUNT} requests) (Rate: {rate:.2f} msg/s)", end="\r")
            time.sleep(1)
    except KeyboardInterrupt:
        pass


def compute_average_rate():
    return sum(RATE) / len(RATE) if RATE else 0


def main():
    global THREADID, SESSIONID, ARGS, VERBOSE, LIMIT_DATE
    
    ARGS = PARSER.parse_args()
    
    try:
        if has_args():
            success, message = parse_args()
            if not success:
                print(colored(f"Error: {message}", "red"))
                return
            
            if message == "list":
                get_threads()
            elif message == "stream":
                print(colored("Stream mode not fully implemented in this version", "yellow"))
            else:
                if VERBOSE:
                    print("Starting in verbose mode...")
                
                waiting_thread = threading.Thread(target=waiting, daemon=True)
                waiting_thread.start()
                
                start()
        else:
            # Interactive mode
            print(colored("=== Instagram DM Scraper ===\n", "cyan"))
            SESSIONID = input("Your account's Sessionid: ")
            
            check_threads = input("See chats list (y/N): ").lower()
            if check_threads == "y":
                get_threads()
            
            THREADID = input("Chat's Threadid: ")
            
            enable_verbose = input("Verbose (y/N): ").lower()
            VERBOSE = (enable_verbose == "y")
            
            enable_export = input("Export to file (y/N): ").lower()
            if enable_export == "y":
                FILE_PATH = input("File path + name: ")
                if os.path.isfile(FILE_PATH):
                    print(colored("Entered path is a file, continuing", "green"))
                elif not os.path.exists(FILE_PATH):
                    print(colored("Could not find the entered file path...", "yellow"))
                    create_file = input("Entered file does not exist, create it (y/N)? ")
                    if create_file == "y":
                        with open(FILE_PATH, "w") as file:
                            file.write("")
                    else:
                        print(colored("Saving to file omitted.", "red"))
            
            temp_limit_date = input("Limit date (dd/mm/yyyy[@hh:mm:ss]): ")
            if temp_limit_date:
                if "@" in temp_limit_date:
                    LIMIT_DATE = datetime.strptime(temp_limit_date, "%d/%m/%Y@%H:%M:%S")
                else:
                    LIMIT_DATE = datetime.strptime(temp_limit_date, "%d/%m/%Y")
            
            waiting_thread = threading.Thread(target=waiting, daemon=True)
            waiting_thread.start()
            start()
        
        # Print summary
        if not ARGS.list and not ARGS.stream:
            hours = int(((TOTAL_TIME / 1000) / 3600) % 24)
            minutes = int(((TOTAL_TIME / 1000) / 60) % 60)
            seconds = int((TOTAL_TIME / 1000) % 60)
            avg_rate = compute_average_rate()
            
            print(colored("\n✓ Fetching complete!", "green"))
            print(colored(f"Total messages: {len(MESSAGES)}", "cyan"))
            print(colored(f"Time elapsed: {hours}h {minutes}m {seconds}s", "cyan"))
            print(colored(f"API requests: {REQUESTS_AMMOUNT}", "cyan"))
            print(colored(f"Average rate: {avg_rate:.2f} messages/second", "cyan"))
    
    except KeyboardInterrupt:
        force_exit()
    except Exception as e:
        print(colored(f"\nUnexpected error: {str(e)}", "red"))
        if VERBOSE:
            traceback.print_exc()
        force_exit()


if __name__ == '__main__':
    main()