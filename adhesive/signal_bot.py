import logging
import secrets
from functools import wraps

import semaphore
from semaphore import StopPropagation
from .bot import INTRO, build_stickers_client
from .glue import convert_link_interactive, convert_pack_interactive, convert_to_telegram

logger = logging.getLogger(__name__)

# Signal doesn't support markdown
INTRO = INTRO.replace('`', '')

handlers = []
def handler(pattern):
	def deco(f):
		@wraps(f)
		async def handler(ctx):
			try:
				await f(ctx)
			except StopPropagation:
				raise
			except Exception as exc:
				ray_id = secrets.randbelow(2**64)
				await ctx.message.reply(
					'An internal error occurred while trying to run that command. '
					f'Hey if you see the owner, give them this code okay? {ray_id}',
					quote=True
				)
				logger.error('Unhandled exception in %s (%s)', f.__name__, ray_id, exc_info=exc)

		handlers.append((pattern, handler))
		return handler
	return deco

@handler(r'^/start')
async def intro(ctx):
	await ctx.message.reply(INTRO + ctx.bot.source_code_url)
	raise StopPropagation

@handler(r'^(https?|sgnl|tg)://')
async def convert(ctx):
	async for _, response in convert_link_interactive(
		ctx.bot.db,
		ctx.bot.tg_client,
		ctx.bot.stickers_client,
		ctx.message.get_body(),
	):
		await ctx.message.reply(response, quote=True)

	raise StopPropagation

@handler('')
async def convert_sticker(ctx):
	sticker = ctx.message.get_sticker()
	if sticker is None:
		return
	async for _, response in convert_pack_interactive(
		ctx.bot.db,
		ctx.bot.tg_client,
		ctx.bot.stickers_client,
		convert_to_telegram,
		sticker.pack.pack_id,
		sticker.pack.pack_key,
	):
		await ctx.message.reply(response, quote=True)

def build_client(config, db, tg_client, stickers_client):
	bot = semaphore.Bot(
		config['signal']['username'],
		socket_path=config['signal'].get('signald_socket_path', '/var/run/signald/signald.sock'),
	)
	bot.tg_client = tg_client
	bot.db = db
	bot.stickers_client = stickers_client
	bot.source_code_url = config['source_code_url']
	for pattern, callback in handlers:
		bot.register_handler(pattern, callback)

	return bot

async def run(signal_client):
	try:
		async with signal_client as bot:
			await bot.start()
	except FileNotFoundError:
		import sys
		logger.fatal(
			'Signal bot was configured but signald is not running. '
			'Please ensure signald is running or else disable the Signal bot '
			'by removing the signal.username key from the config file.'
		)
		sys.exit(1)
