import base64
import email
import imaplib
import os.path
import pickle
import time
import signal
from pathlib import Path
from datetime import datetime, timedelta
import json
import logging
from shutil import copyfile

import pytz

import mysql.connector
import msal
import pdfkit
import requests
from dateutil.parser import parse
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from pytz import timezone
from email.header import decode_header


from make_log import log_exceptions, custom_log_data
from settings import mail_time, file_no, file_blacklist, conn_data, pdfconfig, format_date, save_attachment, \
    hospital_data, timeout, clean_filename, if_exists_not_blank_attach, check_blank_attach, if_exists


class TimeOutException(Exception):
    pass

def alarm_handler(signum, frame):
    print("ALARM signal received")
    raise TimeOutException()

def create_settlement_folder(hosp, ins, date, filepath):
    root = '../index/'
    dst = ""
    try:
        date = datetime.strptime(date, '%d/%m/%Y %H:%M:%S').strftime('%m%d%Y%H%M%S')
        today = datetime.now().strftime("%d_%m_%Y")
        folder = os.path.join(root, today, hosp, "letters", f"{ins}_{date}")
        dst = os.path.join(folder, os.path.split(filepath)[-1])
        Path(folder).mkdir(parents=True, exist_ok=True)
        copyfile(filepath, dst)
    except:
        log_exceptions(hosp=hosp, ins=ins, date=date, filepath=filepath)
    return os.path.abspath(dst)

def get_ins_process(subject, email):
    ins, process = "", ""
    q1 = "select IC from email_ids where email_ids=%s limit 1"
    q2 = "select subject, table_name from email_master where ic_id=%s"
    q3 = "select IC_name from IC_name where IC=%s limit 1"
    with mysql.connector.connect(**conn_data) as con:
        cur = con.cursor(buffered=True)
        cur.execute(q1, (email,))
        result = cur.fetchone()
        if result is not None:
            ic_id = result[0]
            cur.execute(q2, (ic_id,))
            result = cur.fetchall()
            for sub, pro in result:
                if 'Intimation No' in subject:
                    return ('big', 'settlement')
                if 'STAR HEALTH AND ALLIED INSUR04239' in subject:
                    return ('small', 'settlement')
                if sub in subject:
                    cur.execute(q3, (ic_id,))
                    result1 = cur.fetchone()
                    if result1 is not None:
                        return (result1[0], pro)
    return ins, process

def get_folders(hospital, deferred):
    result = []
    if deferred == 'X':
        q = "select historical from mail_folder_config where hospital=%s"
    else:
        q = "select current from mail_folder_config where hospital=%s and current != ''"
    with mysql.connector.connect(**conn_data) as con:
        cur = con.cursor()
        cur.execute(q, (hospital,))
        records = cur.fetchall()
        result = [i[0] for i in records]
    return result

def gmail_api(data, hosp, fromtime, totime, deferred, **kwargs):
    try:
        print(hosp)
        attach_path = os.path.join(hosp, 'new_attach/')
        token_file = data['data']['token_file']
        cred_file = data['data']['json_file']
        SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
        now = datetime.now()
        after = int((now - timedelta(minutes=mail_time)).timestamp())
        after = str(after)
        creds = None
        if os.path.exists(token_file):
            with open(token_file, 'rb') as token:
                creds = pickle.load(token)
        # If there are no (valid) credentials available, let the user log in.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    cred_file, SCOPES)
                creds = flow.run_local_server(port=0)
            # Save the credentials for the next run
            with open(token_file, 'wb') as token:
                pickle.dump(creds, token)

        service = build('gmail', 'v1', credentials=creds, cache_discovery=False)
        for folder in get_folders(hosp, deferred):
            with open('logs/folders.log', 'a') as tfp:
                print(str(datetime.now()), hosp, folder, sep=',', file=tfp)
            q = f"after:{fromtime} before:{totime}"
            results = service.users().messages()
            request = results.list(userId='me', labelIds=[folder], q=q)
            while request is not None:
                msg_col = request.execute()
                messages = msg_col.get('messages', [])
                custom_log_data(filename=hosp+'_mails', data=messages)
                if not messages:
                    pass
                    #print("No messages found.")
                else:
                    print("Message snippets:")
                    for message in messages[::-1]:
                        signal.signal(signal.SIGALRM, alarm_handler)
                        signal.alarm(timeout)
                        try:
                            id, subject, date, filename, sender = '', '', '', '', ''
                            msg = service.users().messages().get(userId='me', id=message['id']).execute()
                            id = msg['id']
                            for i in msg['payload']['headers']:
                                if i['name'] == 'Subject':
                                    subject = i['value']
                                if i['name'] == 'From':
                                    sender = i['value']
                                    sender = sender.split('<')[-1].replace('>', '')
                                if i['name'] == 'Date':
                                    date = i['value']
                                    date = date.split(',')[-1].strip()
                                    format = '%d %b %Y %H:%M:%S %z'
                                    if '(' in date:
                                        date = date.split('(')[0].strip()
                                    try:
                                        date = datetime.strptime(date, format)
                                    except:
                                        try:
                                            date = parse(date)
                                        except:
                                            with open('logs/date_err.log', 'a') as fp:
                                                print(date, file=fp)
                                            raise Exception
                                    date = date.astimezone(timezone('Asia/Kolkata')).replace(tzinfo=None)
                                    format1 = '%d/%m/%Y %H:%M:%S'
                                    date = date.strftime(format1)
                                if i['name'] == 'X-Failed-Recipients':
                                    with open(f'logs/{hosp}_fail_mails.log', 'a') as fp:
                                        print(id, subject, date, sep=',', file=fp)
                                    continue
                            if if_exists_not_blank_attach(subject=subject, date=date, id=id):
                                continue                                
                            ins, process = get_ins_process(subject, sender)
                            flag = 0
                            filename, download_attach = "", True
                            if 'process' in kwargs:
                                if kwargs['process'] == process:
                                    download_attach = True
                                else:
                                    download_attach = False
                            if 'insurer' in kwargs:
                                if kwargs['insurer'] == ins:
                                    download_attach = True
                                else:
                                    download_attach = False
                            if download_attach == True:
                                try:
                                    if 'parts' in msg['payload']:
                                        for j in msg['payload']['parts']:
                                            if 'attachmentId' in j['body']:
                                                temp = j['filename']
                                                if file_blacklist(temp, email=sender):
                                                    filename = clean_filename(temp)
                                                    filename = attach_path + file_no(4) + filename
                                                    filename = filename.replace(' ', '')
                                                    a_id = j['body']['attachmentId']
                                                    attachment = service.users().messages().attachments().get(userId='me', messageId=id,
                                                                                                              id=a_id).execute()
                                                    data = attachment['data']
                                                    with open(filename, 'wb') as fp:
                                                        fp.write(base64.urlsafe_b64decode(data))
                                                    print(filename)
                                                    flag = 1
                                    else:
                                        data = msg['payload']['body']['data']
                                        filename = attach_path + file_no(8) + '.pdf'
                                        with open(attach_path + 'temp.html', 'wb') as fp:
                                            fp.write(base64.urlsafe_b64decode(data))
                                        print(filename)
                                        pdfkit.from_file(attach_path + 'temp.html', filename, configuration=pdfconfig)
                                        flag = 1
                                    if flag == 0:
                                        if 'data' in msg['payload']['parts'][0]['body']:
                                            data = msg['payload']['parts'][0]['parts'][-1]['body']['data']
                                            filename = attach_path + file_no(8) + '.pdf'
                                            with open(attach_path + 'temp.html', 'wb') as fp:
                                                fp.write(base64.urlsafe_b64decode(data))
                                            print(filename)
                                            pdfkit.from_file(attach_path + 'temp.html', filename,
                                                             configuration=pdfconfig)
                                            flag = 1
                                        elif 'data' in msg['payload']['parts'][-1]['body']:
                                            data = msg['payload']['parts'][-1]['body']['data']
                                            filename = attach_path + file_no(8) + '.pdf'
                                            with open(attach_path + 'temp.html', 'wb') as fp:
                                                fp.write(base64.urlsafe_b64decode(data))
                                            print(filename)
                                            pdfkit.from_file(attach_path + 'temp.html', filename, configuration=pdfconfig)
                                            flag = 1
                                        else:
                                            if 'data' in msg['payload']['parts'][0]['parts'][-1]['body']:
                                                data = msg['payload']['parts'][0]['parts'][-1]['body']['data']
                                                filename = attach_path + file_no(8) + '.pdf'
                                                with open(attach_path + 'temp.html', 'wb') as fp:
                                                    fp.write(base64.urlsafe_b64decode(data))
                                                print(filename)
                                                pdfkit.from_file(attach_path + 'temp.html', filename, configuration=pdfconfig)
                                                flag = 1
                                            else:
                                                data = msg['payload']['parts'][0]['parts'][-1]['parts'][-1]['body']['data']
                                                filename = attach_path + file_no(8) + '.pdf'
                                                with open(attach_path + 'temp.html', 'wb') as fp:
                                                    fp.write(base64.urlsafe_b64decode(data))
                                                print(filename)
                                                pdfkit.from_file(attach_path + 'temp.html', filename, configuration=pdfconfig)
                                                flag = 1
                                    if process == 'settlement':
                                        filename = create_settlement_folder(hosp, ins, date, filename)
                                    filename = os.path.abspath(filename)
                                except:
                                    pass
                            if check_blank_attach(subject=subject, date=date, id=id):
                                q = "update all_mails set attach_path=%s where subject=%s and date=%s and id=%s"
                                data = (filename, subject, date, id)
                            if not if_exists(subject=subject, date=date, id=id):
                                q = f"insert into all_mails (`id`,`subject`,`date`,`sys_time`,`attach_path`,`completed`,`sender`,`hospital`,`insurer`,`process`,`deferred`, `mail_folder`) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
                                data = (id, subject, date, str(datetime.now()), filename, '', sender, hosp, ins, process, deferred, folder)
                            with mysql.connector.connect(**conn_data) as con:
                                cur = con.cursor()
                                cur.execute(q, data)
                                con.commit()
                        except:
                            log_exceptions(id=id, hosp=hosp)
                        signal.alarm(0)
                request = results.list_next(request, msg_col)

    except:
        log_exceptions()

def graph_api(data, hosp, fromtime, totime, deferred, **kwargs):
    try:
        print(hosp)
        attachfile_path = os.path.join(hosp, 'new_attach/')
        email = data['data']['email']
        cred_file = data['data']['json_file']
        config = json.load(open(cred_file))
        app = msal.ConfidentialClientApplication(
            config["client_id"], authority=config["authority"],
            client_credential=config["secret"], )
        result = None
        result = app.acquire_token_silent(config["scope"], account=None)
        if not result:
            logging.info("No suitable token exists in cache. Let's get a new one from AAD.")
            result = app.acquire_token_for_client(scopes=config["scope"])
        after = datetime.now() - timedelta(minutes=mail_time)
        after = after.astimezone(pytz.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if "access_token" in result:
            flag = 0
            for folder in get_folders(hosp, deferred):
                with open('logs/folders.log', 'a') as tfp:
                    print(str(datetime.now()), hosp, folder, sep=',', file=tfp)
                flag = 0
                while 1:
                    if flag == 0:
                        query = f"https://graph.microsoft.com/v1.0/users/{email}" \
                                f"/mailFolders/{folder}/messages?$filter=(receivedDateTime ge {fromtime} and receivedDateTime lt {totime})"
                    flag = 1
                    # print(datetime.now(), ' quering graph api')
                    graph_data2 = requests.get(query,
                                               headers={'Authorization': 'Bearer ' + result['access_token']}, ).json()
                    if 'value' in graph_data2:
                        for i in graph_data2['value']:
                            # print(datetime.now(), ' got mails')
                            signal.signal(signal.SIGALRM, alarm_handler)
                            signal.alarm(timeout)
                            try:
                                # print(datetime.now(), ' saving mail in db')
                                date, subject, attach_path, sender = '', '', '', ''
                                format = "%Y-%m-%dT%H:%M:%SZ"
                                b = datetime.strptime(i['receivedDateTime'], format).replace(tzinfo=pytz.utc).astimezone(
                                    pytz.timezone('Asia/Kolkata')).replace(
                                    tzinfo=None)
                                b = b.strftime('%d/%m/%Y %H:%M:%S')
                                date, subject, sender = b, i['subject'], i['sender']['emailAddress']['address']
                                ins, process = get_ins_process(subject, sender)
                                attach_path, download_attach = "", True
                                if if_exists_not_blank_attach(subject=subject, date=date, id=i['id']):
                                    continue
                                if 'process' in kwargs:
                                    if kwargs['process'] == process:
                                        download_attach = True
                                    else:
                                        download_attach = False
                                if 'insurer' in kwargs:
                                    if kwargs['insurer'] == ins:
                                        download_attach = True
                                    else:
                                        download_attach = False
                                if download_attach == True:
                                    flag = 0
                                    try:
                                        if i['hasAttachments'] is True:
                                            q = f"https://graph.microsoft.com/v1.0/users/{email}/mailFolders/inbox/messages/{i['id']}/attachments"
                                            attach_data = requests.get(q,
                                                                       headers={'Authorization': 'Bearer ' + result[
                                                                           'access_token']}, ).json()
                                            for j in attach_data['value']:
                                                if '@odata.mediaContentType' in j:
                                                    j['name'] = j['name'].replace('.PDF', '.pdf')
                                                    # print(j['@odata.mediaContentType'], j['name'])
                                                    if file_blacklist(j['name'], email=sender):
                                                        j['name'] = file_no(4) + j['name']
                                                        with open(os.path.join(attachfile_path, j['name']), 'w+b') as fp:
                                                            fp.write(base64.b64decode(j['contentBytes']))
                                                        attach_path = os.path.join(attachfile_path, j['name'])
                                                        flag = 1
                                        if flag == 0:
                                            filename = attachfile_path + file_no(8) + '.pdf'
                                            if i['body']['contentType'] == 'html':
                                                with open(attachfile_path + 'temp.html', 'w') as fp:
                                                    fp.write(i['body']['content'])
                                                pdfkit.from_file(attachfile_path +'temp.html', filename, configuration=pdfconfig)
                                                attach_path = filename
                                            elif i['body']['contentType'] == 'text':
                                                with open(attachfile_path + 'temp.text', 'w') as fp:
                                                    fp.write(i['body']['content'])
                                                pdfkit.from_file(attachfile_path + 'temp.text', filename, configuration=pdfconfig)
                                                attach_path = filename
                                        # print(date, subject, attach_path, sender, sep='|')
                                        if process == 'settlement':
                                            attach_path = create_settlement_folder(hosp, ins, date, attach_path)
                                        attach_path = os.path.abspath(attach_path)
                                    except:
                                        pass
                                if check_blank_attach(subject=subject, date=date, id=i['id']):
                                    q = "update all_mails set attach_path=%s where subject=%s and date=%s and id=%s"
                                    data = (attach_path, subject, date, i['id'])
                                if not if_exists(subject=subject, date=date, id=i['id']):
                                    q = f"insert into all_mails (`id`,`subject`,`date`,`sys_time`,`attach_path`,`completed`,`sender`,`hospital`,`insurer`,`process`,`deferred`, `mail_folder`) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
                                    data = (
                                    i['id'], subject, date, str(datetime.now()), attach_path, '', sender, hosp, ins, process,
                                    deferred, folder)
                                with mysql.connector.connect(**conn_data) as con:
                                    cur = con.cursor()
                                    cur.execute(q, data)
                                    con.commit()
                            except:
                                log_exceptions(mid=i['id'], hosp=hosp)
                            signal.alarm(0)
                    else:
                        with open('logs/query.log', 'a') as fp:
                            print(query, file=fp)
                    if '@odata.nextLink' in graph_data2:
                        query = graph_data2['@odata.nextLink']
                    else:
                        break
    except:
        log_exceptions(hosp=hosp)

def imap_(data, hosp, fromtime, totime, deferred, **kwargs):
    try:
        print(hosp)
        attachfile_path = os.path.join(hosp, 'new_attach/')
        server, email_id, password = data['data']['host'], data['data']['email'], data['data']['password']
        today = datetime.now().strftime('%d-%b-%Y')
        imap_server = imaplib.IMAP4_SSL(host=server)
        table = f'{hosp}_mails'
        imap_server.login(email_id, password)
        # for i in imap_server.list()[1]:
        #     l = i.decode().split(' "/" ')
        #     print(l[0] + " = " + l[1])
        for folder in get_folders(hosp, deferred):
            with open('logs/folders.log', 'a') as tfp:
                print(str(datetime.now()), hosp, folder, sep=',', file=tfp)
            imap_server.select()
            # imap_server.select(readonly=True, mailbox=f'"{folder}"')  # Default is `INBOX`
            # Find all emails in inbox and print out the raw email data
            # _, message_numbers_raw = imap_server.search(None, 'ALL')
            _, message_numbers_raw = imap_server.search(None, f'(SINCE "{fromtime}" BEFORE "{totime}")')
            for message_number in message_numbers_raw[0].split():
                signal.signal(signal.SIGALRM, alarm_handler)
                signal.alarm(timeout)
                try:
                    _, msg = imap_server.fetch(message_number, '(RFC822)')
                    message = email.message_from_bytes(msg[0][1])
                    sender = message['from']
                    sender = sender.split('<')[-1].replace('>', '')
                    date = format_date(message['Date'])
                    subject = message['Subject'].strip()
                    if '?' in subject:
                        try:
                            subject = decode_header(subject)[0][0].decode("utf-8")
                        except:
                            log_exceptions(subject=subject, hosp=hosp)
                            pass
                    for i in ['\r', '\n', '\t']:
                        subject = subject.replace(i, '').strip()
                    ins, process = get_ins_process(subject, sender)
                    mid = int(message_number)
                    filename, download_attach = "", True
                    if if_exists_not_blank_attach(subject=subject, date=date, id=mid):
                        continue
                    if 'process' in kwargs:
                        if kwargs['process'] == process:
                            download_attach = True
                        else:
                            download_attach = False
                    if 'insurer' in kwargs:
                        if kwargs['insurer'] == ins:
                            download_attach = True
                        else:
                            download_attach = False
                    if download_attach == True:
                        try:
                            a = save_attachment(message, attachfile_path, email=sender)
                            if not isinstance(a, list):
                                filename = attachfile_path + file_no(8) + '.pdf'
                                pdfkit.from_file(a, filename, configuration=pdfconfig)
                            else:
                                filename = a[-1]
                            if process == 'settlement':
                                filename = create_settlement_folder(hosp, ins, date, filename)
                            filename = os.path.abspath(filename)
                        except:
                            pass
                    if check_blank_attach(subject=subject, date=date, id=mid):
                        q = "update all_mails set attach_path=%s where subject=%s and date=%s and id=%s"
                        data = (filename, subject, date, mid)
                    if not if_exists(subject=subject, date=date, id=mid):
                        q = f"insert into all_mails (`id`,`subject`,`date`,`sys_time`,`attach_path`,`completed`,`sender`,`hospital`,`insurer`,`process`,`deferred`, `mail_folder`) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
                        data = (
                        mid, subject, date, str(datetime.now()), filename, '', sender, hosp, ins, process, deferred,
                        folder)
                    with mysql.connector.connect(**conn_data) as con:
                        cur = con.cursor()
                        cur.execute(q, data)
                        con.commit()
                    # with mysql.connector.connect(**conn_data) as con:
                    #     cur = con.cursor()
                    #     q = f"insert into all_mails (`id`,`subject`,`date`,`sys_time`,`attach_path`,`completed`,`sender`,`hospital`,`insurer`,`process`,`deferred`, `mail_folder`) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
                    #     data = (mid, subject, date, str(datetime.now()), os.path.abspath(filename), '', sender, hosp, ins, process, deferred, folder)
                    #     cur.execute(q, data)
                    #     con.commit()
                    #     with open(f'logs/{hosp}_mails_in_db.log', 'a') as fp:
                    #         print(datetime.now(), subject, date, sender, filename, sep=',', file=fp)
                except:
                    log_exceptions(subject=subject, date=date, hosp=hosp)
                signal.alarm(0)
    except:
        log_exceptions(hosp=hosp)

def mail_mover(hospital, deferred):
    fields = ("id","subject","date","sys_time","attach_path","completed","sender","hospital","insurer","process","deferred","sno")
    q = "select * from all_mails where deferred=%s and hospital=%s "
    params = [deferred, hospital]
    # if 'process' in kwargs:
    #     q = q + ' and process=%s'
    #     params.append(kwargs['process'])
    # if 'insurer' in kwargs:
    #     q = q + ' and insurer=%s'
    #     params.append(kwargs['insurer'])
    records = []
    folder = f"../{hospital}/new_attach"
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
            dst = os.path.join(folder, os.path.split(i["attach_path"])[-1])
            Path(folder).mkdir(parents=True, exist_ok=True)
            copyfile(i["attach_path"], dst)
            # if 'process' in kwargs:
            #     if kwargs['process'] == 'settlement':
            #         cur.execute('select * from settlement_mails where `id`=%s and `subject`=%s and `date`=%s limit 1', (i["id"], i["subject"], i["date"]))
            #         temp_r = cur.fetchone()
            #         if temp_r is None or os.path.exists(os.path.abspath(i["attach_path"])) is False:
            #             q = 'INSERT INTO settlement_mails (`id`,`subject`,`date`,`sys_time`,`attach_path`,`completed`,`sender`,`folder`,`process`,`hospital`) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);'
            #             data = (i["id"], i["subject"], i["date"], str(datetime.now()), os.path.abspath(i["attach_path"]), i["completed"], i["sender"], 'date_range', 'settlement', hospital)
            #             cur.execute(q, data)
            # else:
            #     q = f"INSERT INTO {hospital}_mails (`id`,`subject`,`date`,`sys_time`,`attach_path`,`completed`,`sender`) values (%s, %s, %s, %s, %s, %s, %s)"
            #     data = (i["id"], i["subject"], i["date"], str(datetime.now()), os.path.abspath(dst), i["completed"], i["sender"])
            #     cur.execute(q, data)
            cur.execute(f'select * from {hospital}_mails where `id`=%s and `subject`=%s and `date`=%s limit 1',
                        (i["id"], i["subject"], i["date"]))
            temp_r = cur.fetchone()
            if temp_r is None:
                q = f"INSERT INTO {hospital}_mails (`id`,`subject`,`date`,`sys_time`,`attach_path`,`completed`,`sender`) values (%s, %s, %s, %s, %s, %s, %s)"
                data = (i["id"], i["subject"], i["date"], str(datetime.now()), os.path.abspath(dst), i["completed"], i["sender"])
                cur.execute(q, data)
                q = "update all_mails set deferred='MOVED' where sno=%s"
                cur.execute(q, (i['sno'],))
            else:
                q = "update all_mails set deferred='EXISTS' where sno=%s"
                cur.execute(q, (i['sno'],))
            con.commit()


def settlement_mail_mover(deferred):
    fields = ("id","subject","date","sys_time","attach_path","completed","sender","hospital","insurer","process","deferred","sno")
    q = "select * from all_mails where process='settlement' and deferred=%s and attach_path != ''"
    records = []
    with mysql.connector.connect(**conn_data) as con:
        cur = con.cursor()
        cur.execute(q, (deferred,))
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
                    cur.execute('select * from settlement_mails where `id`=%s and `subject`=%s and `date`=%s and attach_path="" limit 1', (i["id"], i["subject"], i["date"]))
                    temp_r = cur.fetchone()
                    if temp_r is not None:
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


def mail_storage(hospital, fromtime, totime, deferred, **kwargs):
    for hosp, data in hospital_data.items():
        if data['mode'] == 'gmail_api' and hosp == hospital:
            print(hosp)
            fromtime = int(datetime.strptime(fromtime, '%d/%m/%Y %H:%M:%S').timestamp())
            totime = int(datetime.strptime(totime, '%d/%m/%Y %H:%M:%S').timestamp())
            gmail_api(data, hosp, fromtime, totime, deferred, **kwargs)
        elif data['mode'] == 'graph_api' and hosp == hospital:
            print(hosp) #.astimezone(pytz.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            fromtime = datetime.strptime(fromtime, '%d/%m/%Y %H:%M:%S').astimezone(pytz.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            totime = datetime.strptime(totime, '%d/%m/%Y %H:%M:%S').astimezone(pytz.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            graph_api(data, hosp, fromtime, totime, deferred, **kwargs)
        elif data['mode'] == 'imap_' and hosp == hospital:
            print(hosp)
            fromtime = datetime.strptime(fromtime, '%d/%m/%Y %H:%M:%S').strftime('%d-%b-%Y')
            totime = datetime.strptime(totime, '%d/%m/%Y %H:%M:%S').strftime('%d-%b-%Y')
            imap_(data, hosp, fromtime, totime, deferred, **kwargs)

if __name__ == '__main__':
    create_settlement_folder('a', 'b', '01/01/2021 12:12:12', 'a')
    pass