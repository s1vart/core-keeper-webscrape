from apscheduler.schedulers.background import BackgroundScheduler
from scraper import update_game_data

scheduler = BackgroundScheduler()
scheduler.add_job(func=update_game_data, trigger="interval", days=1)
scheduler.start() 