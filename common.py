import base64
import os
from datetime import datetime
import re

import mysql.connector
from html2text import html2text

from make_log import log_exceptions
from settings import conn_data, ls_cmd, get_parts


def get_utr_date_from_big(msg, **kwargs):
    try:
        def get_info(data):
            data_dict = {'utr': "", 'date': ""}
            r_list = [r"(?<=:).*(?=Date)", r"(?<=Date:).*(?=\s+Thanking you)"]
            for i, j in zip(r_list, data_dict):
                if tmp := re.compile(i).search(data):
                    tmp = tmp.group().strip()
                    data_dict[j] = tmp
            return data_dict

        data = ""
        if kwargs['mode'] == 'graph_api':
            if msg['body']['contentType'] == 'html':
                data = msg['body']['content']
                data = html2text(data)
            elif msg['body']['contentType'] == 'text':
                data = msg['body']['content']


        if kwargs['mode'] == "gmail_api":
            file_list = [i for i in get_parts(msg['payload'])]
            for j in file_list:
                if j['filename'] == '' and j['mimeType'] == 'text/html':
                    data = j['body']['data']
                    data = base64.urlsafe_b64decode(data).decode()
                    if j['mimeType'] == 'text/html':
                        data = html2text(data)

        if kwargs['mode'] == 'imap_':
            for part in msg.walk():
                if part.get_content_type() == 'text/plain':
                    data = part.get_payload(decode=True)
                if part.get_content_type() == 'text/html':
                    data = part.get_payload(decode=True)
                    data = html2text(data)

        data_dict = get_info(data)

        q1 = "select * from ins_big_utr_date where `id`=%s and hosp=%s and utr=%s limit 1"
        params1 = [kwargs['id'], kwargs['hosp'], data_dict['utr']]
        q = "insert into ins_big_utr_date (`id`, `hosp`, `utr`, `date`) values (%s, %s, %s, %s);"
        params = [kwargs['id'], kwargs['hosp'], data_dict['utr'], data_dict['date']]
        with mysql.connector.connect(**conn_data) as con:
            cur = con.cursor()
            cur.execute(q1, params1)
            r = cur.fetchone()
            if r is None:
                cur.execute(q, params)
                con.commit()
    except:
        log_exceptions(kwargs=kwargs)

def settlement_mail_mover(deferred, **kwargs):
    fields = ("id","subject","date","sys_time","attach_path","completed","sender","hospital","insurer","process","deferred","sno")
    if 'id' in kwargs:
        q = "select * from all_mails where id=%s and process='settlement' and attach_path != ''"
        params = (kwargs['id'],)
    else:
        q = "select * from all_mails where process='settlement' and deferred=%s and attach_path != ''"
        params = (deferred,)

    records = []
    with mysql.connector.connect(**conn_data) as con:
        cur = con.cursor()
        cur.execute(q, params)
        result = cur.fetchall()
        for i in result:
            temp = {}
            for key, value in zip(fields, i):
                temp[key] = value
            records.append(temp)
    with mysql.connector.connect(**conn_data) as con:
        cur = con.cursor()
        for i in records:
            try:
                cur.execute('select * from settlement_mails where `id`=%s and `subject`=%s and `date`=%s limit 1', (i["id"], i["subject"], i["date"]))
                temp_r = cur.fetchone()
                if temp_r is None:
                    q = 'INSERT INTO settlement_mails (`id`,`subject`,`date`,`sys_time`,`attach_path`,`completed`,`sender`,`folder`,`process`,`hospital`) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);'
                    data = (i["id"], i["subject"], i["date"], str(datetime.now()), os.path.abspath(i["attach_path"]), i["completed"], i["sender"], 'date_range', 'settlement', i['hospital'])
                    cur.execute(q, data)
                    q = "update all_mails set deferred='MOVED' where sno=%s"
                    cur.execute(q, (i['sno'],))
                else:
                    cur.execute('select attach_path from settlement_mails where `id`=%s and `subject`=%s and `date`=%s limit 1', (i["id"], i["subject"], i["date"]))
                    temp_r = cur.fetchone()
                    if temp_r is not None:
                        if not ls_cmd(temp_r[0]):
                            q = "update settlement_mails set attach_path=%s where `id`=%s and `subject`=%s and `date`=%s"
                            data = (i["attach_path"], i["id"], i["subject"], i["date"])
                            cur.execute(q, data)
                            q = "update all_mails set deferred='FIXED_ATTACH' where sno=%s"
                            cur.execute(q, (i['sno'],))
                    else:
                        q = "update all_mails set deferred='EXISTS' where sno=%s"
                        cur.execute(q, (i['sno'],))
                con.commit()
            except:
                log_exceptions(i=i)
