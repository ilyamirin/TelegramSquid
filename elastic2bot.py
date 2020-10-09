#!/usr/bin/env python3

import argparse
import asyncio
import logging
import os
import yaml
import json

from datetime import datetime
from dateutil.parser import parse
from elasticsearch import Elasticsearch
from telethon import TelegramClient, events

LOG_LEVEL_INFO = 35

config = {}


def get_config(path: str, default=None, required=True):
    value = config

    for part in path.split("."):
        if value is None or part not in value:
            if required and default is None:
                raise KeyError("Config option {} not found in config file!".format(path))
            else:
                return default

        value = value.get(part)

    if value is None:
        value = default

    return value


def format_response(response, json_format=False):
    if response is None or not bool(response):
        data = "Not found similar entries"
    else:
        response = response["hits"]["hits"][0]["_source"]
        date_obj = parse(response["timestamp"])
        data = {
            "chat": response["chat"],
            "time": date_obj.strftime("%d %b %Y at %H:%M:%S"),
            "login": response["sender"]["username"],
            "name": f'{response["sender"]["firstName"]} {response["sender"]["lastName"]}',
            "message": response["message"]
        }

    if json_format:
        return json.dumps(data, indent=4, ensure_ascii=False)
    elif isinstance(data, dict):
        return f'''
chat: **{data["chat"]}**
time: **{data["time"]}**
login: **{data["login"]}**
name: **{data["name"]}**
message: **{data["message"]}**
'''
    else:
        return data


def is_user_banned(user):
    banned_users = get_config("telegram-bot.banned_users", [])
    return user.username in banned_users


async def answer_message(es_client, message, response_json):
    sender_user = await message.get_sender()

    if is_user_banned(sender_user):
        logging.debug("Skipping message {} from user '{}' because he is banned".format(message.id, sender_user.username))
        return

    text_to_search = message.message
    if text_to_search == "/start": #TODO: Добавить обработку команд
        return

    #TODO: Нужно поэкспериментировать с запросом
    query_body = {
        "query": {
            "match": {
                "message": {
                    "query": text_to_search,
                    "fuzziness": "auto",
                    "operator": "and"
                }
            }
        },
        "sort": {
            "timestamp": {
                "order": "desc"
            }
        },
        "size": 1
    }

    index_name = get_config("elasticsearch.index.prefix", "telegram")

    response = es_client.search(index=f"{index_name}*", body=query_body, filter_path=["hits.hits._*"])
    result = format_response(response, response_json)
    await message.reply(result)


async def listen_for_events(tg_client, es_client, response_json):
    @tg_client.on(events.NewMessage())
    @tg_client.on(events.MessageEdited())
    async def handler(event):
        if event.message.out: return # Some fix
        await answer_message(es_client, event.message, response_json)

    await tg_client.catch_up()


async def task(tg_client, es_client, arguments):
    await listen_for_events(tg_client, es_client, arguments.response_json)


def main():
    global config

    parser = argparse.ArgumentParser(description="A simple Telegram bot that searches for a user's message in the Elasticsearch and returns the source of a similar message")
    parser.add_argument("-c", "--config", help="path to your config file", default=os.getenv("CONFIG_FILE", "config.yml"))
    parser.add_argument("--response-json", help="bot will return messages in json format", action="store_true")

    arguments = parser.parse_args()

    logging.basicConfig(format="[%(levelname) 5s/%(asctime)s] %(name)s: %(message)s", level=logging.WARNING)
    logging.addLevelName(LOG_LEVEL_INFO, "INFO")

    with open(arguments.config, "r") as config_file:
        config = yaml.safe_load(config_file)

    if not isinstance(config, dict):
        logging.error("Unable to parse config file '{}'".format(arguments.config))
        exit(1)

    tg_client = TelegramClient(
        session=os.path.expanduser(get_config("telegram-bot.bot_session_file")),
        api_id=get_config("telegram.api_id"),
        api_hash=get_config("telegram.api_hash")
    ).start(bot_token=get_config("telegram-bot.bot_token"))
    es_client = Elasticsearch(hosts=get_config("elasticsearch.host", "localhost"))

    with tg_client:
        loop = asyncio.get_event_loop()

        loop.create_task(task(tg_client, es_client, arguments))

        try:
            loop.run_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
