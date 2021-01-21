#!/usr/bin/env python3
# Telegram Download Daemon
# Author: Alfonso E.M. <alfonso@el-magnifico.org>
# You need to install telethon (and cryptg to speed up downloads)

from os import getenv, rename
import subprocess
import math
import pwd
import unidecode

from sessionManager import getSession, saveSession

from telethon import TelegramClient, events
from telethon.tl.types import PeerChannel, DocumentAttributeFilename, DocumentAttributeVideo, MessageMediaDocument
import logging

logging.basicConfig(format='[%(levelname) 5s/%(asctime)s]%(name)s:%(message)s',
                    level=logging.WARNING)

import multiprocessing
import argparse
import asyncio

TELEGRAM_DAEMON_API_ID = getenv("TELEGRAM_DAEMON_API_ID")
TELEGRAM_DAEMON_API_HASH = getenv("TELEGRAM_DAEMON_API_HASH")
TELEGRAM_DAEMON_CHANNEL = getenv("TELEGRAM_DAEMON_CHANNEL")

TELEGRAM_DAEMON_SESSION_PATH = getenv("TELEGRAM_DAEMON_SESSION_PATH")

parser = argparse.ArgumentParser(
    description="Script to download files from Telegram Channel.")
parser.add_argument(
    "--api-id",
    required=TELEGRAM_DAEMON_API_ID == None,
    type=int,
    default=TELEGRAM_DAEMON_API_ID,
    help=
    'api_id from https://core.telegram.org/api/obtaining_api_id (default is TELEGRAM_DAEMON_API_ID env var)'
)
parser.add_argument(
    "--api-hash",
    required=TELEGRAM_DAEMON_API_HASH == None,
    type=str,
    default=TELEGRAM_DAEMON_API_HASH,
    help=
    'api_hash from https://core.telegram.org/api/obtaining_api_id (default is TELEGRAM_DAEMON_API_HASH env var)'
)
parser.add_argument(
    "--dest",
    type=str,
    default=getenv("TELEGRAM_DAEMON_DEST", "/telegram-downloads"),
    help=
    'Destenation path for downloading files (default is /telegram-downloads).')
parser.add_argument(
    "--channel",
    required=TELEGRAM_DAEMON_CHANNEL == None,
    type=int,
    default=TELEGRAM_DAEMON_CHANNEL,
    help=
    'Channel id to download from it (default is TELEGRAM_DAEMON_CHANNEL env var'
)
args = parser.parse_args()

api_id = args.api_id
api_hash = args.api_hash
channel_id = args.channel
downloadFolder = args.dest
worker_count = multiprocessing.cpu_count()

# Edit these lines:
proxy = None


# End of interesting parameters
async def sendHelloMessage(client, peerChannel):
    entity = await client.get_entity(peerChannel)
    print("Hi! Ready for your files!")
#    await client.send_message(entity, "Hi! Ready for your files!")
 

async def log_reply(event : events.ChatAction.Event, reply):
    print(reply)
    await event.reply(reply)

def getFilename(event: events.NewMessage.Event):
    for attribute in event.media.document.attributes:
        if isinstance(attribute, DocumentAttributeFilename): return attribute.file_name
        if isinstance(attribute, DocumentAttributeVideo): return "DocumentAttributeVideo"


in_progress={}

def set_progress(filename, received, total):
    if received >= total:
        try: in_progress.pop(filename)
        except: pass
        return
    percentage = math.trunc(received / total * 10000) / 100;

    in_progress[filename] = f"{percentage} % ({received} / {total})"

with TelegramClient(getSession(), api_id, api_hash,
                    proxy=proxy).start() as client:

    saveSession(client.session)

    queue = asyncio.Queue()
    peerChannel = PeerChannel(channel_id)

    @client.on(events.NewMessage())
    async def handler(event):

        if event.to_id != peerChannel:
            return

        #print(event)

        if not event.media and event.message:
            command = event.message.message
            command = command.lower()
            output = "Unknown command"

            if command == "list":
                output = subprocess.run(["ls", "-l", downloadFolder], capture_output=True).stdout
                output = output.decode('utf-8')

            if command == "status":
                try:
                    output = "".join([ f"{key}: {value}\n" for (key, value) in in_progress.items()])
                    if output: output = "Active downloads:\n\n" + output
                    else: output = "No active downloads"
                except:
                    output = "Some error occured while checking the status. Retry."

            await log_reply(event, output)

        if event.media:
            if isinstance(event.media, MessageMediaDocument):
                if event.media.document.mime_type == "application/pdf":
                    filename=getFilename(event)
                    print(f"{filename} added to queue")
                    #await log_reply(event, f"{filename} added to queue")
                    queue.put_nowait(event)

    async def worker():
        while True:
            event = await queue.get()

            filename=getFilename(event)
            docsize = round(event.media.document.size/1048576, 2)
            print(f"Downloading file {filename} ({docsize} MB)")
            #await log_reply(
            #    event,
            #    f"Downloading file {filename} ({event.media.document.size} bytes)"
            #)

            download_callback = lambda received, total: set_progress(filename, received, total)

            await client.download_media(event.message, f"{downloadFolder}/{filename}.partial", progress_callback = download_callback)
            set_progress(filename, 1, 1)
            clean_filename = unidecode.unidecode(f"{filename}")
            rename(f"{downloadFolder}/{filename}.partial", f"{downloadFolder}/{clean_filename}")
            print(f"{clean_filename} ready")
            #await log_reply(event, f"{filename} ready")

            queue.task_done()

    async def start():
        tasks = []
        loop = asyncio.get_event_loop()
        for i in range(worker_count):
            task = loop.create_task(worker())
            tasks.append(task)
        await sendHelloMessage(client, peerChannel)
        await client.run_until_disconnected()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    client.loop.run_until_complete(start())
