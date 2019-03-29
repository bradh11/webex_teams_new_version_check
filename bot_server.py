import threading
from waitress import serve
from config import webhook_port
from apscheduler.schedulers.background import BackgroundScheduler
import bot


bot.register_webhook()

scheduler = BackgroundScheduler()
job = scheduler.add_job(bot.periodic_version_check, "interval", minutes=1)
scheduler.start()

serve(bot.app, host="0.0.0.0", port=webhook_port)
