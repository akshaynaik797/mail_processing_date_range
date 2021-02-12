import base64
import email
import imaplib
import os.path
import pickle
import time
from datetime import datetime, timedelta
import json
import logging
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
from settings import mail_time, file_no, file_blacklist, conn_data, pdfconfig, format_date, save_attachment

all_mails_fields = ("id","subject","date","sys_time","attach_path","completed","sender","hospital","insurer","process","deferred")

def get_ins_process(subject, email):
    ins, process = "", ""
    q1 = "select IC from email_ids where email_ids=%s"
    q2 = "select subject, table_name from email_master where ic_id=%s"
    q3 = "select IC_name from IC_name where IC=%s"
    with mysql.connector.connect(**conn_data) as con:
        cur = con.cursor()
        cur.execute(q1, (email,))
        result =cur.fetchone()
        if result is not None:
            ic_id = result[0]
            cur.execute(q2, (ic_id,))
            result = cur.fetchall()
            for sub, pro in result:
                if sub in subject:
                    cur.execute(q3, (ic_id,))
                    result1 = cur.fetchone()
                    if result1 is not None:
                        return (result1[0], pro)
    return ins, process

def get_folders(hospital):
    result = []
    q = "select name from mail_folder_config where active=1 and hospital=%s"
    with mysql.connector.connect(**conn_data) as con:
        cur = con.cursor()
        cur.execute(q, (hospital,))
        records = cur.fetchall()
        result = [i[0] for i in records]
    return result

def if_exists(**kwargs):
    if 'id' in kwargs:
        q = f"select * from {kwargs['hosp']}_mails where id=%s limit 1"
        data = (kwargs['id'],)
    elif 'subject' in kwargs and 'date' in kwargs:
        q = f"select * from {kwargs['hosp']}_mails where subject=%s and date=%s limit 1"
        data = (kwargs['subject'], kwargs['date'])
    with mysql.connector.connect(**conn_data) as con:
        cur = con.cursor()
        cur.execute(q, data)
        result = cur.fetchone()
        if result is None:
            return False
    return True

def gmail_api(data, hosp, fromtime, totime, deferred):
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
        #############
        # results = service.users().labels().list(userId='me').execute()
        # labels = results.get('labels', [])
        #############
        for folder in get_folders(hosp):
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
                            ins, process = get_ins_process(subject, sender)
                            custom_log_data(filename=hosp + '_mails', data=[id, subject, date, filename, sender])
                            flag = 0
                            if 'parts' in msg['payload']:
                                for j in msg['payload']['parts']:
                                    if 'attachmentId' in j['body']:
                                        filename = j['filename']
                                        filename = filename.replace('.PDF', '.pdf')
                                        filename = attach_path + file_no(4) + filename
                                        if file_blacklist(filename):
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
                                if 'data' in msg['payload']['parts'][-1]['body']:
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
                            with mysql.connector.connect(**conn_data) as con:
                                cur = con.cursor()
                                q = f"insert into {hosp}_mails (`id`,`subject`,`date`,`sys_time`,`attach_path`,`completed`, `sender`) VALUES (%s, %s, %s, %s, %s, %s, %s)"
                                data = (id, subject, date, str(datetime.now()), os.path.abspath(filename), '', sender)
                                cur.execute(q, data)
                                con.commit()
                        except:
                            log_exceptions(id=id, hosp=hosp)
                request = results.list_next(request, msg_col)

    except:
        log_exceptions()

def graph_api(data, hosp, fromtime, totime, deferred):
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
            for folder in get_folders(hosp):
                while 1:
                    if flag == 0:
                        query = f"https://graph.microsoft.com/v1.0/users/{email}" \
                                f"/mailFolders/{folder}/messages?$filter=(receivedDateTime ge {fromtime} and receivedDateTime lt {totime})"
                    flag = 1
                    print(datetime.now(), ' quering graph api')
                    ###################
                    # query = f"https://graph.microsoft.com/v1.0/users/{email}/mailFolders/JUNKEMAIL"
                    ###################
                    graph_data2 = requests.get(query,
                                               headers={'Authorization': 'Bearer ' + result['access_token']}, ).json()
                    if 'value' in graph_data2:
                        for i in graph_data2['value']:
                            print(datetime.now(), ' got mails')
                            try:
                                print(datetime.now(), ' saving mail in db')
                                date, subject, attach_path, sender = '', '', '', ''
                                format = "%Y-%m-%dT%H:%M:%SZ"
                                b = datetime.strptime(i['receivedDateTime'], format).replace(tzinfo=pytz.utc).astimezone(
                                    pytz.timezone('Asia/Kolkata')).replace(
                                    tzinfo=None)
                                b = b.strftime('%d/%m/%Y %H:%M:%S')
                                date, subject, sender = b, i['subject'], i['sender']['emailAddress']['address']
                                ins, process = get_ins_process(subject, sender)
                                # print(i['receivedDateTime'], b, i['subject'])
                                # print(i['sender']['emailAddress']['address'])
                                if i['hasAttachments'] is True:
                                    q = f"https://graph.microsoft.com/v1.0/users/{email}/mailFolders/inbox/messages/{i['id']}/attachments"
                                    attach_data = requests.get(q,
                                                               headers={'Authorization': 'Bearer ' + result[
                                                                   'access_token']}, ).json()
                                    for j in attach_data['value']:
                                        if '@odata.mediaContentType' in j:
                                            j['name'] = j['name'].replace('.PDF', '.pdf')
                                            # print(j['@odata.mediaContentType'], j['name'])
                                            if file_blacklist(j['name']):
                                                j['name'] = file_no(4) + j['name']
                                                with open(os.path.join(attachfile_path, j['name']), 'w+b') as fp:
                                                    fp.write(base64.b64decode(j['contentBytes']))
                                                attach_path = os.path.join(attachfile_path, j['name'])
                                else:
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
                                with mysql.connector.connect(**conn_data) as con:
                                    cur = con.cursor()
                                    q = f"insert into {hosp}_mails (`id`,`subject`,`date`,`sys_time`,`attach_path`,`completed`, `sender`) VALUES (%s, %s, %s, %s, %s, %s, %s)"
                                    data = (
                                    i['id'], subject, date, str(datetime.now()), os.path.abspath(attach_path), '', sender)
                                    cur.execute(q, data)
                                    con.commit()
                                    print(datetime.now(), ' saved mail in db')
                                    print(date, subject, attach_path, sender, sep='|')
                            except:
                                log_exceptions(mid=i['id'], hosp=hosp)
                    else:
                        with open('logs/query.log', 'a') as fp:
                            print(query, file=fp)
                    if '@odata.nextLink' in graph_data2:
                        query = graph_data2['@odata.nextLink']
                    else:
                        break
    except:
        log_exceptions(hosp=hosp)

def imap_(data, hosp, fromtime, totime, deferred):
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
        for folder in get_folders(hosp):
            imap_server.select(readonly=True, mailbox=f'"{folder}"')  # Default is `INBOX`
            # Find all emails in inbox and print out the raw email data
            # _, message_numbers_raw = imap_server.search(None, 'ALL')
            _, message_numbers_raw = imap_server.search(None, f'(SINCE "{fromtime}" BEFORE "{totime}")')
            for message_number in message_numbers_raw[0].split():
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
                    a = save_attachment(message, attachfile_path)
                    if not isinstance(a, list):
                        filename = attachfile_path + file_no(8) + '.pdf'
                        pdfkit.from_file(a, filename, configuration=pdfconfig)
                    else:
                        filename = a[-1]
                    with open(f'logs/{hosp}_mails.log', 'a') as fp:
                        print(datetime.now(), subject, date, sender, filename, sep=',', file=fp)
                    with mysql.connector.connect(**conn_data) as con:
                        cur = con.cursor()
                        q = f"insert into {table} (`id`,`subject`,`date`,`sys_time`,`attach_path`,`completed`, `sender`) VALUES (%s, %s, %s, %s, %s, %s, %s)"
                        data = (mid, subject, date, str(datetime.now()), os.path.abspath(filename), '', sender)
                        cur.execute(q, data)
                        con.commit()
                        with open(f'logs/{hosp}_mails_in_db.log', 'a') as fp:
                            print(datetime.now(), subject, date, sender, filename, sep=',', file=fp)
                except:
                    log_exceptions(subject=subject, date=date, hosp=hosp)
    except:
        log_exceptions(hosp=hosp)