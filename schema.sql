-- This table stores packs converted from Telegram to Signal.
-- It does not store the reverse, because our Telegram sticker pack URLs include the signal pack_id
-- and that's used instead of this table.
CREATE TABLE packs (
	tg_hash INTEGER PRIMARY KEY,
	signal_pack_id BLOB NOT NULL,
	signal_pack_key BLOB NOT NULL,
	-- for timed deletion
	-- UTC seconds since 1970 without leap seconds
	converted_at INTEGER NOT NULL DEFAULT cast(strftime('%s', 'now') AS INT)
);
