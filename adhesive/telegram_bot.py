#!/usr/bin/env python3

import textwrap

import anyio
import telethon
from telethon import TelegramClient, errors, events, tl
from signalstickers_client import StickersClient as SignalStickersClient

from .glue import convert_interactive
from .bot import INTRO, build_stickers_client

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# so that we can register them all in the correct order later (globals() is not guaranteed to be ordered)
event_handlers = []
def register_event(*args, **kwargs):
	def deco(f):
		event_handlers.append(events.register(*args, **kwargs)(f))
		return f
	return deco

@register_event(events.NewMessage(pattern=r'^/start'))
async def intro(event):
	await event.respond(INTRO + event.client.source_code_url)

@register_event(events.NewMessage(pattern=r'^(https?|sgnl|tg)://'))
async def convert(event):
	async for response in convert_interactive(event.client, event.client.stickers_client, event.message.message):
		await event.respond(response)

def build_client(config, stickers_client):
	tg_config = config['telegram']
	signal_stickers_config = config['signal']['stickers']

	client = TelegramClient(tg_config.get('session_name', 'adhesive'), tg_config['api_id'], tg_config['api_hash'])
	client.config = tg_config
	client.source_code_url = config['source_code_url']
	client.stickers_client = stickers_client

	for handler in event_handlers:
		client.add_event_handler(handler)

	return client

async def run(client):
	await client.start(bot_token=client.config['api_token'])
	async with client:
		await client.run_until_disconnected()

def main():
	import toml
	with open('config.toml') as f:
		config = toml.load(f)

	stickers_client = build_stickers_client(config)
	client = build_client(config, stickers_client)

	anyio.run(run, client)

if __name__ == '__main__':
	main()
