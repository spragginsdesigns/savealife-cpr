"""
Dry Run Test - Simulates full registration flow without actually registering.

Usage:
    python test_dry_run.py                    # Use default test data
    python test_dry_run.py --real             # Actually register (remove dry run)
"""

import sys
import os
from dotenv import load_dotenv

load_dotenv()

from cpr_bot import CprBot

# Test booking data - modify as needed
TEST_BOOKING = {
    "itemId": "TEST-DRY-RUN-001",
    "item": {
        "bookingNumber": "DRY-RUN-TEST",
        "productName": "Cambridge: Standard First Aid Blended",  # Location: Course Type
        "startTime": "2025-12-31T09:00:00",  # Course date
        "endTime": "2025-12-31T17:00:00",
        "options": [
            {
                "name": "Certification Level",
                "value": "Standard First Aid - Level C"
            }
        ],
        "participants": {
            "details": [
                {
                    "personDetails": {
                        "firstName": "Test",
                        "lastName": "Participant",
                        "emailAddress": "test@savealifecpr.ca",
                        "phoneNumbers": [{"number": "519-555-1234"}],
                        "streetAddress": {
                            "address1": "123 Test Street",
                            "address2": "",
                            "city": "Cambridge",
                            "state": "Ontario",
                            "postcode": "N1R 5S2"
                        }
                    }
                }
            ]
        }
    }
}


def main():
    # Check for --real flag to disable dry run
    dry_run = "--real" not in sys.argv

    print("=" * 70)
    print("SaveALife CPR Bot - Registration Test")
    print("=" * 70)
    print(f"Mode: {'DRY RUN (no actual registration)' if dry_run else '🔴 REAL REGISTRATION'}")
    print("")
    print("Test Booking Details:")
    print(f"  Course: {TEST_BOOKING['item']['productName']}")
    print(f"  Date: {TEST_BOOKING['item']['startTime'].split('T')[0]}")
    print(f"  Participant: {TEST_BOOKING['item']['participants']['details'][0]['personDetails']['firstName']} "
          f"{TEST_BOOKING['item']['participants']['details'][0]['personDetails']['lastName']}")
    print(f"  Email: {TEST_BOOKING['item']['participants']['details'][0]['personDetails']['emailAddress']}")
    print("=" * 70)
    print("")

    if not dry_run:
        confirm = input("⚠️  This will CREATE A REAL REGISTRATION. Type 'yes' to continue: ")
        if confirm.lower() != 'yes':
            print("Aborted.")
            return

    # Create bot with dry_run flag
    bot = CprBot(dry_run=dry_run)

    # Run the registration
    result = bot.run(TEST_BOOKING)

    print("")
    print("=" * 70)
    print(f"Final Result: {result}")
    print("=" * 70)


if __name__ == "__main__":
    main()
