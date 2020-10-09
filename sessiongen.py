#!/usr/bin/env python3

import sys
import yaml
import argparse
import os

from pathlib import Path
from telethon.sync import TelegramClient
from telethon.errors.rpcerrorlist import AuthKeyUnregisteredError, PhoneCodeInvalidError

# These example values won't work. You must get your own api_id and
# api_hash from https://my.telegram.org, under API Development.
# Look https://core.telegram.org/api/obtaining_api_id for more info

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


def main():
    global config

    parser = argparse.ArgumentParser(description=
        "Utility for generating *.session file for Telegram user, necessary for other scripts to work on behalf of the user"
    )
    parser.add_argument("-c", "--config", help="path to your config file", default=os.getenv("CONFIG_FILE", "config.yml"))
    args = parser.parse_args()

    with open(args.config, "r") as config_file:
        config = yaml.safe_load(config_file)

    if not isinstance(config, dict):
        print("Unable to parse config file '{}'".format(args.config), file=sys.stderr)
        exit(1)

    client = TelegramClient(
        os.path.expanduser(get_config("telegram.session_file")),
        get_config("telegram.api_id"), 
        get_config("telegram.api_hash")
    )
    client.connect()

    try:
        if not client.is_user_authorized():
            client.send_code_request(get_config("telegram.phone_number"))
            client.sign_in(get_config("telegram.phone_number"), input("Enter the code: "))
            client.send_message("me", "Hello! Friend. This is a message for getting *.session file")
            print("Look in the Telegram for a new message...")

        user_name = client.get_me().username
        file_name, _ = os.path.splitext(get_config("telegram.session_file"))
        print("File '{}.session' is valid for '{}' user".format(file_name, user_name))
    except KeyboardInterrupt:
        pass
    except (AuthKeyUnregisteredError, PhoneCodeInvalidError) as msg:
        print("ERROR: {}".format(msg), file=sys.stderr)
        exit(1)
    finally:
        client.disconnect()


if __name__ == "__main__":
    main()
