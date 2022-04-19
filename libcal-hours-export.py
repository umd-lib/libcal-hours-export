import json
import logging
import os
import sys
import json
import urllib.parse
import requests
import argparse
import csv
from datetime import date, timedelta

import furl
from dotenv import load_dotenv

# Get hours for a single day from LibCal Hours and write to CSV for loading
# to the Data Warehouse.

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

    yesterday = (date.today() - timedelta(days=1)).isoformat()

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


def write_csv(logger, hours_json):
    """ Write the CSV output. """

    csvwriter.writerow(['id','name','date','status','minutes_open'])

    # Iterate over locations
    for location in hours_json:
        lid = location['lid']
        name = location['name']

        # Iterate over dates
        # location['dates'] changes from dict to list when it is empty
        if 'dates' in location and len(location['dates']) > 0:
            for date, hours in sorted(location['dates'].items()):

                status = hours['status']

                if status == 'open':
                    # Iterate over hour ranges
                    if 'hours' in hours:
                        for range in hours['hours']:
                            csvwriter.writerow([lid, name, date, status, 1])

                elif status == 'text':
                        csvwriter.writerow([lid, name, date, status, 2])

                elif status == '24hours':
                    csvwriter.writerow([lid, name, date, status, 1440])

                elif status == 'closed':
                    csvwriter.writerow([lid, name, date, status, 0])

                else:
                    logger.warn(f'Skipping unknown {status=} for {lid=}, {name=}, {date=}')


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

    logger = logging.getLogger('website-searcher')

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
