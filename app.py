import json
import logging
import requests

from config import webex_teams_token, bot_email, bot_name, logging_config

logging.basicConfig(**logging_config)
logger = logging.getLogger()

win_ver_url = "https://7f3b835a2983943a12b7-f3ec652549fc8fa11516a139bfb29b79.ssl.cf5.rackcdn.com/WebexTeamsDesktop-Windows-Gold/webexteams_upgrade.txt"
mac_ver_url = "https://7f3b835a2983943a12b7-f3ec652549fc8fa11516a139bfb29b79.ssl.cf5.rackcdn.com/WebexTeamsDesktop-OSX-Gold/webexteams_upgrade.txt"

win_ver_info = requests.get(win_ver_url)
win_ver_dict = json.loads(win_ver_info.text)

mac_ver_info = requests.get(mac_ver_url)
mac_ver_dict = json.loads(mac_ver_info.text)

print(win_ver_dict["versionInfo"]["version"])
print(mac_ver_dict["versionInfo"]["version"])
