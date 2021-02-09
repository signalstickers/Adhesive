# Port of org.whispersystems.textsecuregcm.limits.LeakyBucket

import time
from collections import namedtuple
from math import floor

class LeakyBucketConfig(namedtuple('LeakyBucketConfig', 'bucket_size leak_rate_per_second')):
	def new(self, **kwargs):
		return LeakyBucket(*self, **kwargs)

class LeakyBucket:
	__slots__ = 'bucket_size', 'leak_rate_per_second', 'space_remaining', 'last_updated_at'

	def __init__(
		self,
		bucket_size: int,
		leak_rate_per_second: float,
		*,
		space_remaining: int = None,
		last_updated_at: float = None,
		_timer=time.time,
	):
		self.bucket_size = bucket_size
		self.leak_rate_per_second = leak_rate_per_second
		self.space_remaining = bucket_size if space_remaining is None else space_remaining
		self.last_updated_at = _timer() if last_updated_at is None else last_updated_at

	def add(self, amount: int, now=None) -> bool:
		self.update_space_remaining(now)
		if (self.space_remaining >= amount):
			self.space_remaining -= amount
			return True
		return False

	def update_space_remaining(self, now=None, *, _timer=time.time) -> int:
		now = now or _timer()
		elapsed = now - self.last_updated_at
		self.last_updated_at = now
		rv = min(self.bucket_size, floor(self.space_remaining + elapsed * self.leak_rate_per_second))
		self.space_remaining = rv
		return rv

	def get_wait_time(self, amount: int, now=None) -> float:
		"""Return how long to wait until the given amount of tokens will be available."""
		space_remaining = self.update_space_remaining(now=now)
		if space_remaining >= amount:
			return 0.0
		return (amount - space_remaining) / self.leak_rate_per_second

	def __repr__(self):
		return (
			f'<{type(self).__qualname__} bucket_size={self.bucket_size} '
			f'leak_rate_per_second={self.leak_rate_per_second}>'
		)

# Port of org.whispersystems.textsecuregcm.tests.limits.LeackyBucketTest

def test_full():
	buck_conf = LeakyBucketConfig(2, 1.0 / 2.0)

	buck = buck_conf.new()

	assert buck.add(1)
	assert buck.get_wait_time(1) == 0.0
	assert buck.add(1)
	assert not buck.add(1)
	assert buck.get_wait_time(1) == 2.0

	buck = buck_conf.new()

	assert buck.add(2)
	assert not buck.add(1)
	assert not buck.add(2)

def test_lapse_rate():
	buck = LeakyBucket(
		bucket_size=2,
		leak_rate_per_second=4.0,
		space_remaining=0,
		last_updated_at=time.time()-2*60,
	)

	assert buck.add(2)
	assert not buck.add(1)
	time.sleep(1/4)
	assert buck.add(1)
	assert not buck.add(1)
	time.sleep(1/2)
	assert buck.add(2)
