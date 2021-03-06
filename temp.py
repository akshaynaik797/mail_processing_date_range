from time import sleep

from mail_storage import settlement_mail_mover

while 1:
    settlement_mail_mover('X')
    sleep(60)
