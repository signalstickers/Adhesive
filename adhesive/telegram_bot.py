#!/usr/bin/env python3

import secrets
import textwrap
from functools import wraps

import anyio
import telethon
from telethon import TelegramClient, errors, events, tl
from signalstickers_client import StickersClient as SignalStickersClient

from .glue import convert_link_interactive, convert_pack_interactive, convert_to_signal
from .bot import INTRO, build_stickers_client

import logging
logger = logging.getLogger(__name__)
# this logger is a bit too noisy for my liking
logging.getLogger('telethon.client.downloads').setLevel(logging.WARNING)

# so that we can register them all in the correct order later (globals() is not guaranteed to be ordered)
event_handlers = []

def register_event(*args, **kwargs):
	def deco(f):
		@wraps(f)
		async def handler(event):
			try:
				await f(event)
			except Exception as exc:
				ray_id = secrets.randbelow(2**64)
				await event.reply(
					'An internal error occurred while trying to run that command. '
					f'Hey if you see the owner, give them this code okay? `{ray_id}`'
				)
				logger.error('Unhandled exception in %s (%s)', f.__name__, ray_id, exc_info=exc)

		event_handlers.append(events.register(*args, **kwargs)(handler))
		return handler
	return deco

@register_event(events.NewMessage(pattern=r'^/start'))
async def intro(event):
	await event.respond(INTRO + event.client.source_code_url)
	raise events.StopPropagation

@register_event(events.NewMessage(pattern=r'^(https?|sgnl|tg)://'))
async def convert(event):
	async for response in convert_link_interactive(
		event.client.db, event.client, event.client.stickers_client, event.message.message,
	):
		await event.reply(response, link_preview=False)
	raise events.StopPropagation

def sticker_message_required(handler):
	@wraps(handler)
	async def wrapped_handler(event):
		message = event.message
		if not isinstance(message.media, tl.types.MessageMediaDocument):
			return
		for attr in message.media.document.attributes:
			if isinstance(attr, tl.types.DocumentAttributeSticker):
				event.sticker_set = attr.stickerset
				return await handler(event)

	return wrapped_handler

@register_event(events.NewMessage)
@sticker_message_required
async def convert_sticker(event):
	async for response in convert_pack_interactive(
		event.client.db, event.client, event.client.stickers_client, convert_to_signal, event.sticker_set,
	):
		await event.reply(response, link_preview=False)

def build_client(config, db, stickers_client):
	tg_config = config['telegram']
	signal_stickers_config = config['signal']['stickers']

	client = TelegramClient(tg_config.get('session_name', 'adhesive'), tg_config['api_id'], tg_config['api_hash'])
	client.config = tg_config
	client.source_code_url = config['source_code_url']
	client.stickers_client = stickers_client
	client.db = db

	for handler in event_handlers:
		client.add_event_handler(handler)

	return client

async def run(client):
	await client.start(bot_token=client.config['api_token'])
	client.user = await client.get_me()
	async with client:
		await client.run_until_disconnected()
