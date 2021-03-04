from mail_storage import mail_mover, mail_storage

def process_mails_in_range(hospital, fromtime, totime, deferred):
    #if deffred is X then read historical
    mail_storage(hospital, fromtime, totime, deferred)
    if deferred != 'X':
        mail_mover(hospital, deferred, process='settlement')

if __name__ == '__main__':
    for i in ['ils_agartala', 'ils_howrah', 'ils', 'ils_dumdum', 'noble', 'inamdar']:
        process_mails_in_range(i, "01/02/2021 00:00:01", "02/03/2021 00:00:01", "")