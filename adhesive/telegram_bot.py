#!/usr/bin/env python3

import contextlib
import secrets
import textwrap
from functools import wraps, partial

import anyio
import httpx
import telethon
import telethon.errors
from telethon import TelegramClient, errors, events, tl
from signalstickers_client import StickersClient as SignalStickersClient

from .glue import (
	convert_link_interactive,
	convert_pack_interactive,
	convert_to_signal,
	signal_pack_url,
	propose_to_signalstickers_dot_com,
)
from .bot import INTRO, build_stickers_client

import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
# this logger is a bit too noisy for my liking
for spammy_logger in 'telethon.client.downloads', 'telethon.client.uploads':
	logging.getLogger(spammy_logger).setLevel(logging.WARNING)

# so that we can register them all in the correct order later (globals() is not guaranteed to be ordered)
event_handlers = []

def register_event(*args, **kwargs):
	def deco(f):
		@wraps(f)
		async def handler(event):
			try:
				await f(event)
			except events.StopPropagation:
				raise
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
	async for is_link, response in convert_link_interactive(
		event.client.db, event.client, event.client.stickers_client, event.message.message,
	):
		await maybe_enter_convo(event, is_link, response)
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
	async for is_link, response in convert_pack_interactive(
		event.client.db, event.client, event.client.stickers_client, convert_to_signal, event.sticker_set,
	):
		await maybe_enter_convo(event, is_link, response)

async def maybe_enter_convo(event, is_link, response):
	"""Go through the signalstickers.com propose flow if this is a Signal pack link"""
	if not is_link or not isinstance(response, tuple):
		await event.reply(response, link_preview=False)
		return

	pack_id, pack_key = map(bytes.hex, response[:2])
	url = signal_pack_url(pack_id, pack_key)

	if not event.client.config['signal'].get('stickers', {}).get('signalstickers_api_key'):
		await event.reply(url)
		return

	# 'p' for 'propose'
	data = b'p' + b''.join(response[:2])
	orig_link = response[-1]
	buttons = [telethon.Button.inline('Propose to signalstickers.com', data=data)]

	timeout = 5 * 60

	async with event.client.conversation(event.sender.id) as convo:
		t = convo.wait_event(events.CallbackQuery(func=lambda e: e.data == data), timeout=timeout)
		orig_msg = await event.reply(url, buttons=buttons, link_preview=False)
		try:
			begin_ev = await t
		except anyio.get_cancelled_exc_class():
			return
		else:
			async with anyio.create_task_group() as tg:
				await tg.spawn(begin_ev.answer)
				await tg.spawn(partial(orig_msg.edit, buttons=None))

		meta = dict(
			pack_id=pack_id,
			pack_key=pack_key,
			source=orig_link,
			tags=[],
			nsfw=False,
			original=False,
			animated=False,
		)

		buttons = [
			# display the first two on row one…
			[
				telethon.Button.inline(
					'Edit tags',
					data=b't' + data[1:],
				), telethon.Button.inline(
					'Toggle NSFW',
					# 'l' for 'lewd'
					data=b'l' + data[1:],
				),
			# …and the last one on its own row
			], [telethon.Button.inline(
				'Done (propose this to signalstickers.com)',
				data=b'd' + data[1:],
			)],
		]

		def format_message():
			tags_pretty = ', '.join(f'“{tag}”' for tag in meta['tags']) if meta['tags'] else '__None__'
			nsfw_pretty = '__Not Safe For Work__' if meta['nsfw'] else '__Safe For Work__'

			return (
				f'**Tags:** {tags_pretty}\n'
				f'**NSFW:** {nsfw_pretty}'
			)

		def format_draft_message():
			return "OK, let's get this show on the road. Here's what I have so far:\n\n" + format_message()

		first_loop = True

		try:
			while True:
				t = convo.wait_event(
					events.CallbackQuery(
						func=lambda e: e.data[0] in b'tld' and e.data[1:] == data[1:]
					),
					timeout=timeout,
				)

				if first_loop:
					draft_msg = await convo.send_message(format_draft_message(), buttons=buttons)
					first_loop = False
				else:
					with contextlib.suppress(telethon.errors.MessageNotModifiedError):
						await draft_msg.edit(format_draft_message(), buttons=buttons)

				button_ev = await t

				if button_ev.data[0] == ord(b'd'):
					break

				if button_ev.data[0] == ord(b't'):
					await button_ev.answer()
					t = convo.get_response(timeout=timeout)
					tags_edit_msg = await convo.send_message('Enter some tags for your sticker pack, one per line.')
					msg = await t
					meta['tags'] = msg.message.splitlines()
					async with anyio.create_task_group() as tg:
						await tg.spawn(msg.delete)
						await tg.spawn(tags_edit_msg.delete)

				elif button_ev.data[0] == ord(b'l'):
					await button_ev.answer()
					meta['nsfw'] = not meta['nsfw']

				else:
					print(chr(button_ev.data[0]))

		except anyio.get_cancelled_exc_class():
			await event.respond('Sorry, you took too long to respond. Send the pack again to start over.')
			return

		status_code, data = await propose_to_signalstickers_dot_com(
			event.client.http,
			meta,
			token=event.client.config['signal']['stickers']['signalstickers_api_key'],
			# TODO use log levels for this i guess
			test_mode=event.client.config['signal']['stickers'].get('signalstickers_api_test_mode', False),
		)
		await button_ev.answer()
		await draft_msg.delete()
		if status_code not in range(200, 300):
			await event.reply(
				"Ruh roh. Looks like we got an error from signalstickers.com. Here's what they said: "
				f'“{data["error"]}”'
			)
		else:
			await event.reply(
				'Yuh, I submitted your pack to signalstickers.com. It will now be reviewed by a real meat-popsicle! '
				f'Check it out here: {data["pr_url"]}\n'
				'If you have a GitHub account you can comment on it there, '
				"or if you don't, you can DM [@signalstickers on Twitter](https://twitter.com/signalstickers).",
				link_preview=False,
			)

def build_client(config, db, stickers_client):
	tg_config = config['telegram']
	signal_stickers_config = config['signal']['stickers']

	client = TelegramClient(tg_config.get('session_name', 'adhesive'), tg_config['api_id'], tg_config['api_hash'])
	client.config = config
	client.source_code_url = config['source_code_url']
	client.stickers_client = stickers_client
	client.db = db

	for handler in event_handlers:
		client.add_event_handler(handler)

	return client

async def run(client):
	await client.start(bot_token=client.config['telegram']['api_token'])
	client.user = await client.get_me()
	# yes, with syntax really doesn't support parentheses
	async with \
		client, \
		httpx.AsyncClient(headers={'User-Agent': f'Adhesive ({client.config["source_code_url"]})'}) as client.http \
	:
		await client.run_until_disconnected()
