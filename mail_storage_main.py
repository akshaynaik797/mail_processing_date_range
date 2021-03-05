from mail_storage import mail_mover, mail_storage, settlement_mail_mover


def process_mails_in_range(hospital, fromtime, totime, deferred, **kwargs):
    #if deffred is X then read historical
    mail_storage(hospital, fromtime, totime, deferred, **kwargs)
    if deferred != 'X':
        mail_mover(hospital, deferred, process='settlement')
    if 'process' in kwargs:
        if kwargs['process'] == 'settlement':
            settlement_mail_mover()

if __name__ == '__main__':
    for i in ['noble', 'ils_agartala', 'ils_howrah', 'ils', 'ils_dumdum', 'inamdar']:
        process_mails_in_range(i, "01/02/2021 00:00:01", "06/03/2021 00:00:01", "X", process='settlement')
