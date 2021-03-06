import time

import mysql.connector

from one import gmail_api
from settings import hospital_data, conn_data

while 1:
    deferred = 'X'
    with mysql.connector.connect(**conn_data) as con:
        cur = con.cursor()
        q = "select id, hospital from all_mails where attach_path = '' and process = 'settlement'"
        cur.execute(q)
        r = cur.fetchall()
        for i, j in r:
            if j in ['noble', 'inamdar']:
                gmail_api(hospital_data[j], j, i, deferred, process='settlement')
    time.sleep(60)
