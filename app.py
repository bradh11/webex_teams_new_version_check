import os
import json
import time
import logging
import threading
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
db = TinyDB("db.json", indent=2, sort_keys=True)
db.table(name="_default", cache_size=0)
User = Query()

# Initialize the Bot in Webex Teams
api = WebexTeamsAPI(access_token=webex_teams_token)
bot_room_list = api.rooms.list()
registered_webhooks = api.webhooks.list()
webhook_listener = webhook_listener_base_url + f":{webhook_port}/{bot_name}"

app = Flask(__name__)

help_message_group = f"## Webex Teams Update Notifier\nThank you for adding me to your space.  I am here to alert you when new versions of Webex Teams are released by Cisco.  I will do this automatically unless you ask me not to.\n\n* If you want to stop receiving automatic updates simply @mention me and type `unsubscribe`.\n\n* If you want to opt back in simply @mention me and type `subscribe`\n\n* If you want to know the latest version, simply type `version`"
help_message_direct = f"## Webex Teams Update Notifier\nThank you for adding me to your space.  I am here to alert you when new versions of Webex Teams are released by Cisco.  I will do this automatically unless you ask me not to.\n\n* If you want to stop receiving automatic updates simply type `unsubscribe`.\n\n* If you want to opt back in simply type `subscribe`\n\n* If you want to know the latest version, simply type `version`"
release_notes = f"https://help.webex.com/en-us/mqkve8/Cisco-Webex-Teams-Release-Notes"
whats_new = f"https://help.webex.com/en-us/8dmbcr/What-s-New-in-Cisco-Webex-Teams"


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


def check_version_cache_exists():
    exists = os.path.isfile("version_cache.json")
    if exists:
        pass
    else:
        update_version_cache(get_latest_version())


def get_old_version():
    check_version_cache_exists()
    with open("version_cache.json", "rb") as ov:
        version_file = ov.read()
        version_dict = json.loads(version_file)
    return version_dict


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
    messages.append(
        f"To learn more, you can check out the [release notes]({release_notes}) and find out [what's new]({whats_new})"
    )

    return messages


def compare_latest_version(version_info):
    # pull last known version and compare it to the latest one received from get_latest_version()
    updated_versions = []
    old_ver = get_old_version()
    new_ver = version_info
    for platform, version in old_ver.items():
        if new_ver[platform] > version:
            updated_versions.append({platform: new_ver[platform]})

    return updated_versions


def update_room_in_database(json_data):
    """
    # Get Room details from room ID and update the DB if room does not exist
    """
    room_id = json_data["data"]["roomId"]
    room = api.rooms.get(roomId=room_id)
    print(f"webhook received from: {room.title}")

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
    else:
        bot_user[0]["last_access"] = str(datetime.now())
        bot_user[0]["room_title"] = room.title
        bot_user[0]["help_requests"]["general"] = (
            bot_user[0]["help_requests"]["general"] + 1
        )
        db.write_back(bot_user)


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

    # print(received_message)
    if "unsubscribe" in received_message.text.lower():
        unsubscribe_to_updates(room_id, reason="message")
    elif "subscribe" in received_message.text.lower():
        subscribe_to_updates(room_id)
    elif "help" in received_message.text.lower() and room_type == "direct":
        api.messages.create(roomId=room_id, markdown=help_message_direct)
    elif "help" in received_message.text.lower() and room_type == "group":
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
    if json_data["data"]["personEmail"] != bot_email:
        update_room_in_database(json_data)

    # print(json_data)
    if json_data["resource"] == "memberships" and json_data["event"] == "created":
        update_room_in_database(json_data)
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


def update_version_cache(latest_versions):
    with open("version_cache.json", "w") as outfile:
        json.dump(latest_versions, outfile, indent=2)
    return True


def alert_subscribers(messages):
    """
    Alert subscribers that a version has changed
    """
    subscribers = db.search(User.subscribed == True)

    for user in subscribers:
        print(f"sending {messages} to {user['room_title']}")
        # TODO: api.messages.create  and send update messages
        api.messages.create(
            user["room_id"], markdown=f"## Webex Teams Update Notification:"
        )
        for message in messages:
            api.messages.create(user["room_id"], markdown=message)
        api.messages.create(
            user["room_id"], markdown=f"\nTo unsubscribe just type `unsubscribe`\n\n"
        )


def construct_version_update_messages(version_check):
    messages = []
    for ver in version_check:
        for platform, version in ver.items():
            messages.append(
                f"Webex Teams for {platform} has been updated to version {version}."
            )

    messages.append(
        f"To learn more, you can check out the [release notes]({release_notes}) and find out [what's new]({whats_new})"
    )

    return messages


def periodic_version_check():
    """ 
    This function will run inside a loop and check if versions have changed every 30 minutes.
    """
    interval = 180  # frequency of checks
    time.sleep(interval / 2)

    logger.debug(f"checking version for change")
    latest_versions = get_latest_version()
    version_changed = compare_latest_version(latest_versions)

    if not version_changed:
        print(f"no change in version")
        pass
    else:
        update_messages = construct_version_update_messages(version_changed)
        # alert_subscribers of change and send update messages
        alert_subscribers(update_messages)
        update_version_cache(latest_versions)

    threading.Timer(interval / 2, periodic_version_check).start()


if __name__ == "__main__":
    register_webhook()
    latest_versions = get_latest_version()
    # print(latest_versions)
    version_messages = latest_version_message(latest_versions)
    for message in version_messages:
        print(message)

    t = threading.Thread(target=periodic_version_check)
    t.start()

    print(f"bot is running")
    app.run(debug=True, host="0.0.0.0", port=webhook_port, use_reloader=False)
