import semaphore
from semaphore import StopPropagation
from .bot import INTRO, build_stickers_client
from .glue import convert_link_interactive, convert_pack_interactive, convert_to_telegram

# Signal doesn't support markdown
INTRO = INTRO.replace('`', '')

handlers = []
def handler(pattern):
	def deco(func):
		handlers.append((pattern, func))
		return func
	return deco

@handler(r'^/start')
async def intro(ctx):
	await ctx.message.reply(INTRO + ctx.bot.source_code_url)
	raise StopPropagation

@handler(r'^(https?|sgnl|tg)://')
async def convert(ctx):
	async for response in convert_link_interactive(ctx.bot.tg_client, ctx.bot.stickers_client, ctx.message.get_body()):
		await ctx.message.reply(response, quote=True)

	raise StopPropagation

@handler('')
async def convert_sticker(ctx):
	sticker = ctx.message.get_sticker()
	if sticker is None:
		return
	async for response in convert_pack_interactive(
		ctx.bot.tg_client, ctx.bot.stickers_client, convert_to_telegram, sticker.pack.pack_id, sticker.pack.pack_key,
	):
		await ctx.message.reply(response, quote=True)

def build_client(config, tg_client, stickers_client):
	bot = semaphore.Bot(config['signal']['username'])
	bot.tg_client = tg_client
	bot.stickers_client = stickers_client
	bot.source_code_url = config['source_code_url']
	for pattern, callback in handlers:
		bot.register_handler(pattern, callback)

	return bot

async def run(signal_client):
	async with signal_client as bot:
		await bot.start()
