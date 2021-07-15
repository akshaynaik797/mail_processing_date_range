import signal
from time import sleep

timeout = 1


class TimeOutException(Exception):
    pass


def alarm_handler(signum, frame):
    print("ALARM signal received")
    raise TimeOutException()


while 1:
    try:
        signal.signal(signal.SIGALRM, alarm_handler)
        signal.alarm(timeout)
        sleep(10)
        signal.alarm(0)
    except:
        print('1')