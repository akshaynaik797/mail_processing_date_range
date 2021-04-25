from common import settlement_mail_mover
from mail_storage import mail_mover, mail_storage


def process_mails_in_range(hospitals, fromtime, totime, deferred, **kwargs):
    #if deffred is X then read historical
    for hospital in hospitals:
        mail_storage(hospital, fromtime, totime, deferred, **kwargs)
        if 'process' in kwargs:
            if kwargs['process'] == 'settlement':
                settlement_mail_mover(deferred)
        if deferred != 'X':
            mail_mover(hospital, deferred)

if __name__ == '__main__':
    # for i in ['ils', 'ils_dumdum', 'inamdar', 'ils_agartala', 'ils_howrah', 'noble']:
    #     process_mails_in_range(i, "01/02/2021 00:00:01", "06/03/2021 00:00:01", "X", process='settlement')
    hospitals = ['ils', 'ils_dumdum', 'ils_agartala', 'ils_howrah', 'ils_ho']
    hospitals = ['noble']
    process_mails_in_range(hospitals, "24/04/2021 07:32:45", "24/04/2021 08:51:34", "")
    # mail_mover(hospitals[0], 'Z')
