# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Status

**Production Ready - v2.0.0 (November 2025)**

## Project Overview

SaveALife CPR Bot automates registration of CPR/First Aid course participants from Bookeo booking system into the Canadian Red Cross MyRC portal. It handles:
- Azure AD B2C two-step authentication to MyRC
- Course lookup by date, type, and location (substring matching)
- Participant registration via OData REST API (new or existing contacts)
- Smart CPR level assignment based on course type
- Email notifications and Bookeo booking updates
- Async Lambda invocation for fast webhook response

**Why this project exists:** The original `lambda_function.py` stopped working when Canadian Red Cross updated their MyRC portal's authentication flow and APIs. This rewrite (`cpr_bot.py`) adapts to the new B2C two-step auth and OData REST API structure.

## Development Commands

```bash
# Install dependencies
uv sync                  # Using uv (recommended)
pip install -e .         # Using pip

# Test login connectivity
python test_login.py           # Basic login test
python test_login.py --full    # Full test including course search

# Dry run registration (no actual changes)
python test_dry_run.py

# Real registration test (prompts for confirmation)
python test_dry_run.py --real
```

## Architecture

### Core Files
- `cpr_bot.py` - Main bot implementation (`CprBot` class)
- `lambda_function.py` - Original AWS Lambda script (legacy, reference only)
- `test_login.py` - Authentication test script
- `test_dry_run.py` - Registration flow test with dry run support

### Authentication Flow (Azure AD B2C)
The bot uses a six-step authentication process:
1. GET MyRC sign-in page → extract CSRF and StateProperties
2. POST email + password to B2C SelfAsserted endpoint
3. GET confirmation page → extract new CSRF (triggers second password prompt)
4. POST password again (second step of two-step flow)
5. GET final confirmation → extract state and id_token
6. POST tokens to MyRC → get SecureConfiguration from CourseManagement page

### Key API Details
- B2C Tenant: `crcsb2c.onmicrosoft.com`
- B2C Policy: `B2C_1A_MYRC_SIGNUP_SIGNIN` (case-sensitive)
- SecureConfiguration: Extracted from `data-view-layouts` attribute (base64 JSON)
- Course search endpoint: `/_services/entity-grid-data.json/6d6b3012-e709-4c45-a00d-df4b3befc518`

### MyRC OData API Endpoints

These are the current REST/OData endpoints (as of Nov 2025):

**Contact Search:**
```
GET /_api/contacts?$filter=(lastname eq 'DOE' and emailaddress1 eq 'john@example.com' and statecode eq 0)
```

**Create Contact:**
```
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
```
POST /_api/crc_courseparticipants
Content-Type: application/json

{
  "crc_attendee@odata.bind": "/contacts(CONTACT_GUID)",
  "crc_coursesession@odata.bind": "/crc_coursesessions(SESSION_GUID)",
  "crc_participanttype": "0",
  "crc_status": "171120001"
}
```

Note: These endpoints may change when MyRC updates their portal. The original `lambda_function.py` used form-based endpoints that are now deprecated.

### Course Type Mappings
Bookeo course names map to MyRC types:
- "Standard First Aid" → "Standard First Aid Blended"
- "Emergency First Aid" → "Emergency First Aid Blended"
- "CPR/AED" → "CPR/AED Blended"
- "Basic Life Support" → "Basic Life Support"
- "Babysitter's Course" → "Babysitter Course"
- "Stay Safe!" → "Stay Safe!"
- Recertification adds "(Recert)" suffix

### CPR Level Logic
- **Regular courses**: Always register as Level C (code `171120001`)
- **Recert/BLS courses**: Keep customer's selection (A=`171120000`, C=`171120001`)
- **Babysitter/Stay Safe**: No CPR level field (None)

### Lambda Async Pattern
The `lambda_handler` uses self-invocation for webhook responsiveness:
1. First call: Parse API Gateway body, invoke self async, return `200 OK` immediately
2. Async call (has `_async_process` flag): Execute `CprBot().run(event)`

## Environment Variables

Required in `.env`:
```
MYRC_EMAIL=           # MyRC portal login
MYRC_PASSWORD=        # MyRC portal password
BOOKEO_API_KEY=       # Bookeo API key
BOOKEO_SECRET_KEY=    # Bookeo secret key
EMAIL_USER=           # Gmail for notifications
EMAIL_PASSWORD=       # Gmail app password
EMAIL_RECIPIENTS=     # JSON array of recipients
```

## Deployment

Designed for AWS Lambda triggered by Bookeo webhooks via API Gateway.

- Entry point: `lambda_handler(event, context)` in `cpr_bot.py`
- Deployment package: `lambda_deployment_full.zip` (includes requests + dependencies)
- Lambda needs `lambda:InvokeFunction` permission for self-invocation
- API Gateway must be configured to pass body to Lambda

## AWS CLI Health Check Commands

Use `--profile savealife` for all commands (credentials configured in AWS CLI):

```bash
# List recent log streams (most recent first)
MSYS_NO_PATHCONV=1 aws logs describe-log-streams --profile savealife \
  --log-group-name "/aws/lambda/savealife-cpr-bot" \
  --order-by LastEventTime --descending --limit 10 \
  --query "logStreams[*].[logStreamName,lastEventTimestamp]" --output table

# Check for successful registrations (last 24 hours)
START_TIME=$(python -c "import time; print(int((time.time() - 86400) * 1000))") && \
MSYS_NO_PATHCONV=1 aws logs filter-log-events --profile savealife \
  --log-group-name "/aws/lambda/savealife-cpr-bot" \
  --filter-pattern "Successfully registered" --start-time $START_TIME \
  --query "events[*].[timestamp,message]" --output text

# Check for errors (last 24 hours)
START_TIME=$(python -c "import time; print(int((time.time() - 86400) * 1000))") && \
MSYS_NO_PATHCONV=1 aws logs filter-log-events --profile savealife \
  --log-group-name "/aws/lambda/savealife-cpr-bot" \
  --filter-pattern "ERROR" --start-time $START_TIME \
  --query "events[*].[timestamp,message]" --output text

# Check for "No Courses Found" (course not in MyRC)
START_TIME=$(python -c "import time; print(int((time.time() - 86400) * 1000))") && \
MSYS_NO_PATHCONV=1 aws logs filter-log-events --profile savealife \
  --log-group-name "/aws/lambda/savealife-cpr-bot" \
  --filter-pattern "No Courses Found" --start-time $START_TIME \
  --query "events[*].[timestamp,message]" --output text

# Get specific log stream details
MSYS_NO_PATHCONV=1 aws logs get-log-events --profile savealife \
  --log-group-name "/aws/lambda/savealife-cpr-bot" \
  --log-stream-name 'STREAM_NAME_HERE' --limit 50 \
  --query "events[*].message" --output text

# Check Lambda function status
aws lambda list-functions --profile savealife \
  --query "Functions[*].[FunctionName,LastModified,Runtime]" --output table
```

Note: `MSYS_NO_PATHCONV=1` prevents Git Bash from converting `/aws/...` paths on Windows.

## Key Implementation Notes

- **Substring matching**: Course type and location lookups use `in` operator, not exact match
- **Debug logging**: Extensive `print()` statements for CloudWatch debugging
- **Contact ID**: Returned in `entityid` header from POST `/_api/contacts`
- **Already registered**: Treated as success if participant already in course

## Important Limitation: Course Must Exist in MyRC First

Bookeo and MyRC are **separate systems**:
- **Bookeo** = Customer booking/payment system
- **MyRC** = Red Cross certification portal

The bot only works if the course session exists in MyRC **before** the customer books in Bookeo.

**If a customer books before the MyRC course is created:**
- Webhook fires → returns "No Courses Found"
- Bot does NOT retry automatically when course is later created
- **Manual fix required:** Re-trigger webhook from Bookeo OR manually register in MyRC

**Correct workflow:**
1. Create course session in MyRC first
2. Customer books in Bookeo
3. Bot auto-registers in MyRC
