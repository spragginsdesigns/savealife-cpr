"""
================================================================================
DEPRECATED - NO LONGER IN SERVICE
================================================================================

This Lambda function is deprecated and is no longer operational or maintained.
It has been preserved for historical documentation and reference purposes only.

Original Purpose:
    This AWS Lambda function automated the process of registering course 
    participants from Bookeo (booking system) into the Canadian Red Cross 
    MyRC portal for CPR/First Aid certification courses.

Functionality (when active):
    - Received webhook events from Bookeo when new bookings were created
    - Authenticated with the Red Cross MyRC portal
    - Searched for matching course sessions
    - Registered participants in the Red Cross system
    - Updated Bookeo with registration status
    - Sent email notifications for successes/failures

Deprecation Date: November 2025
Reason: System migration / service discontinued

DO NOT attempt to deploy or use this code - it will not function as the 
external APIs and authentication mechanisms have changed.
================================================================================
"""

# ============================================================================
# DEPRECATED CODE - KEPT FOR DOCUMENTATION ONLY
# ============================================================================

from botocore.vendored import requests  # Note: This import is also deprecated in newer AWS Lambda
import pickle, re, json, os, random, smtplib


class Cprbot:
  """
  [DEPRECATED] CPR/First Aid course registration bot.
  
  This class is no longer functional and is preserved for documentation only.
  """
  def __init__(self):
    self.secure_config=""
    self.session = requests.session()
    self.job_ids=""
    self.parsed_webhook=""
    self.output_myrc_id="N/A"
    self.course_type = ""

  def send_email(self, subject, bookeo_response, booking_number):
    recipients = json.loads(os.environ['email_recipients'])
    email_text = """\
    From: %s\nTo: %s\nSubject: %s\n
    Status Codes: %s
    Booking Number: %s
    Myrc Course Number: %s
    Course Type: %s
    *The status codes indicate the problems (or successes) each participant in this booking had when being entered. They are in the same order as the participants in bookeo.
    """ % (os.environ['email_user'], ", ".join(recipients), subject, str(bookeo_response), booking_number, str(self.output_myrc_id), self.course_type)

    server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
    server.ehlo()
    server.login(os.environ['email_user'], os.environ['email_password'])
    server.sendmail(os.environ['email_user'], recipients, email_text)
    server.close()

  def bookeo_put(self, response_code, event):
    print(response_code)

    headers = {
      'Content-Type': 'application/json',
    }
    params = (
      ('secretKey', os.environ['secret_key']),
      ('mode', 'backend'),
      ('apiKey', os.environ['api_key']),
    )
    event['item']['externalRef'] = response_code + ", myrc: " + self.output_myrc_id
    event['item'].pop('startTime', None)
    event['item'].pop('endTime', None)
    event['item'].pop('customer', None)
    event['item']['participants'].pop('details', None)
    return self.session.put('https://api.bookeo.com/v2/bookings/' + event['itemId'], params=params, data=json.dumps(event['item']), headers=headers)

  def request1(self):
    params = (
        ('returnUrl', '/en/'),
    )
    return self.session.get('https://myrc.redcross.ca/en/SignIn', params=params)

  def request2(self, state_properties, csrf):
    headers = {
      'X-CSRF-TOKEN': csrf,
    }
    params = (
      ('tx', 'StateProperties=' + state_properties),
      ('p', 'B2C_1_PS_Dev_SUSI'),
    )
    data = {
      'request_type': 'RESPONSE',
      'logonIdentifier': os.environ['logon_identifier'],
      'password': os.environ['password']
    }
    return self.session.post('https://crcsb2c.b2clogin.com/crcsb2c.onmicrosoft.com/B2C_1_PS_Dev_SUSI/SelfAsserted', headers=headers, params=params, data=data)

  def request3(self, state_properties, csrf):
    params = (
      ('csrf_token', csrf),
      ('tx', 'StateProperties=' + state_properties),
      ('p', 'B2C_1_PS_Dev_SUSI'),
    )
    return self.session.get('https://crcsb2c.b2clogin.com/crcsb2c.onmicrosoft.com/B2C_1_PS_Dev_SUSI/api/CombinedSigninAndSignup/confirmed', params=params)

  def request4(self, state, id_token):
    data = {
      'state': state,
      'id_token': id_token
    }
    return self.session.post('https://myrc.redcross.ca/', data=data)

  def request5(self, verif_token, secure_config, page):
    headers = {
      'Content-Type': 'application/json; charset=UTF-8',
      'X-Requested-With': 'XMLHttpRequest',
      '__RequestVerificationToken': verif_token,
    }
    data = '{"base64SecureConfiguration": "' + secure_config + '","sortExpression":"crc_startdate ASC","search":"' + self.parsed_webhook["course_date"] + '","page":' + str(page) + ',"pageSize":10,"filter":"account","metaFilter":null,"customParameters":[]}'
    return self.session.post('https://myrc.redcross.ca/_services/entity-grid-data.json/6d6b3012-e709-4c45-a00d-df4b3befc518', headers=headers, data=data)

  def request6(self):
    params = (
      ('refentity', 'crc_coursesession'),
      ('refid', self.job_ids["ref_id"]),
      ('refrel', 'crc_coursesession_crc_courseparticipant'),
    )
    return self.session.get('https://myrc.redcross.ca/en/CourseManagement/SessionDetails/ContactSearch/',  params=params)

  def request7(self, view_state, view_state_gen, event_validation):
    params = (
      ('refentity', 'crc_coursesession'),
      ('refid', self.job_ids["ref_id"]),
      ('refrel', 'crc_coursesession_crc_courseparticipant'),
    )
    data = {
      '__VIEWSTATE': view_state,
      '__VIEWSTATEGENERATOR': view_state_gen,
      '__EVENTVALIDATION': event_validation,
      'ctl00$ctl00$ContentContainer$MainContent$txtName': self.parsed_webhook["last_name"],
      'ctl00$ctl00$ContentContainer$MainContent$txtEmail': self.parsed_webhook["email"],
      'ctl00$ctl00$ContentContainer$MainContent$btnSearch': 'Search'
    }
    return self.session.post('https://myrc.redcross.ca/en/CourseManagement/SessionDetails/ContactSearch/', params=params, data=data)

  def request8(self):
    params = (
      ('refentity', 'crc_coursesession'),
      ('refid', self.job_ids["ref_id"]),
      ('refrel', 'crc_coursesession_crc_courseparticipant'),
    )
    return self.session.get('https://myrc.redcross.ca/en/CourseManagement/SessionDetails/RosterSubmission/', params=params)

  def request9(self, view_state, view_state_gen):
    params = (
      ('refentity', 'crc_coursesession'),
      ('refid', self.job_ids["ref_id"]),
      ('refrel', 'crc_coursesession_crc_courseparticipant'),
    )
    data = {
      '__EVENTTARGET': 'ctl00$ctl00$ContentContainer$MainContent$EntityControls$WebFormControl$NextButton',
      '__VIEWSTATE': view_state,
      '__VIEWSTATEGENERATOR': view_state_gen,
      'EntityFormView_EntityName': 'contact',
      'ctl00$ctl00$ContentContainer$MainContent$EntityControls$WebFormControl$EntityFormView$crc_language': '171120000',
      'ctl00$ctl00$ContentContainer$MainContent$EntityControls$WebFormControl$EntityFormView$firstname': self.parsed_webhook["first_name"],
      'ctl00$ctl00$ContentContainer$MainContent$EntityControls$WebFormControl$EntityFormView$lastname': self.parsed_webhook["last_name"],
      'ctl00$ctl00$ContentContainer$MainContent$EntityControls$WebFormControl$EntityFormView$emailaddress1': self.parsed_webhook["email"],
      'ctl00$ctl00$ContentContainer$MainContent$EntityControls$WebFormControl$EntityFormView$address1_line1': self.parsed_webhook["line1"],
      'ctl00$ctl00$ContentContainer$MainContent$EntityControls$WebFormControl$EntityFormView$address1_line2': self.parsed_webhook["line2"],
      'ctl00$ctl00$ContentContainer$MainContent$EntityControls$WebFormControl$EntityFormView$address1_city': self.parsed_webhook["city"],
      'ctl00$ctl00$ContentContainer$MainContent$EntityControls$WebFormControl$EntityFormView$address1_stateorprovince': self.parsed_webhook["province"],
      'ctl00$ctl00$ContentContainer$MainContent$EntityControls$WebFormControl$EntityFormView$telephone1': self.parsed_webhook["phone"],
      'ctl00$ctl00$ContentContainer$MainContent$EntityControls$WebFormControl$EntityFormView$address1_postalcode': self.parsed_webhook["postal_code"]
    }
    return self.session.post('https://myrc.redcross.ca/en/CourseManagement/SessionDetails/RosterSubmission/', params=params, data=data)

  def request10(self, final_submit_url, participantid, view_state, view_state_gen):
    data = {
      '__EVENTTARGET': 'ctl00$ctl00$ContentContainer$MainContent$EntityControls$EntityFormControl$InsertButton',
      '__VIEWSTATE': view_state,
      '__VIEWSTATEGENERATOR': view_state_gen,
      'ctl00$ctl00$ContentContainer$MainContent$EntityControls$EntityFormControl$EntityFormControl_EntityFormView$EntityFormControl_EntityFormView_EntityName': 'crc_courseparticipant',
      'ctl00$ctl00$ContentContainer$MainContent$EntityControls$EntityFormControl$EntityFormControl_EntityFormView$crc_coursesession': self.job_ids["ref_id"],
      'ctl00$ctl00$ContentContainer$MainContent$EntityControls$EntityFormControl$EntityFormControl_EntityFormView$crc_coursesession_entityname': 'crc_coursesession',
      'ctl00$ctl00$ContentContainer$MainContent$EntityControls$EntityFormControl$EntityFormControl_EntityFormView$crc_attendee': participantid,
      'ctl00$ctl00$ContentContainer$MainContent$EntityControls$EntityFormControl$EntityFormControl_EntityFormView$crc_attendee_entityname': 'contact',
      'ctl00$ctl00$ContentContainer$MainContent$EntityControls$EntityFormControl$EntityFormControl_EntityFormView$crc_cprlevel': self.parsed_webhook["cpr_level"],
      'ctl00$ctl00$ContentContainer$MainContent$EntityControls$EntityFormControl$EntityFormControl_EntityFormView$crc_participanttype': '0',
      'ctl00$ctl00$ContentContainer$MainContent$EntityControls$EntityFormControl$EntityFormControl_EntityFormView$crc_status': '171120001'
    }
    return self.session.post(final_submit_url, data=data)

  def parse_and_find_ids(self, json_response_arr):
    self.output_myrc_id = "N/A"
    jsonified = json.loads(json_response_arr)
    matchedIds=[]
    for container in jsonified:
      for record in container["Records"]:
        matchedType=False
        matchedLocation=False
        courseId="0"
        refId=record["Id"]
        for attribute in record["Attributes"]:
          if attribute["Name"] == "crc_coursetype":
            if attribute["Value"]["Name"] == self.parsed_webhook["course_type"]:
              matchedType=True
          elif attribute["Name"] == "crc_facility":
            if attribute["Value"]["Name"] == self.parsed_webhook["course_location"]:
              matchedLocation=True
          elif attribute["Name"] == "crc_name":
            courseId=attribute["Value"]
        if matchedType and matchedLocation:
          matchedIds.append({"course_id": courseId, "ref_id": refId})
    if len(matchedIds) == 1:
      self.output_myrc_id = matchedIds[0]["course_id"]
      return matchedIds[0]
    if len(matchedIds) == 0:
      return None
    return "multiple"

  def main(self):
    #Set up session and load cookies if they are available
    if os.path.isfile('/tmp/cookies'):
      with open('/tmp/cookies', 'rb') as f:
          self.session.cookies.update(pickle.load(f))

    #Check if session still valid
    #response = session.get('https://myrc.redcross.ca/en/CourseManagement/')
    # Overriding session checks to try and bugfix runtime issue
    response = ""
    if False: #os.environ['name'] in response.text:
      #Session is valid!
      self.secure_config = re.search('Base64SecureConfiguration&quot;:&quot;([^&]*)&', response.text).group(1)
    else:
      #Session invalid, start the login process
      response = self.request1()
      response.raise_for_status()
      state_properties = re.search('StateProperties=([^"]*)"', response.text).group(1)
      csrf = re.search('"csrf":"([^"]*)"', response.text).group(1)
      response = self.request2(state_properties, csrf)
      response.raise_for_status()
      response = self.request3(state_properties, csrf)
      response.raise_for_status()
      state = re.search('id=\'state\' value=\'([^\']*)\'', response.text).group(1)
      id_token = re.search('id=\'id_token\' value=\'([^\']*)\'', response.text).group(1)
      response = self.request4(state, id_token)
      response.raise_for_status()
      self.secure_config = re.search('Base64SecureConfiguration&quot;:&quot;([^&]*)&', response.text).group(1)

    response = self.session.get('https://myrc.redcross.ca/_layout/tokenhtml')
    verif_token = re.search('value="([^"]*)"', response.text).group(1)
    #Search for specific course based on the (possible unconclusive) information we have
    response = self.request5(verif_token, self.secure_config, 1)
    json_response_arr = "[" + response.text
    num_pages = re.search('"PageCount":([^,]*),', response.text).group(1)
    for page in range(2, int(num_pages)+1):
      response = self.request5(verif_token, self.secure_config, page)
      json_response_arr += "," + response.text
    json_response_arr += "]"
    response.raise_for_status()
    #Exit if impossible to determine course to work with
    self.job_ids = self.parse_and_find_ids(json_response_arr)
    if self.job_ids == None:
      return "No Courses Found"
    if self.job_ids == "multiple":
      return "Multiple Courses Found"

    response = self.request6()
    response.raise_for_status()
    view_state = re.search('id="__VIEWSTATE" value="([^"]*)"', response.text).group(1)
    view_state_gen = re.search('id="__VIEWSTATEGENERATOR" value="([^"]*)"', response.text).group(1)
    event_validation = re.search('id="__EVENTVALIDATION" value="([^"]*)"', response.text).group(1)

    response = self.request7(view_state, view_state_gen, event_validation)
    response.raise_for_status()
    final_submit_url="https://myrc.redcross.ca/en/participantcreate/?"
    #Check if user already exists in red cross db
    if "No Contact found." in response.text:
      #Doees not exist, thus add them
      response = self.request8()
      response.raise_for_status()
      view_state = re.search('id="__VIEWSTATE" value="([^"]*)"', response.text).group(1)
      view_state_gen = re.search('id="__VIEWSTATEGENERATOR" value="([^"]*)"', response.text).group(1)

      response = self.request9(view_state, view_state_gen)
      response.raise_for_status()
      if "Contact with this email ID already exists" in response.text:
        return "Email in Use Already"
      participant_reg = re.search('en/participantcreate/\?([^\s]*)\s', response.text)
      if participant_reg == None:
        return "Invalid Customer Data"
      final_submit_url += participant_reg.group(1)
    else:
      #Already exists, so continue through the in page link
      final_submit_url += re.search('en/participantcreate/\?([^\s]*)\s', response.text).group(1)
      response = self.session.get(final_submit_url)

    #Submit final post for client to be added to course
    participantid = re.search('\?id=([^&]*)&', final_submit_url).group(1)
    view_state = re.search('id="__VIEWSTATE" value="([^"]*)"', response.text).group(1)
    view_state_gen = re.search('id="__VIEWSTATEGENERATOR" value="([^"]*)"', response.text).group(1)

    response = self.request10(final_submit_url, participantid, view_state, view_state_gen)
    response.raise_for_status()

    #post against bookeo to state how we did
    return "Success"


    #Save cookies to file
    with open('/tmp/cookies', 'wb') as f:
      pickle.dump(self.session.cookies, f)

  def run(self, event):
    print(event)
    #This could become outdated if they add more cpr options
    cpr_level = "171120000"
    bookeo_response = []
    self.course_type = ""

    if 'options' in event['item']:
      for option in event['item']['options']:
        if "Certification" in option['name']:
          if "evel A" in option['value']:
            cpr_level = "171120000"
          elif "evel C" in option['value']:
            cpr_level = "171120001"
          if "Standard First Aid" in option['value']:
            self.course_type = "Standard First Aid Blended"
          elif "Emergency First Aid" in option['value']:
            self.course_type = "Emergency First Aid Blended"
          elif "AED" in option['value']:
            self.course_type = "CPR/AED Blended"
          elif "Oxygen Therapy" in option['value']:
            self.course_type = "Basic Life Support with Airway Management and Oxygen Therapy"
    try:
      self.course_type = course_name_parser(event['item']['productName'].split(": ", 1)[1], self.course_type)
    except:
      pass

    for participant in event['item']['participants']['details']:
      try:
        self.parsed_webhook = {
          "course_type": self.course_type,
          "course_location": event['item']['productName'].split(": ", 1)[0],
          "course_date": event['item']['startTime'].split("T", 1)[0],
          "first_name": participant['personDetails']['firstName'],
          "last_name": participant['personDetails']['lastName'],
          "email": participant['personDetails']['emailAddress'],
          "line1": participant['personDetails']['streetAddress']['address1'],
          "line2": "",
          "city": participant['personDetails']['streetAddress']['city'],
          "province": province_abbreviator(participant['personDetails']['streetAddress']['state']),
          "phone": phone_parser(participant['personDetails']['phoneNumbers'][0]['number']),
          "postal_code": participant['personDetails']['streetAddress']['postcode'],
          "cpr_level": cpr_level
        }
      except:
        bookeo_response.append("Malformed Data")
        continue
      for i in range(1, 5):
        try:
          mission = self.main()
          bookeo_response.append(mission)
          if (mission == "Multiple Courses Found") or (mission == "No Courses Found"):
            self.send_email(mission, bookeo_response, event['item']['bookingNumber'])
            self.bookeo_put(str(bookeo_response), event)
            return {
              'statusCode': 200,
              'body': ""
            }
          break
        except requests.exceptions.RequestException as e:
          print("Attempt number", i, "has failed.")
          print(e)
        if i == 4:
          bookeo_response.append("Failure")
    stat = "SUCCESS"
    for res in bookeo_response:
      if res != "Success":
        stat = "FAILURE"
    self.bookeo_put(str(bookeo_response), event)
    self.send_email(stat, bookeo_response, event['item']['bookingNumber'])

    return {
      'statusCode': 200,
      'body': ""
    }

def province_abbreviator(province):
  if "lberta" in province:
    return "AB"
  if "olumbia" in province:
    return "BC"
  if "anitoba" in province:
    return "MB"
  if "runswick" in province:
    return "NB"
  if "abrador" in province:
    return "NL"
  if "ewfoundland" in province:
    return "NL"
  if "erritories" in province:
    return "NT"
  if "cotia" in province:
    return "NS"
  if "unavut" in province:
    return "NU"
  if "ntario" in province:
    return "ON"
  if "sland" in province:
    return "PE"
  if "uebec" in province:
    return "QC"
  if "askatchewan" in province:
    return "SK"
  return "YT"

def phone_parser(phone):
  return "(" + phone[:3] + ") " + phone[3:6] + "-" + phone[6:]

def course_name_parser(course_name, course_type):
  if course_type:
    if "Recertification" in course_name:
      return course_type.replace("Blended", "(Recert)")
    return course_type

  if course_name.startswith("Private "):
    course_name = course_name[8:]
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

def lambda_handler(event, context):
  """
  [DEPRECATED] AWS Lambda entry point - NO LONGER FUNCTIONAL.
  
  This handler is preserved for documentation purposes only and should not be deployed.
  """
  raise DeprecationWarning("This Lambda function is deprecated and no longer in service.")
  # Original code preserved below for reference:
  # return Cprbot().run(event)
