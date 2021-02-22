from mail_storage import mail_mover, mail_storage

def process_mails_in_range(hospital, fromtime, totime, deferred):
    #if deffred is X then read historical
    mail_storage(hospital, fromtime, totime, deferred)
    if deferred != 'X':
        mail_mover(hospital, deferred)

if __name__ == '__main__':
    for i in ['ils_agartala']:
        mail_storage(i, "25/01/2021 12:00:00", "31/01/2021 23:59:00", "X")