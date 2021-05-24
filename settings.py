import os
import re
import subprocess
from datetime import datetime
from random import randint

import mysql.connector
import pdfkit
from pathlib import Path
from dateutil.parser import parse
from pytz import timezone

timeout = 60 # seconds
mail_time = 15  # minutes
interval = 300  # seconds
conn_data = {'host': "database-iclaim.caq5osti8c47.ap-south-1.rds.amazonaws.com",
             'user': "admin",
             'password': "Welcome1!",
             'database': 'python'}

pdfconfig = pdfkit.configuration(wkhtmltopdf='/usr/bin/wkhtmltopdf')

hospital_data = {
    'inamdar': {
        "mode": "gmail_api",
        "data": {
            "json_file": 'data/credentials_inamdar.json',
            "token_file": "data/inamdar_token.pickle"
        }
    },
    'noble': {
        "mode": "gmail_api",
        "data": {
            "json_file": 'data/credentials_noble.json',
            "token_file": "data/noble_token.pickle"
        }
    },
    'ils': {
        "mode": "graph_api",
        "data": {
            "json_file": "data/credentials_ils.json",
            "email": 'ilsmediclaim@gptgroup.co.in'
        }
    },
    'ils_dumdum': {
        "mode": "graph_api",
        "data": {
            "json_file": "data/credentials_ils.json",
            "email": 'mediclaim.ils.dumdum@gptgroup.co.in'
        }
    },
    'ils_ho': {
        "mode": "graph_api",
        "data": {
            "json_file": "data/credentials_ils.json",
            "email": 'rgupta@gptgroup.co.in'
        }
    },
    'ils_agartala': {
        "mode": "imap_",
        "data": {
            "host": "gptgroup.icewarpcloud.in",
            "email": "billing.ils.agartala@gptgroup.co.in",
            "password": 'Gpt@2019'
        }
    },
    'ils_howrah': {
        "mode": "imap_",
        "data": {
            "host": "gptgroup.icewarpcloud.in",
            "email": "mediclaim.ils.howrah@gptgroup.co.in",
            "password": 'Gpt@2019'
        }
    },
}

for i in hospital_data:
    Path(os.path.join(i, "new_attach/")).mkdir(parents=True, exist_ok=True)

def remove_img_tags(data):
    p = re.compile(r'<img.*?/>')
    return p.sub('', data)

def html_to_pdf(src, dst):
    with open(src, 'r') as fp:
        data = fp.read()
    data = remove_img_tags(data)
    with open(src, 'w') as fp:
        fp.write(data)
    try:
        pdfkit.from_file(src, dst, configuration=pdfconfig)
    except:
        if os.path.exists(dst):
            pass
        else:
            raise Exception

def file_no(len):
    return str(randint((10 ** (len - 1)), 10 ** len)) + '_'

def get_parts(part):
    if 'parts' in part:
        for i in part['parts']:
            yield from get_parts(i)
    else:
        yield part

def clean_filename(filename):
    filename = filename.replace('.PDF', '.pdf')
    temp = ['/', ' ']
    for i in temp:
        filename = filename.replace(i, '')
    return filename


def file_blacklist(filename, **kwargs):
    fp = filename.strip('.')
    filename, file_extension = os.path.splitext(fp)
    ext = ['.pdf', '.htm', '.html', '.PDF', '.xlsx', '.xls']
    if file_extension not in ext:
        return False
    if 'email' in kwargs:
        if 'ECS' in fp and kwargs['email'] == 'paylink.india@citi.com':
            return False
        if 'ecs' in fp and kwargs['email'] == 'paylink.india@citi.com':
            return False
    if fp.find('ATT00001') != -1:
        return False
    # if (fp.find('MDI') != -1) and (fp.find('Query') == -1):
    #     return False
    if (fp.find('knee') != -1):
        return False
    if (fp.find('KYC') != -1):
        return False
    if fp.find('image') != -1:
        return False
    if (fp.find('DECLARATION') != -1):
        return False
    if (fp.find('Declaration') != -1):
        return False
    if (fp.find('notification') != -1):
        return False
    if (fp.find('CLAIMGENIEPOSTER') != -1):
        return False
    if (fp.find('declar') != -1):
        return False
    return True


def remove_img_tags(data):
    p = re.compile(r'<img.*?>')
    return p.sub('', data)


def format_date(date):
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
    return date


def save_attachment(msg, download_folder, **kwargs):
    """
    Given a message, save its attachments to the specified
    download folder (default is /tmp)

    return: file path to attachment
    """
    att_path = []
    flag = 0
    filename = None
    file_seq = file_no(4)
    for part in msg.walk():
        z = part.get_filename()
        z1 = part.get_content_type()
        if part.get_content_maintype() == 'multipart':
            continue
        if part.get('Content-Disposition') is None and part.get_content_type() != 'application/octet-stream':
            continue
        flag = 1
        filename = part.get_filename()
        if filename is not None and file_blacklist(filename, **kwargs):
            if not os.path.isfile(filename):
                fp = open(os.path.join(download_folder, file_seq + filename), 'wb')
                fp.write(part.get_payload(decode=True))
                fp.close()
                att_path.append(os.path.join(download_folder, file_seq + filename))
    if flag == 0 or filename is None or len(att_path) == 0:
        for part in msg.walk():
            if part.get_content_type() == 'text/plain':
                filename = 'text.txt'
                fp = open(os.path.join(download_folder, filename), 'wb')
                data = part.get_payload(decode=True)
                fp.write(data)
                fp.close()
                att_path = os.path.join(download_folder, filename)
            if part.get_content_type() == 'text/html':
                filename = 'text.html'
                fp = open(os.path.join(download_folder, filename), 'wb')
                data = part.get_payload(decode=True)
                fp.write(data)
                fp.close()
                with open(os.path.join(download_folder, filename), 'r', encoding='utf-8') as fp:
                    data = fp.read()
                data = remove_img_tags(data)
                with open(os.path.join(download_folder, filename), 'w', encoding='utf-8') as fp:
                    fp.write(data)
                att_path = os.path.join(download_folder, filename)
                pass
    return att_path

def if_exists_not_blank_attach(**kwargs):
    q = f"select * from all_mails where subject=%s and date=%s and id=%s and attach_path != '' limit 1"
    data = (kwargs['subject'], kwargs['date'], kwargs['id'])
    with mysql.connector.connect(**conn_data) as con:
        cur = con.cursor()
        cur.execute(q, data)
        result = cur.fetchone()
        if result is not None:
            return True
    return False

def if_exists(**kwargs):
    for i in kwargs:
        if kwargs[i] is None:
            return True
    q = f"select * from all_mails where subject=%s and date=%s and id=%s limit 1"
    data = (kwargs['subject'], kwargs['date'], kwargs['id'])
    with mysql.connector.connect(**conn_data) as con:
        cur = con.cursor()
        cur.execute(q, data)
        result = cur.fetchone()
        if result is not None:
            return True
    return False


def check_blank_attach(**kwargs):
    q = f"select attach_path from all_mails where subject=%s and date=%s and id=%s limit 1"
    data = (kwargs['subject'], kwargs['date'], kwargs['id'])
    with mysql.connector.connect(**conn_data) as con:
        cur = con.cursor()
        cur.execute(q, data)
        result = cur.fetchone()
        if result is not None:
            if not ls_cmd(result[0]):
                return True
    return False

def ls_cmd(filename):
    if os.path.exists(filename) and filename != "":
        return True
    return False