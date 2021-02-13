from flask import Flask, request, jsonify, url_for
from flask_cors import CORS

from apscheduler.schedulers.background import BackgroundScheduler

from mail_storage_main import process_mails_in_range
app = Flask(__name__)
cors = CORS(app)


app.config['CORS_HEADERS'] = 'Content-Type'
app.config['referrer_url'] = None


@app.route("/")
def index():
    return url_for('index', _external=True)


@app.route("/process_mails", methods=["POST"])
def process_mails():
    data = request.form.to_dict()
    for i in ['hospital' 'fromtime', 'totime', 'deferred']:
        if i not in data:
            return jsonify({"error":f"pass {i} parameter"})
    sched = BackgroundScheduler(daemon=False)
    sched.add_job(process_mails_in_range, 'interval', seconds=30, max_instances=1, args=[data["hospital"], data['fromtime'], data['totime'], data['deferred']])
    sched.start()
    return jsonify("done")

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=9980)
