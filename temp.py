from settings import conn_data
import mysql.connector

q = "insert into mail_folder_config (hospital, historical, current) values (%s, %s, %s);"
with mysql.connector.connect(**conn_data) as con:
    cur = con.cursor()
    with open('folders.csv') as fp:
        for i in fp:
            row = i.strip('\n').split(',')
            hosp, hist, curr = row[0], row[1].upper().replace(' ', ''), ''
            if 'X' in row:
                curr = hist.upper().replace(' ', '')
            cur.execute(q, (hosp, hist, curr))
    con.commit()