from temp import mail_mover, mail_storage

def process_mails_in_range(hospital, fromtime, totime, deferred):
    mail_storage(hospital, fromtime, totime, deferred)
    if deferred != 'X':
        mail_mover(hospital, deferred)

if __name__ == '__main__':
    mail_storage("ils_agartala", "01/02/2021 12:00:00", "02/02/2021 12:00:00", "X")