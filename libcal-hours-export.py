import json
import logging
import os
import sys
import json
import urllib.parse
import requests
import argparse
import csv
import datetime as dt
import re

import furl
from dotenv import load_dotenv

# Get hours for a date range from LibCal Hours using the API and write to CSV for loading
# to a reporting database.

# See https://umd.libcal.com/admin/api/1.1/endpoint/hours
# and https://umd.libcal.com/admin/api/authentication


def get_configuration():
    """ Get runtime configuration from the command line and environment variables. """

    # Get command line arguments
    parser = argparse.ArgumentParser()

    parser.add_argument("-o", "--output-file",
                        type=argparse.FileType('w'),
                        default="-",
                        help="CSV output file; default is stdout",)

    yesterday = (dt.date.today() - dt.timedelta(days=1)).isoformat()

    parser.add_argument('-f', '--from-date',
                        default=yesterday,
                        help='from date (YYYY-MM-DD), inclusive; default is yesterday')

    parser.add_argument('-t', '--to-date',
                        default=yesterday,
                        help='to date (YYYY-MM-DD), inclusive; default is yesterday')

    args = parser.parse_args()

    # Add any environment variables from .env
    load_dotenv('.env')

    # Get environment variables
    env = {}
    for key in ('LIBCAL_HOURS_CLIENT_ID', 'LIBCAL_HOURS_CLIENT_SECRET',
                'LIBCAL_HOURS_LOCATION_IDS', 'LIBCAL_HOURS_URL',
                'LIBCAL_HOURS_OAUTH_URL'):
        env[key] = os.environ.get(key)
        if env[key] is None:
            raise RuntimeError(f'Must provide environment variable: {key}')

    return args, env


def authenticate(logger, oath_url, client_id, client_secret):
    """ Authenticate against LibCal using oAuth2 and return the access token. """

    # Authenticate via oAuth 2

    logger.info("Authenticating via oAuth2 ")

    data = {'grant_type': 'client_credentials'}

    token_response = requests.post(oath_url, data=data, allow_redirects=False, auth=(client_id, client_secret))

    logger.debug('Response Headers: ' + str(token_response.headers))
    logger.debug('Response Text: ' + token_response.text)

    tokens = json.loads(token_response.text)
    access_token = tokens['access_token']

    logger.debug("Access Token: " + access_token)

    return access_token


def get_text_time(time_str):
    """ Extract the time from the freeform text field. """

    hour = time_str[:-2]
    minute = '00'
    pm = time_str[-2:].lower() == 'pm'

    if (i := hour.find(":")) > 0:
        minute = hour[i + 1, i + 3]
        hour = hour[0:i]

    hour, minute = int(hour), int(minute)

    if pm:
        hour += 12

    return dt.time(hour=hour, minute=minute)


def get_times(logger, date, open_time_str, close_time_str, text):
    """ Get computed open_time, close_time, and open_minutes. """

    if open_time_str and close_time_str:
        # Get times directly from LibCal from and to values
        open_dt = dt.datetime.strptime(date + open_time_str, '%Y-%m-%d%I:%M%p')
        close_dt = dt.datetime.strptime(date + close_time_str, '%Y-%m-%d%I:%M%p')
        if close_time_str == "12:00AM":
            close_dt += dt.timedelta(days=1)

    elif text:
        # Extract times from the text value
        if (m := re.search(r'(\d{1,2}(?:\:\d{2})?(?:am|pm|AM|PM)) *[–-] *(\d{1,2}(?:\:\d{2})?(?:am|pm|AM|PM))', text)):
            open_dt = dt.datetime.combine(dt.date.fromisoformat(date), get_text_time(m[1]))
            close_dt = dt.datetime.combine(dt.date.fromisoformat(date), get_text_time(m[2]))

        else:
            raise RuntimeWarning("Unable to extract times from the text value")

    else:
        raise RuntimeWarning("Unable to extract times")

    minutes_open = int((close_dt - open_dt).total_seconds() / 60)

    return open_dt.strftime('%I:%M%p'), close_dt.strftime('%I:%M%p'), minutes_open


def write_csv(logger, hours_json):
    """ Write the CSV output. """

    csvwriter.writerow(['libcal_location_id', 'libcal_location_name', 'libcal_date',
                        'libcal_status', 'libcal_from', 'libcal_to', 'open_time',
                        'close_time', 'minutes_open', 'libcal_text', 'libcal_note'])

    # Iterate over locations
    for location in hours_json:
        lid = location['lid']
        name = location['name']

        # Iterate over dates
        # location['dates'] changes from dict to list when it is empty
        if 'dates' in location and len(location['dates']) > 0:
            for date, hours in sorted(location['dates'].items()):

                status = hours['status']

                text = hours['text'] if 'text' in hours else ''

                note = hours['note'] if 'note' in hours else ''

                if status == 'open':
                    # Iterate over hour ranges
                    if 'hours' in hours:
                        for hrange in hours['hours']:
                            try:
                                open_time, close_time, minutes_open = get_times(logger, date, hrange['from'], hrange['to'], '')
                            except Exception as e:
                                logger.warning(f'{e=} {lid=} {name=} {date=}, {hrange["from"]=}, {hrange["to"]=}, {text=}')
                                open_time, close_time, minutes_open = '', '', 0

                            csvwriter.writerow([lid, name, date, status, hrange['from'], hrange['to'], open_time,
                                                close_time, minutes_open, text, note])

                elif status == 'text':
                    try:
                        open_time, close_time, minutes_open = get_times(logger, date, '', '', text)
                    except Exception as e:
                        logger.warning(f'{e=} {lid=} {name=} {date=}, {text=}')
                        open_time, close_time, minutes_open = '', '', 0

                    csvwriter.writerow([lid, name, date, status, '', '', open_time,
                                        close_time, minutes_open, text, note])

                elif status == '24hours':
                    csvwriter.writerow([lid, name, date, status, '', '', '', '', 1440, text, note])

                elif status == 'closed':
                    csvwriter.writerow([lid, name, date, status, '', '', '', '', 0, text, note])

                else:
                    logger.warning(f'Skipping unknown {status=} for {lid=}, {name=}, {date=}')


if __name__ == '__main__':

    # Get input configuration
    args, env = get_configuration()

    oath_url = furl.furl(env['LIBCAL_HOURS_OAUTH_URL'])
    client_id = env['LIBCAL_HOURS_CLIENT_ID']
    client_secret = env['LIBCAL_HOURS_CLIENT_SECRET']

    hours_url = furl.furl(env['LIBCAL_HOURS_URL'])
    hours_url /= env['LIBCAL_HOURS_LOCATION_IDS']

    debug = os.environ.get('LIBCAL_HOURS_DEBUG') == 'true'

    # Setup logging
    logging.root.addHandler(logging.StreamHandler())

    logger = logging.getLogger('libcal-hours-export')

    if debug:
        logger.setLevel(logging.DEBUG)

        # from http.client import HTTPConnection
        # HTTPConnection.debuglevel = 1
        # requests_log = logging.getLogger("requests.packages.urllib3")
        # requests_log.setLevel(logging.DEBUG)
        # requests_log.propagate = True
    else:
        logger.setLevel(logging.INFO)

    # Authenticate
    access_token = authenticate(logger, oath_url, client_id, client_secret)

    # Get the hours data
    logger.info("Requesting Hours Data")

    request_headers = {'Authorization': 'Bearer ' + access_token}
    response = requests.get(hours_url, headers=request_headers, params={'from': args.from_date, 'to': args.to_date})

    logger.debug(response.text)

    hours_json = json.loads(response.text)

    if 'error' in hours_json:
        raise RuntimeError(f'Error returned from LibCal Hours API: {hours_json["error"]}')

    # Generate the CSV output
    logger.info("Generating CSV output")

    csvwriter = csv.writer(args.output_file)

    write_csv(logger, hours_json)
