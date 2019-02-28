import json
import logging
from datetime import datetime
import requests
from webexteamssdk import WebexTeamsAPI
from tinydb import TinyDB, Query, where
from tinydb.operations import delete, increment, decrement
from config import (
    webex_teams_token,
    bot_email,
    bot_name,
    logging_config,
    webhook_listener_base_url,
    webhook_port,
)

logging.basicConfig(**logging_config)
logger = logging.getLogger()

# initialize the database
db = TinyDB("db.json")
User = Query()

# Initialize the Bot in Webex Teams
api = WebexTeamsAPI(access_token=webex_teams_token)
bot_room_list = api.rooms.list()


def get_latest_version():
    """
    returns a dict with the latest win and osx version numbers
    """
    win_ver_url = "https://7f3b835a2983943a12b7-f3ec652549fc8fa11516a139bfb29b79.ssl.cf5.rackcdn.com/WebexTeamsDesktop-Windows-Gold/webexteams_upgrade.txt"
    mac_ver_url = "https://7f3b835a2983943a12b7-f3ec652549fc8fa11516a139bfb29b79.ssl.cf5.rackcdn.com/WebexTeamsDesktop-OSX-Gold/webexteams_upgrade.txt"

    win_ver_info = requests.get(win_ver_url)
    mac_ver_info = requests.get(mac_ver_url)

    win_ver_dict = json.loads(win_ver_info.text)
    mac_ver_dict = json.loads(mac_ver_info.text)
    return {
        win_ver_dict["versionInfo"]["platform"]: win_ver_dict["versionInfo"]["version"],
        mac_ver_dict["versionInfo"]["platform"]: mac_ver_dict["versionInfo"]["version"],
    }


def latest_version_message(version_info):
    """
    return a message formatted with the latest versions known available
    """
    messages = []
    for platform, version in version_info.items():
        message_body = (
            f"The latest version of Webex Teams for {platform} is **{version}**"
        )
        messages.append(message_body)
    return messages


def compare_latest_version(version_info, last_version=0):
    pass


for room in bot_room_list:
    print(f"bot is spawning in: {room.title}")

    bot_user = db.search(User.room_id == room.id)
    if bot_user == [] or bot_user == None:
        print(f"{room.title} not in db")
        db.insert(
            {
                "room_id": room.id,
                "room_title": room.title,
                "subscribed": True,
                "help_requests": {"general": 0},
                "last_access": str(datetime.now()),
                "createdAt": str(datetime.now()),
            }
        )


if __name__ == "__main__":
    latest_versions = get_latest_version()
    version_messages = latest_version_message(latest_versions)
    for message in version_messages:
        print(message)
