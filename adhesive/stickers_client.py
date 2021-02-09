import time
import logging
import itertools

import httpx

from signalstickers_client.classes import downloader, uploader
from signalstickers_client.models import LocalStickerPack
from signalstickers_client.utils.ca import CACERT_PATH
from signalstickers_client.errors import RateLimited as ServerRateLimited

from .leaky_bucket import LeakyBucketConfig, LeakyBucket

logger = logging.getLogger(__name__)

# https://github.com/signalapp/Signal-Server/blob/3432529f9c018d75774ce89f3207b18051c26fe7/service/src/main/java/org/whispersystems/textsecuregcm/configuration/RateLimitsConfiguration.java#L75
CREATE_PACK_RL = LeakyBucketConfig(bucket_size=50, leak_rate_per_second=20 / (60 * 60 * 24))

class RateLimited(Exception):
	pass

class Account:
	__slots__ = 'username password bucket'.split()
	def __init__(self, username, password, bucket=None):
		self.username = username
		self.password = password
		if bucket is None:
			self.bucket = CREATE_PACK_RL.new()
		else:
			self.bucket = bucket

class MultiStickersClient:
	def __init__(self, db, accounts, buckets=()):
		self.db = db
		self.http: httpx.AsyncClient

		if not buckets:
			buckets = itertools.repeat(None)
		elif len(buckets) != len(accounts):
			raise ValueError('Buckets must either be empty or correspond to accounts')

		self.accounts = accs = []
		for account_config, bucket in zip(accounts, buckets):
			accs.append(Account(account_config['username'], account_config['password'], bucket))

	async def __aenter__(self) -> 'MultiStickersClient':
		self.http = await httpx.AsyncClient(verify=CACERT_PATH).__aenter__()
		return self

	async def __aexit__(self, *excinfo):
		return await self.http.__aexit__(*excinfo)

	async def get_pack(self, pack_id, pack_key):
		return await downloader.get_pack(self.http, pack_id, pack_key)

	async def get_pack_metadata(self, pack_id, pack_key):
		return await downloader.get_pack_metadata(self.http, pack_id, pack_key)

	async def download_sticker(self, sticker_id: int, pack_id, pack_key) -> bytes:
		return await downloader.get_sticker(self.http, sticker_id, pack_id, pack_key)

	async def upload_pack(self, pack: LocalStickerPack):
		account = self.get_next_account()
		try:
			return await uploader.upload_pack(self.http, pack, account.username, account.password)
		except ServerRateLimited:
			logger.warning(
				'%s ratelimited but not detected client-side. Setting space_remaining to 0.', account.username
			)
			account.bucket.space_remaining = 0
			raise
		finally:
			await self.save(account)

	def get_next_account(self):
		now = time.time()
		for account in self.accounts:
			if account.bucket.add(1, now=now):
				return account

		logger.warning('All accounts ratelimited.')
		raise RateLimited('Unable to find an account with rate limit tokens remaining')

	async def save(self, account):
		await self.db.execute("""
			INSERT OR REPLACE INTO signal_accounts (account_id, space_remaining, last_updated_at)
			VALUES (?, ?, ?)
		""", (account.username, account.bucket.space_remaining, account.bucket.last_updated_at))

	def get_min_wait_time(self, amount=1):
		now = time.time()
		return min(account.bucket.get_wait_time(amount, now=now) for account in self.accounts)
