import json
import logging
from datetime import datetime
from flask import Flask, request
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
registered_webhooks = api.webhooks.list()
webhook_listener = webhook_listener_base_url + f":{webhook_port}/{bot_name}"

app = Flask(__name__)

help_message_group = f"## Webex Teams Update Notifier\nThank you for adding me to your space.  I am here to alert you when new versions of Webex Teams are released by Cisco.  I will do this automatically unless you ask me not to.\n\n* If you want to stop receiving automatic updates simply @mention me and type `unsubscribe`.\n\n* If you want to opt back in simply @mention me and type `subscribe`"
help_message_direct = f"## Webex Teams Update Notifier\nThank you for adding me to your space.  I am here to alert you when new versions of Webex Teams are released by Cisco.  I will do this automatically unless you ask me not to.\n\n* If you want to stop receiving automatic updates simply type `unsubscribe`.\n\n* If you want to opt back in simply type `subscribe`"


def register_webhook():
    # cleanout any old webhooks the bot created in the past when initializing
    for webhook in registered_webhooks:
        api.webhooks.delete(webhook.id)

    # Register the BOT webhook for new message notification
    webhook_reg = api.webhooks.create(
        name=bot_name, targetUrl=webhook_listener, resource="all", event="all"
    )
    logger.info(webhook_reg)


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
    # pull last known version and compare it to the latest one received from get_latest_version()
    pass


def add_room_to_database(json_data):
    """
    # Get Room details from room ID and update the DB if room does not exist
    """
    room_id = json_data["data"]["roomId"]
    room = api.rooms.get(roomId=room_id)
    print(f"bot is spawning in: {room.title}")

    room_type = json_data["data"]["roomType"]

    bot_user = db.search(User.room_id == room_id)
    if bot_user == [] or bot_user == None:
        print(f"{room.title} not in db")
        logger.info(f"{room.title} not in db")
        db.insert(
            {
                "room_id": room_id,
                "room_title": room.title,
                "room_type": room_type,
                "subscribed": True,
                "help_requests": {"general": 0},
                "last_access": str(datetime.now()),
                "createdAt": str(datetime.now()),
            }
        )


def unsubscribe_to_updates(room_id, reason="message"):
    """
    update the database subscription to false if the user types `unsubscribe`
    """
    bot_user = db.search(User.room_id == room_id)
    bot_user[0]["subscribed"] = False
    db.write_back(bot_user)
    logger.info(f"room has unsubscribed from updates: {room_id}")
    print(f"room has unsubscribed from updates: {room_id}")
    if reason == "message":
        api.messages.create(
            roomId=room_id,
            markdown=f"This room is now unsubscribed from update announcements.",
        )


def subscribe_to_updates(room_id, reason="message"):
    """
    update the database subscription to True if the user types `subscribe`
    """
    bot_user = db.search(User.room_id == room_id)
    bot_user[0]["subscribed"] = True

    logger.info(f"room has subscribed to updates: {room_id}")
    print(f"room has subscribed to updates: {room_id}")
    if reason == "message":
        api.messages.create(
            roomId=room_id,
            markdown=f"This room is now subscribed to update announcements.",
        )
    else:
        print(bot_user)
        if bot_user[0]["room_type"] == "group":
            api.messages.create(roomId=room_id, markdown=help_message_group)

        else:
            api.messages.create(roomId=room_id, markdown=help_message_direct)
    db.write_back(bot_user)


def respond_to_message(json_data):
    """
    """
    message_id = json_data["data"]["id"]
    user_id = json_data["data"]["personId"]
    email = json_data["data"]["personEmail"]
    room_id = json_data["data"]["roomId"]
    room_type = json_data["data"]["roomType"]
    input_file = json_data["data"].get("files")
    received_message = api.messages.get(messageId=message_id)

    # Only respond to messages not from the Bot account to avoid infinite loops...
    if email == bot_email:
        return  # break out of this function

    print(received_message)
    if "unsubscribe" in received_message.text:
        unsubscribe_to_updates(room_id, reason="message")
    elif "subscribe" in received_message.text:
        subscribe_to_updates(room_id)
    elif "help" in received_message.text and room_type == "direct":
        api.messages.create(roomId=room_id, markdown=help_message_direct)
    elif "help" in received_message.text and room_type == "group":
        api.messages.create(roomId=room_id, markdown=help_message_group)
    else:
        latest_versions = get_latest_version()
        version_messages = latest_version_message(latest_versions)
        for message in version_messages:
            api.messages.create(roomId=room_id, markdown=f"{message}")


@app.route(f"/{bot_name}", methods=["POST"])
def webhook_receiver():
    """
    Listen for incoming webhooks.  Webex Teams will send a POST for each message directed to the BOT.
    For a group space, @mention of the BOT must occur.
    For a 1-1, @mentions are not allowed and the bot will respond to any message directed to it.
    """
    json_data = request.json
    # logger.debug(json_data)
    # update database with room info if it does not exist yet
    add_room_to_database(json_data)

    # print(json_data)
    if json_data["resource"] == "memberships" and json_data["event"] == "created":
        add_room_to_database(json_data)
        subscribe_to_updates(
            room_id=json_data["data"]["roomId"], reason="deleted_membership"
        )

    if json_data["resource"] == "memberships" and json_data["event"] == "deleted":
        # disable subscription for room
        unsubscribe_to_updates(
            room_id=json_data["data"]["roomId"], reason="deleted_membership"
        )

    if json_data["resource"] == "messages" and json_data["event"] == "created":
        respond_to_message(json_data)

    return "200"


for room in bot_room_list:
    logger.info(f"bot is spawning in: {room.title}")


if __name__ == "__main__":
    register_webhook()
    latest_versions = get_latest_version()
    version_messages = latest_version_message(latest_versions)
    for message in version_messages:
        print(message)

    print(f"bot is running")
    app.run(debug=True, host="0.0.0.0", port=webhook_port)
