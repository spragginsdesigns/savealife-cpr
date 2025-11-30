# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SaveALife CPR Bot automates registration of CPR/First Aid course participants from Bookeo booking system into the Canadian Red Cross MyRC portal. It handles:
- Azure AD B2C two-step authentication to MyRC
- Course lookup by date, type, and location
- Participant registration (new or existing contacts)
- Email notifications and Bookeo booking updates

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

### Course Type Mappings
Bookeo course names map to MyRC types:
- "Standard First Aid" → "Standard First Aid Blended"
- "Emergency First Aid" → "Emergency First Aid Blended"
- "CPR/AED" → "CPR/AED Blended"
- "Basic Life Support" → "Basic Life Support"
- Recertification adds "(Recert)" suffix

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

Designed for AWS Lambda triggered by Bookeo webhooks. Entry point: `lambda_handler(event, context)` in `cpr_bot.py`.
