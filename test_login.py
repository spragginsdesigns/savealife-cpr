"""
Test script to validate MyRC login flow.
Run this to verify the authentication is working before processing real bookings.
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()

def check_env_vars():
    """Check that required environment variables are set."""
    required = ['MYRC_EMAIL', 'MYRC_PASSWORD']
    missing = [var for var in required if not os.environ.get(var)]

    if missing:
        print("Missing required environment variables:")
        for var in missing:
            print(f"  - {var}")
        print("\nPlease update your .env file with these values.")
        return False
    return True

def test_login():
    """Test the MyRC login flow."""
    from cpr_bot import CprBot

    print("=" * 50)
    print("MyRC Login Test")
    print("=" * 50)

    if not check_env_vars():
        return False

    print(f"\nTesting login with: {os.environ.get('MYRC_EMAIL')}")
    print("-" * 50)

    bot = CprBot()

    try:
        success = bot.login()

        if success:
            print("\n" + "=" * 50)
            print("LOGIN SUCCESSFUL!")
            print("=" * 50)
            print(f"Secure config obtained: {bot.secure_config[:50]}...")
            return True
        else:
            print("\n" + "=" * 50)
            print("LOGIN FAILED!")
            print("=" * 50)
            return False

    except Exception as e:
        print(f"\nError during login: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_course_search():
    """Test searching for courses (requires successful login)."""
    from cpr_bot import CprBot

    print("\n" + "=" * 50)
    print("Course Search Test")
    print("=" * 50)

    bot = CprBot()

    # Set up a test search
    bot.parsed_webhook = {
        "course_date": "2025-11-30",  # Today's date
        "course_type": "Standard First Aid Blended",
        "course_location": "Cambridge"
    }

    try:
        if not bot.login():
            print("Login failed, cannot test course search")
            return False

        # Get verification token
        response = bot.session.get(f'{bot.MYRC_BASE_URL}/_layout/tokenhtml')
        import re
        token_match = re.search(r'value="([^"]+)"', response.text)

        if not token_match:
            print("Failed to get verification token")
            return False

        verif_token = token_match.group(1)
        print(f"Got verification token: {verif_token[:20]}...")

        # Try to search courses
        response = bot._search_courses(verif_token, 1)
        print(f"Course search response status: {response.status_code}")
        print(f"Response preview: {response.text[:200]}...")

        return response.status_code == 200

    except Exception as e:
        print(f"Error during course search: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("\nSaveALife CPR Bot - Connection Test")
    print("=" * 50)

    # Run tests
    login_ok = test_login()

    if login_ok and "--full" in sys.argv:
        test_course_search()

    print("\n" + "=" * 50)
    if login_ok:
        print("Basic connectivity test PASSED")
        print("You can now configure Bookeo webhook integration")
    else:
        print("Test FAILED - check your credentials")
    print("=" * 50)
