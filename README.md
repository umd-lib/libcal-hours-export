# libcal-hours-export

Python 3 application to export hours historical data using the LibCal API and export to a CSV file for import into a reporting database.

## Requires

* Python 3

## Running the application

```bash
# create a .env file (then manually update environment variables)
$ cp .env-template .env

# usage
$ python libcal-hours-export.py -h
usage: libcal-hours-export.py [-h] [-o OUTPUT_FILE] [-f FROM_DATE] [-t TO_DATE]

optional arguments:
  -h, --help            show this help message and exit
  -o OUTPUT_FILE, --output-file OUTPUT_FILE
                        CSV output file; default is stdout
  -f FROM_DATE, --from-date FROM_DATE
                        from date (YYYY-MM-DD), inclusive; default is yesterday
  -t TO_DATE, --to-date TO_DATE
                        to date (YYYY-MM-DD), inclusive; default is yesterday
```

## License

See the [LICENSE](LICENSE.txt) file for license rights and limitations.
