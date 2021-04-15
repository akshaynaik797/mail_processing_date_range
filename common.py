import os
from datetime import datetime

import mysql.connector

from make_log import log_exceptions
from settings import conn_data, ls_cmd


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