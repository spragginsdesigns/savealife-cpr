"""
CPR Course Registration Bot for Canadian Red Cross MyRC Portal
Version: 2.0.0

This bot automates the registration of CPR course participants from Bookeo
into the Canadian Red Cross MyRC system.
"""

import requests
import pickle
import re
import json
import os
import smtplib
import base64
from typing import Optional, Dict, Any, List
from pathlib import Path

# Load .env for local development (ignored in Lambda)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class CprBot:
    """Handles automated registration of CPR course participants."""

    # Azure B2C Configuration - Updated November 2025
    B2C_TENANT = "crcsb2c.onmicrosoft.com"
    B2C_POLICY = "B2C_1A_MYRC_SIGNUP_SIGNIN"  # Case-sensitive policy name
    B2C_CLIENT_ID = "e0ef264d-2d7a-4182-8e8b-dea60e9a408a"

    # MyRC Portal URLs
    MYRC_BASE_URL = "https://myrc.redcross.ca"
    MYRC_SIGNIN_URL = f"{MYRC_BASE_URL}/en/SignIn"

    def __init__(self, dry_run: bool = False):
        """
        Initialize the CPR Bot.

        Args:
            dry_run: If True, performs all steps except final registration.
                     Useful for testing the flow without creating real registrations.
        """
        self.dry_run = dry_run
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self.secure_config = ""
        self.job_ids = ""
        self.parsed_webhook = {}
        self.output_myrc_id = "N/A"
        self.course_type = ""
        self.cookies_path = Path("/tmp/cookies.pkl")

        if self.dry_run:
            print("=" * 60)
            print("🔍 DRY RUN MODE - No actual registrations will be made")
            print("=" * 60)

    def send_email(self, subject: str, bookeo_response: List[str], booking_number: str) -> None:
        """Send email notification about registration status."""
        recipients = json.loads(os.environ.get('EMAIL_RECIPIENTS', '[]'))
        if not recipients:
            print("Warning: No email recipients configured")
            return

        email_text = f"""\
From: {os.environ.get('EMAIL_USER')}
To: {", ".join(recipients)}
Subject: {subject}

Status Codes: {str(bookeo_response)}
Booking Number: {booking_number}
Myrc Course Number: {str(self.output_myrc_id)}
Course Type: {self.course_type}

*The status codes indicate the problems (or successes) each participant
in this booking had when being entered. They are in the same order as
the participants in bookeo.
"""
        try:
            server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
            server.ehlo()
            server.login(os.environ['EMAIL_USER'], os.environ['EMAIL_PASSWORD'])
            server.sendmail(os.environ['EMAIL_USER'], recipients, email_text)
            server.close()
            print(f"Email sent successfully: {subject}")
        except Exception as e:
            print(f"Failed to send email: {e}")

    def bookeo_put(self, response_code: str, event: Dict[str, Any]) -> requests.Response:
        """Update Bookeo with registration status."""
        print(f"Updating Bookeo with response: {response_code}")

        headers = {'Content-Type': 'application/json'}
        params = {
            'secretKey': os.environ.get('BOOKEO_SECRET_KEY'),
            'mode': 'backend',
            'apiKey': os.environ.get('BOOKEO_API_KEY'),
        }

        event['item']['externalRef'] = f"{response_code}, myrc: {self.output_myrc_id}"

        # Remove fields that shouldn't be in PUT request
        for field in ['startTime', 'endTime', 'customer']:
            event['item'].pop(field, None)
        if 'participants' in event['item']:
            event['item']['participants'].pop('details', None)

        return self.session.put(
            f'https://api.bookeo.com/v2/bookings/{event["itemId"]}',
            params=params,
            data=json.dumps(event['item']),
            headers=headers
        )

    def _get_signin_page(self) -> requests.Response:
        """Get the initial sign-in page to start OAuth flow."""
        params = {'returnUrl': '/en/'}
        return self.session.get(self.MYRC_SIGNIN_URL, params=params, allow_redirects=True)

    def _extract_b2c_settings(self, html: str) -> Dict[str, str]:
        """Extract Azure B2C settings from login page HTML."""
        settings = {}

        # Extract CSRF token
        csrf_match = re.search(r'"csrf"\s*:\s*"([^"]+)"', html)
        if csrf_match:
            settings['csrf'] = csrf_match.group(1)

        # Extract transaction ID (StateProperties)
        trans_match = re.search(r'"transId"\s*:\s*"StateProperties=([^"]+)"', html)
        if trans_match:
            settings['state_properties'] = trans_match.group(1)

        # Extract API endpoint
        api_match = re.search(r'"api"\s*:\s*"([^"]+)"', html)
        if api_match:
            settings['api'] = api_match.group(1)

        return settings

    def _submit_credentials(self, state_properties: str, csrf: str) -> requests.Response:
        """Submit login credentials to Azure B2C."""
        headers = {
            'X-CSRF-TOKEN': csrf,
            'Content-Type': 'application/x-www-form-urlencoded',
        }
        params = {
            'tx': f'StateProperties={state_properties}',
            'p': self.B2C_POLICY,
        }
        data = {
            'request_type': 'RESPONSE',
            'signInName': os.environ.get('MYRC_EMAIL'),  # Changed from logonIdentifier
            'password': os.environ.get('MYRC_PASSWORD')
        }

        url = f'https://crcsb2c.b2clogin.com/{self.B2C_TENANT}/{self.B2C_POLICY}/SelfAsserted'
        return self.session.post(url, headers=headers, params=params, data=data)

    def _confirm_signin(self, state_properties: str, csrf: str) -> requests.Response:
        """Confirm sign-in and get tokens."""
        params = {
            'csrf_token': csrf,
            'tx': f'StateProperties={state_properties}',
            'p': self.B2C_POLICY,
        }
        url = f'https://crcsb2c.b2clogin.com/{self.B2C_TENANT}/{self.B2C_POLICY}/api/CombinedSigninAndSignup/confirmed'
        return self.session.get(url, params=params)

    def _complete_signin(self, state: str, id_token: str) -> requests.Response:
        """Complete sign-in by posting tokens back to MyRC."""
        data = {
            'state': state,
            'id_token': id_token
        }
        return self.session.post(self.MYRC_BASE_URL + '/', data=data)

    def _search_courses(self, verif_token: str, page: int = 1) -> requests.Response:
        """Search for courses matching the booking."""
        headers = {
            'Content-Type': 'application/json; charset=UTF-8',
            'X-Requested-With': 'XMLHttpRequest',
            '__RequestVerificationToken': verif_token,
        }
        data = json.dumps({
            "base64SecureConfiguration": self.secure_config,
            "sortExpression": "crc_startdate ASC",
            "search": self.parsed_webhook["course_date"],
            "page": page,
            "pageSize": 10,
            "pagingCookie": "",
            "filter": "account",
            "metaFilter": None,
            "nlSearchFilter": "",
            "timezoneOffset": 480,  # EST offset in minutes
            "customParameters": []
        })

        # Entity grid endpoint for course search
        url = f'{self.MYRC_BASE_URL}/_services/entity-grid-data.json/6d6b3012-e709-4c45-a00d-df4b3befc518'
        return self.session.post(url, headers=headers, data=data)

    def _search_contact_api(self, verif_token: str) -> Optional[Dict[str, Any]]:
        """
        Search for existing contact using new OData API (Updated Nov 2025).

        Returns:
            Contact data dict if found, None if not found
        """
        headers = {
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest',
            '__RequestVerificationToken': verif_token,
        }

        # OData query to search contacts by last name and email
        params = {
            '$select': 'contactid,fullname,birthdate,adx_identity_username,address1_line1,address1_line2,address1_city,address1_stateorprovince,address1_postalcode',
            '$filter': f"(lastname eq '{self.parsed_webhook['last_name']}' and emailaddress1 eq '{self.parsed_webhook['email']}' and statecode eq 0)"
        }

        response = self.session.get(
            f'{self.MYRC_BASE_URL}/_api/contacts',
            headers=headers,
            params=params
        )
        response.raise_for_status()

        data = response.json()
        contacts = data.get('value', [])

        if contacts:
            return contacts[0]  # Return first matching contact
        return None

    def _create_contact_api(self, verif_token: str) -> Optional[str]:
        """
        Create a new contact using OData API (Updated Nov 2025).

        Returns:
            Contact ID if successful, None otherwise
        """
        headers = {
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest',
            '__RequestVerificationToken': verif_token,
        }

        # Build contact data
        contact_data = {
            'firstname': self.parsed_webhook['first_name'],
            'lastname': self.parsed_webhook['last_name'],
            'emailaddress1': self.parsed_webhook['email'],
            'address1_line1': self.parsed_webhook['line1'],
            'address1_line2': self.parsed_webhook['line2'],
            'address1_city': self.parsed_webhook['city'],
            'address1_stateorprovince': self.parsed_webhook['province'],
            'address1_postalcode': self.parsed_webhook['postal_code'],
            'telephone1': self.parsed_webhook['phone'],
        }

        # Remove empty values
        contact_data = {k: v for k, v in contact_data.items() if v}

        response = self.session.post(
            f'{self.MYRC_BASE_URL}/_api/contacts',
            headers=headers,
            json=contact_data
        )

        if response.status_code in (200, 201, 204):
            # Contact ID is returned in the entityid header
            contact_id = response.headers.get('entityid')
            return contact_id

        print(f"Failed to create contact: {response.status_code} - {response.text}")
        return None

    def _add_participant_api(self, verif_token: str, contact_id: str) -> bool:
        """
        Add participant to course session using OData API (Updated Nov 2025).

        Args:
            verif_token: Request verification token
            contact_id: The contact's GUID

        Returns:
            True if successful, False otherwise
        """
        headers = {
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest',
            '__RequestVerificationToken': verif_token,
        }

        # Build participant data using OData binding syntax
        participant_data = {
            'crc_attendee@odata.bind': f'/contacts({contact_id})',
            'crc_coursesession@odata.bind': f'/crc_coursesessions({self.job_ids["ref_id"]})',
            'crc_participanttype': '0',  # 0 = Participant
            'crc_status': '171120001',  # Status code
        }

        # Add CPR level if specified
        if self.parsed_webhook.get('cpr_level'):
            participant_data['crc_cprlevel'] = self.parsed_webhook['cpr_level']

        response = self.session.post(
            f'{self.MYRC_BASE_URL}/_api/crc_courseparticipants',
            headers=headers,
            json=participant_data
        )

        if response.status_code in (200, 201, 204):
            return True

        # Check for "already registered" error
        if 'already registered' in response.text.lower():
            print(f"Participant already registered in this course")
            return True  # Consider this a success

        print(f"Failed to add participant: {response.status_code} - {response.text}")
        return False

    def parse_and_find_ids(self, json_response_arr: str) -> Optional[Dict[str, str]]:
        """Parse course search results and find matching course."""
        self.output_myrc_id = "N/A"

        try:
            jsonified = json.loads(json_response_arr)
        except json.JSONDecodeError as e:
            print(f"Failed to parse course search results: {e}")
            return None

        matched_ids = []

        for container in jsonified:
            for record in container.get("Records", []):
                matched_type = False
                matched_location = False
                course_id = "0"
                ref_id = record.get("Id", "")

                for attribute in record.get("Attributes", []):
                    attr_name = attribute.get("Name", "")
                    attr_value = attribute.get("Value", {})

                    if attr_name == "crc_coursetype":
                        if isinstance(attr_value, dict) and attr_value.get("Name") == self.parsed_webhook["course_type"]:
                            matched_type = True
                    elif attr_name == "crc_facility":
                        if isinstance(attr_value, dict) and attr_value.get("Name") == self.parsed_webhook["course_location"]:
                            matched_location = True
                    elif attr_name == "crc_name":
                        course_id = attr_value

                if matched_type and matched_location:
                    matched_ids.append({"course_id": course_id, "ref_id": ref_id})

        if len(matched_ids) == 1:
            self.output_myrc_id = matched_ids[0]["course_id"]
            return matched_ids[0]
        if len(matched_ids) == 0:
            return None
        return "multiple"

    def _load_cookies(self) -> bool:
        """Load saved session cookies if available."""
        if self.cookies_path.exists():
            try:
                with open(self.cookies_path, 'rb') as f:
                    self.session.cookies.update(pickle.load(f))
                return True
            except Exception as e:
                print(f"Failed to load cookies: {e}")
        return False

    def _save_cookies(self) -> None:
        """Save session cookies for reuse."""
        try:
            with open(self.cookies_path, 'wb') as f:
                pickle.dump(self.session.cookies, f)
        except Exception as e:
            print(f"Failed to save cookies: {e}")

    def login(self) -> bool:
        """Perform full two-step login flow to MyRC portal (Updated Nov 2025)."""
        import time
        print("Starting login flow...")

        # Step 1: Get sign-in page (follows redirect to B2C)
        response = self._get_signin_page()
        response.raise_for_status()

        # Extract B2C settings from the login page
        settings = self._extract_b2c_settings(response.text)

        if 'csrf' not in settings or 'state_properties' not in settings:
            state_match = re.search(r'StateProperties=([^"&\s]+)', response.text)
            csrf_match = re.search(r'"csrf"\s*:\s*"([^"]+)"', response.text)
            if state_match:
                settings['state_properties'] = state_match.group(1)
            if csrf_match:
                settings['csrf'] = csrf_match.group(1)

        if 'csrf' not in settings or 'state_properties' not in settings:
            print("Failed to extract B2C settings from login page")
            return False

        csrf = settings['csrf']
        state_properties = settings['state_properties']
        print("Extracted CSRF and StateProperties")

        # Step 2: Submit email + password (first step of two-step flow)
        headers = {
            'X-CSRF-TOKEN': csrf,
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'X-Requested-With': 'XMLHttpRequest',
        }
        params = {
            'tx': f'StateProperties={state_properties}',
            'p': self.B2C_POLICY,
        }
        data = {
            'request_type': 'RESPONSE',
            'signInName': os.environ.get('MYRC_EMAIL'),
            'password': os.environ.get('MYRC_PASSWORD'),
        }
        url = f'https://crcsb2c.b2clogin.com/{self.B2C_TENANT}/{self.B2C_POLICY}/SelfAsserted'
        response = self.session.post(url, headers=headers, params=params, data=data)
        response.raise_for_status()
        print(f"First credential submit: {response.text}")

        # Step 3: Get confirmation page (this triggers the second password prompt)
        params = {
            'rememberMe': 'false',
            'csrf_token': csrf,
            'tx': f'StateProperties={state_properties}',
            'p': self.B2C_POLICY,
        }
        url = f'https://crcsb2c.b2clogin.com/{self.B2C_TENANT}/{self.B2C_POLICY}/api/CombinedSigninAndSignup/confirmed'
        response = self.session.get(url, params=params)

        # Extract new CSRF and state for step 2
        new_csrf = re.search(r'"csrf"\s*:\s*"([^"]+)"', response.text)
        new_trans = re.search(r'"transId"\s*:\s*"StateProperties=([^"]+)"', response.text)
        if new_csrf and new_trans:
            csrf = new_csrf.group(1)
            state_properties = new_trans.group(1)
            print("Got new CSRF for step 2")

        # Step 4: Submit password again (second step of two-step flow)
        headers = {
            'X-CSRF-TOKEN': csrf,
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'X-Requested-With': 'XMLHttpRequest',
        }
        params = {
            'tx': f'StateProperties={state_properties}',
            'p': self.B2C_POLICY,
        }
        data = {
            'request_type': 'RESPONSE',
            'password': os.environ.get('MYRC_PASSWORD'),
        }
        url = f'https://crcsb2c.b2clogin.com/{self.B2C_TENANT}/{self.B2C_POLICY}/SelfAsserted'
        response = self.session.post(url, headers=headers, params=params, data=data)
        response.raise_for_status()
        print(f"Second password submit: {response.text}")

        time.sleep(0.3)  # Brief delay for B2C to process

        # Step 5: Get final confirmation with tokens
        params = {
            'rememberMe': 'false',
            'csrf_token': csrf,
            'tx': f'StateProperties={state_properties}',
            'p': self.B2C_POLICY,
        }
        url = f'https://crcsb2c.b2clogin.com/{self.B2C_TENANT}/{self.B2C_POLICY}/api/CombinedSigninAndSignup/confirmed'
        response = self.session.get(url, params=params, allow_redirects=True)

        # Extract state and id_token
        state_match = re.search(r"name=['\"]state['\"][^>]*value=['\"]([^'\"]+)['\"]", response.text)
        token_match = re.search(r"name=['\"]id_token['\"][^>]*value=['\"]([^'\"]+)['\"]", response.text)
        if not state_match:
            state_match = re.search(r"id=['\"]state['\"] value=['\"]([^'\"]+)['\"]", response.text)
        if not token_match:
            token_match = re.search(r"id=['\"]id_token['\"] value=['\"]([^'\"]+)['\"]", response.text)

        if not state_match or not token_match:
            print("Failed to extract state/token from confirmation response")
            return False

        state = state_match.group(1)
        id_token = token_match.group(1)
        print("Extracted state and id_token")

        # Step 6: Complete sign-in to MyRC
        response = self._complete_signin(state, id_token)
        response.raise_for_status()
        print(f"Logged into MyRC: {response.url}")

        # Step 7: Get SecureConfiguration from CourseManagement page
        response = self.session.get(f'{self.MYRC_BASE_URL}/en/CourseManagement/')

        # Extract data-view-layouts attribute (base64 encoded JSON)
        # Try both single and double quote patterns
        layouts_match = re.search(r"data-view-layouts=['\"]([^'\"]+)['\"]", response.text)
        if not layouts_match:
            print("Failed to find data-view-layouts attribute in CourseManagement page")
            return False

        try:
            # Decode the base64 outer layer
            layouts_b64 = layouts_match.group(1)
            layouts_json = base64.b64decode(layouts_b64).decode('utf-8')
            layouts = json.loads(layouts_json)

            # Get Base64SecureConfiguration from the first layout
            if layouts and 'Base64SecureConfiguration' in layouts[0]:
                self.secure_config = layouts[0]['Base64SecureConfiguration']
                print(f"Login successful! Got SecureConfiguration (length: {len(self.secure_config)})")
                self._save_cookies()
                return True
            else:
                print("No Base64SecureConfiguration found in layouts")
                return False
        except Exception as e:
            print(f"Failed to parse data-view-layouts: {e}")
            return False

    def register_participant(self) -> str:
        """
        Main registration flow for a single participant.
        Updated Nov 2025 to use new OData REST API instead of ASP.NET forms.
        """
        # Clear any stale cookies and start fresh
        # Old cookies can interfere with the B2C login flow
        self.session.cookies.clear()

        # Always perform fresh login for reliability
        if not self.login():
            return "Login Failed"

        if self.dry_run:
            print("✅ Step 1/5: Login successful")

        # Get verification token
        response = self.session.get(f'{self.MYRC_BASE_URL}/_layout/tokenhtml')
        token_match = re.search(r'value="([^"]+)"', response.text)
        if not token_match:
            return "Failed to get verification token"
        verif_token = token_match.group(1)

        if self.dry_run:
            print(f"✅ Step 2/5: Got verification token: {verif_token[:20]}...")

        # Search for the course
        response = self._search_courses(verif_token, 1)
        json_response_arr = "[" + response.text

        page_match = re.search(r'"PageCount":(\d+)', response.text)
        num_pages = int(page_match.group(1)) if page_match else 1

        for page in range(2, num_pages + 1):
            response = self._search_courses(verif_token, page)
            json_response_arr += "," + response.text
        json_response_arr += "]"

        response.raise_for_status()

        # Find matching course
        self.job_ids = self.parse_and_find_ids(json_response_arr)
        if self.job_ids is None:
            if self.dry_run:
                print("❌ Step 3/5: No matching courses found")
                print(f"   Searched for: {self.parsed_webhook.get('course_date')} | {self.parsed_webhook.get('course_location')} | {self.parsed_webhook.get('course_type')}")
            return "No Courses Found"
        if self.job_ids == "multiple":
            if self.dry_run:
                print("⚠️ Step 3/5: Multiple matching courses found - manual review needed")
            return "Multiple Courses Found"

        if self.dry_run:
            print(f"✅ Step 3/5: Found matching course")
            print(f"   MyRC Course ID: {self.output_myrc_id}")
            print(f"   Reference ID: {self.job_ids.get('ref_id', 'N/A')}")

        # Search for existing contact using new OData API
        contact = self._search_contact_api(verif_token)
        contact_id = None

        if contact:
            contact_id = contact.get('contactid')
            if self.dry_run:
                print(f"✅ Step 4/5: Found existing contact")
                print(f"   Contact ID: {contact_id}")
                print(f"   Name: {contact.get('fullname', 'N/A')}")
        else:
            if self.dry_run:
                print(f"✅ Step 4/5: No existing contact found")
                print(f"   Would create: {self.parsed_webhook.get('first_name')} {self.parsed_webhook.get('last_name')}")
                print(f"   Email: {self.parsed_webhook.get('email')}")

            # In dry run, don't actually create the contact
            if self.dry_run:
                print("=" * 60)
                print("🔍 DRY RUN COMPLETE - All steps passed!")
                print("=" * 60)
                print("   ✅ Login: Success")
                print(f"   ✅ Course Found: {self.output_myrc_id}")
                print("   ✅ Contact: Would create new")
                print("   ⏸️ Registration: SKIPPED (dry run)")
                print("")
                print("To perform actual registration, run without dry_run=True")
                return "Dry Run Success"

            # Create new contact
            contact_id = self._create_contact_api(verif_token)
            if not contact_id:
                return "Failed to Create Contact"
            print(f"Created new contact: {contact_id}")

        # In dry run with existing contact, stop here
        if self.dry_run:
            print("=" * 60)
            print("🔍 DRY RUN COMPLETE - All steps passed!")
            print("=" * 60)
            print("   ✅ Login: Success")
            print(f"   ✅ Course Found: {self.output_myrc_id}")
            print(f"   ✅ Contact: Exists ({contact_id})")
            print("   ⏸️ Registration: SKIPPED (dry run)")
            print("")
            print("To perform actual registration, run without dry_run=True")
            return "Dry Run Success"

        # Add participant to course session
        success = self._add_participant_api(verif_token, contact_id)
        if success:
            print(f"Successfully registered participant to course {self.output_myrc_id}")
            return "Success"
        else:
            return "Failed to Add Participant"

    def run(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Process a Bookeo webhook event."""
        print(f"Processing event: {event.get('itemId', 'unknown')}")

        cpr_level = "171120000"  # Default to Level A
        bookeo_response = []
        self.course_type = ""

        # Parse course options
        if 'options' in event.get('item', {}):
            for option in event['item']['options']:
                if "Certification" in option.get('name', ''):
                    value = option.get('value', '')

                    # Determine CPR level
                    if "evel A" in value:
                        cpr_level = "171120000"
                    elif "evel C" in value:
                        cpr_level = "171120001"

                    # Determine course type
                    if "Standard First Aid" in value:
                        self.course_type = "Standard First Aid Blended"
                    elif "Emergency First Aid" in value:
                        self.course_type = "Emergency First Aid Blended"
                    elif "AED" in value:
                        self.course_type = "CPR/AED Blended"
                    elif "Oxygen Therapy" in value:
                        self.course_type = "Basic Life Support with Airway Management and Oxygen Therapy"

        # Parse course name for additional type info
        try:
            product_name = event['item']['productName']
            course_name = product_name.split(": ", 1)[1] if ": " in product_name else product_name
            self.course_type = course_name_parser(course_name, self.course_type)
        except (KeyError, IndexError):
            pass

        # Process each participant
        for participant in event.get('item', {}).get('participants', {}).get('details', []):
            try:
                person = participant.get('personDetails', {})
                address = person.get('streetAddress', {})
                phones = person.get('phoneNumbers', [])

                self.parsed_webhook = {
                    "course_type": self.course_type,
                    "course_location": event['item']['productName'].split(": ", 1)[0],
                    "course_date": event['item']['startTime'].split("T", 1)[0],
                    "first_name": person.get('firstName', ''),
                    "last_name": person.get('lastName', ''),
                    "email": person.get('emailAddress', ''),
                    "line1": address.get('address1', ''),
                    "line2": address.get('address2', ''),
                    "city": address.get('city', ''),
                    "province": province_abbreviator(address.get('state', '')),
                    "phone": phone_parser(phones[0]['number']) if phones else '',
                    "postal_code": address.get('postcode', ''),
                    "cpr_level": cpr_level
                }
            except (KeyError, IndexError, TypeError) as e:
                print(f"Malformed participant data: {e}")
                bookeo_response.append("Malformed Data")
                continue

            # Attempt registration with retries
            for attempt in range(1, 5):
                try:
                    result = self.register_participant()
                    bookeo_response.append(result)

                    if result in ("Multiple Courses Found", "No Courses Found"):
                        self.send_email(result, bookeo_response, event['item']['bookingNumber'])
                        self.bookeo_put(str(bookeo_response), event)
                        return {'statusCode': 200, 'body': ''}
                    break

                except requests.exceptions.RequestException as e:
                    print(f"Attempt {attempt} failed: {e}")
                    if attempt == 4:
                        bookeo_response.append("Failure")

        # Determine overall status
        status = "SUCCESS" if all(r == "Success" for r in bookeo_response) else "FAILURE"

        self.bookeo_put(str(bookeo_response), event)
        self.send_email(status, bookeo_response, event['item']['bookingNumber'])

        return {'statusCode': 200, 'body': ''}


def province_abbreviator(province: str) -> str:
    """Convert Canadian province name to abbreviation."""
    province_map = {
        "lberta": "AB",
        "olumbia": "BC",
        "anitoba": "MB",
        "runswick": "NB",
        "abrador": "NL",
        "ewfoundland": "NL",
        "erritories": "NT",
        "cotia": "NS",
        "unavut": "NU",
        "ntario": "ON",
        "sland": "PE",
        "uebec": "QC",
        "askatchewan": "SK",
    }

    for key, abbrev in province_map.items():
        if key in province:
            return abbrev
    return "YT"  # Default to Yukon


def phone_parser(phone: str) -> str:
    """Format phone number for Red Cross system."""
    # Remove any non-digit characters
    digits = ''.join(c for c in phone if c.isdigit())
    if len(digits) >= 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:10]}"
    return phone


def course_name_parser(course_name: str, course_type: str) -> str:
    """Parse course name to determine course type."""
    if course_type:
        if "Recertification" in course_name:
            return course_type.replace("Blended", "(Recert)")
        return course_type

    # Strip "Private " prefix
    if course_name.startswith("Private "):
        course_name = course_name[8:]

    # Map course names
    if "Red Cross Babysitter's Course" in course_name:
        return "Babysitter Course"
    if "Basic Life Support" in course_name:
        if "Recertification" in course_name:
            return "Basic Life Support Recertification"
        return "Basic Life Support"
    if "Red Cross First Aid Course" in course_name:
        if "Recertification" in course_name:
            return "Standard First Aid (Recert)"
        return "Standard First Aid Blended"

    return course_name


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """AWS Lambda entry point."""
    return CprBot().run(event)


# For local testing
if __name__ == "__main__":
    # Example test event structure
    test_event = {
        "itemId": "TEST123",
        "item": {
            "bookingNumber": "TEST-001",
            "productName": "Test Location: Standard First Aid",
            "startTime": "2024-01-15T09:00:00",
            "options": [],
            "participants": {
                "details": []
            }
        }
    }

    print("CprBot initialized for testing")
    print("Set environment variables and provide real event data to test")
