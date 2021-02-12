from datetime import datetime

import pytz

from settings import hospital_data, pdfconfig, file_no, file_blacklist, conn_data, interval
from mail_storage import gmail_api, graph_api, imap_, get_folders

def mail_storage(hospital, fromtime, totime, process, deferred):
    for hosp, data in hospital_data.items():
        if data['mode'] == 'gmail_api' and hosp == hospital:
            print(hosp)
            fromtime = int(datetime.strptime(fromtime, '%d/%m/%Y %H:%M:%S').timestamp())
            totime = int(datetime.strptime(totime, '%d/%m/%Y %H:%M:%S').timestamp())
            gmail_api(data, hosp, fromtime, totime)
        elif data['mode'] == 'graph_api' and hosp == hospital:
            print(hosp) #.astimezone(pytz.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            fromtime = datetime.strptime(fromtime, '%d/%m/%Y %H:%M:%S').astimezone(pytz.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            totime = datetime.strptime(totime, '%d/%m/%Y %H:%M:%S').astimezone(pytz.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            graph_api(data, hosp, fromtime, totime)
        elif data['mode'] == 'imap_' and hosp == hospital:
            print(hosp)
            fromtime = datetime.strptime(fromtime, '%d/%m/%Y %H:%M:%S').strftime('%d-%b-%Y')
            totime = datetime.strptime(totime, '%d/%m/%Y %H:%M:%S').strftime('%d-%b-%Y')
            imap_(data, hosp, fromtime, totime)

if __name__ == '__main__':
    mail_storage('ils_howrah', '10/02/2021 12:00:00', '12/02/2021 12:00:00', 'X', 'X')