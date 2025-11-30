# SaveALife CPR Bot

Automated course registration bot that syncs Bookeo bookings to the Canadian Red Cross MyRC portal.

## Overview

This bot listens for Bookeo webhook events when customers book CPR/First Aid courses and automatically registers them in the Canadian Red Cross MyRC system. It handles:

- Azure AD B2C authentication to MyRC portal
- Course lookup by date, type, and location
- Participant registration (new or existing contacts)
- Email notifications for registration status
- Bookeo booking updates with registration results

> **Note:** This is a rewrite of the original `lambda_function.py` which stopped working when Canadian Red Cross updated their MyRC portal's authentication flow (from single-step to two-step B2C) and migrated to OData REST APIs. The original form-based endpoints are now deprecated.

## How It Works

```
┌─────────┐     Webhook      ┌─────────┐     B2C Auth     ┌─────────┐
│ Bookeo  │ ───────────────► │ CPR Bot │ ───────────────► │  MyRC   │
│ Booking │                  │         │ ◄─────────────── │ Portal  │
└─────────┘                  └─────────┘   Course Data    └─────────┘
     ▲                            │
     │      Update Booking        │
     └────────────────────────────┘
```

1. Customer books a course on Bookeo
2. Bookeo sends webhook to the bot
3. Bot authenticates with MyRC via Azure AD B2C (two-step flow)
4. Bot searches for matching course session
5. Bot registers participant(s) in MyRC
6. Bot updates Bookeo with registration status
7. Email notification sent with results

## Setup

### Prerequisites

- Python 3.10+
- [uv](https://github.com/astral-sh/uv) package manager (recommended) or pip

### Installation

```bash
# Clone the repository
git clone https://github.com/spragginsdesigns/savealife-cpr.git
cd savealife-cpr

# Install dependencies with uv
uv sync

# Or with pip
pip install -r requirements.txt
```

### Configuration

1. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` with your credentials:
   ```env
   # Bookeo API Credentials
   BOOKEO_API_KEY=your_bookeo_api_key
   BOOKEO_SECRET_KEY=your_bookeo_secret_key

   # MyRC Portal Credentials
   MYRC_EMAIL=your_myrc_email@example.com
   MYRC_PASSWORD=your_myrc_password

   # Email Notifications (optional)
   EMAIL_USER=your_gmail@gmail.com
   EMAIL_PASSWORD=your_gmail_app_password
   EMAIL_RECIPIENTS=["recipient1@example.com", "recipient2@example.com"]
   ```

### Testing the Connection

Run the test script to verify your credentials work:

```bash
python test_login.py

# Full test including course search
python test_login.py --full
```

Expected output:
```
==================================================
LOGIN SUCCESSFUL!
==================================================
Secure config obtained: ...
```

## Usage

### As AWS Lambda

The bot is designed to run as an AWS Lambda function triggered by Bookeo webhooks:

```python
from cpr_bot import lambda_handler

# Lambda will call this with the Bookeo webhook event
def handler(event, context):
    return lambda_handler(event, context)
```

### Locally (for testing)

```python
from cpr_bot import CprBot

bot = CprBot()

# Test event structure
event = {
    "itemId": "BOOKING_ID",
    "item": {
        "bookingNumber": "12345",
        "productName": "Cambridge: Standard First Aid",
        "startTime": "2025-12-01T09:00:00",
        "options": [...],
        "participants": {
            "details": [...]
        }
    }
}

result = bot.run(event)
```

## Bookeo Webhook Setup

1. Go to Bookeo Settings > Integrations > Webhooks
2. Add a new webhook pointing to your Lambda endpoint
3. Select "New Booking" event type
4. Use your API key and secret key for authentication

## Course Type Mapping

The bot maps Bookeo course names to MyRC course types:

| Bookeo Course | MyRC Course Type |
|--------------|------------------|
| Standard First Aid | Standard First Aid Blended |
| Emergency First Aid | Emergency First Aid Blended |
| CPR/AED | CPR/AED Blended |
| Basic Life Support | Basic Life Support |
| Recertification courses | (Recert) suffix |

## Response Codes

The bot returns these status codes in Bookeo's externalRef field:

| Code | Meaning |
|------|---------|
| Success | Participant registered successfully |
| No Courses Found | No matching course for date/location/type |
| Multiple Courses Found | Ambiguous match - manual review needed |
| Email in Use Already | Contact exists with different details |
| Login Failed | MyRC authentication failed |
| Malformed Data | Missing required participant info |

## Technical Details

### Authentication Flow

The bot uses Azure AD B2C with a two-step authentication:

1. GET sign-in page, extract CSRF token and StateProperties
2. POST email + password to SelfAsserted endpoint
3. GET confirmation page, extract new CSRF
4. POST password again (second step)
5. GET final confirmation with id_token
6. POST tokens to MyRC to complete sign-in

### SecureConfiguration

MyRC uses a PowerApps portal with encrypted grid configurations. The bot extracts `Base64SecureConfiguration` from the `data-view-layouts` attribute on the CourseManagement page, which is required for all API calls.

### MyRC OData API Reference

The portal uses Dynamics 365/PowerApps OData endpoints:

**Contact Search:**
```http
GET /_api/contacts?$filter=(lastname eq 'DOE' and emailaddress1 eq 'john@example.com' and statecode eq 0)
```

**Create Contact:**
```http
POST /_api/contacts
Content-Type: application/json

{
  "firstname": "John",
  "lastname": "Doe",
  "emailaddress1": "john@example.com",
  "address1_line1": "123 Main St",
  "address1_city": "Toronto",
  "address1_stateorprovince": "ON",
  "address1_postalcode": "M5V 1A1",
  "telephone1": "(416) 555-1234"
}
```

**Add Participant to Course Session:**
```http
POST /_api/crc_courseparticipants
Content-Type: application/json

{
  "crc_attendee@odata.bind": "/contacts(CONTACT_GUID)",
  "crc_coursesession@odata.bind": "/crc_coursesessions(SESSION_GUID)",
  "crc_participanttype": "0",
  "crc_status": "171120001"
}
```

## Troubleshooting

### Login Failed
- Verify MyRC credentials in `.env`
- Check if MyRC portal is accessible
- The B2C policy may have changed (current: `B2C_1A_MYRC_SIGNUP_SIGNIN`)

### No Courses Found
- Verify course date format (YYYY-MM-DD)
- Check that location name matches exactly
- Ensure course type mapping is correct

### API Errors
- SecureConfiguration may have expired (re-login)
- Verification token may be stale (refresh)

## License

Private - SaveALife CPR Training

## Support

For issues, contact tyler@savealifecpa.ca
