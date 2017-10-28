import json
import gspread as gs
from oauth2client.client import SignedJwtAssertionCredentials
from calendar import month_name


def upload_to_spread_sheet(p_name, spreadsheet, month, cells_time):  # cells_time= {cells_row: time}
    print("Syncing: \n" + str(cells_time) + "...")
    json_key = json.load(open('cred-ptc.json'))
    credentials = SignedJwtAssertionCredentials(json_key['client_email'],
                                                bytes(json_key['private_key'], 'utf-8'),
                                                json_key['scope'])
    print('Authenticating....')
    gc = gs.authorize(credentials)
    print('opening your sheet...')
    sheet = gc.open(spreadsheet)
    month_sheet = sheet.worksheet(month_name[month])
    rows_left = len(cells_time)
    for (row, value) in cells_time.items():
        print("Writing value in row number: " + row)
        print(str(rows_left) + " items left.")
        rows_left -= 1
        # update start
        month_sheet.update_acell('B' + row, '00:00:00')
        # update end
        month_sheet.update_acell('c' + row, value)
    print('finished writing')
