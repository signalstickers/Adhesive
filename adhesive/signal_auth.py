import os, sys
import contextlib
import json
from collections import namedtuple
from contextvars import ContextVar
from sqlcipher3 import dbapi2 as sqlcipher
from pathlib import Path

def get_config_path():
	# https://www.electronjs.org/docs/api/app#appgetpathname
	with contextlib.suppress(KeyError):
		return os.environ['SIGNAL_CONFIG_PATH']

	if os.name == 'nt':  # Windows
		p = os.environ['APPDATA']
	elif sys.platform == 'darwin': # macOS
		p = '~/Library/Application Support'
	elif os.name == 'posix':
		try:
			p = os.environ['XDG_CONFIG_HOME']
		except KeyError:
			p = '~/.config'
	else:
		raise LookupError('Signal config path could not be located. Please set env var SIGNAL_CONFIG_PATH instead.')

	return Path(p) / 'Signal'

_db = ContextVar('db')

def db():
	with contextlib.suppress(LookupError):
		return _db.get()

	config_path = get_config_path()
	db = sqlcipher.connect(get_config_path() / 'sql' / 'db.sqlite')
	key = json.loads((config_path / 'config.json').read_text())['key']
	db.execute(f'''PRAGMA key="x'{key}'"''')
	_db.set(db)
	return db

def fetchval(db, query, *args):
	return db.execute(query, *args).fetchone()[0]

def get_config_item(key):
	try:
		return json.loads(fetchval(db(), 'SELECT json FROM items WHERE id = ?', (key,)))['value']
	except (TypeError, KeyError):
		return None

Credentials = namedtuple('Credentials', 'username password')

def get_credentials():
	# https://github.com/signalapp/Signal-Desktop/blob/9181731c78768dbd519a1bf1bf15851f844741d0/sticker-creator/preload.js#L80-L108

	username = get_config_item('uuid_id')
	old_username = get_config_item('number_id')
	password = get_config_item('password')

	if not old_username or not password:
		raise LookupError('Please set up Signal on your phone and desktop to use the Signal sticker packs')

	return Credentials(username or old_username, password)

if __name__ == '__main__':
	username, password = get_credentials()
	print(f"username = '{username}'")
	print(f"password = '{password}'")
