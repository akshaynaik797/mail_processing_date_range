from time import sleep

from apscheduler.schedulers.background import BackgroundScheduler

def fun1(num):
    for i in range(num-10, num):
        print(i)
        sleep(1)

sched = BackgroundScheduler(daemon=False)
sched.add_job(fun1, 'interval', seconds=3, args=[10], max_instances=1)
sched.add_job(fun1, 'interval', seconds=3, args=[20], max_instances=1)
sched.add_job(fun1, 'interval', seconds=3, args=[30], max_instances=1)
sched.add_job(fun1, 'interval', seconds=3, args=[40], max_instances=1)
sched.start()
print('started')