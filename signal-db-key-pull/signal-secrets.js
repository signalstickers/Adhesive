const { app, safeStorage } = require('electron')
const fs = require('node:fs')
const path = require('node:path')

function getConfigDirPath() {
	return (
		process.env.SIGNAL_CONFIG_PATH !== undefined
		? process.env.SIGNAL_CONFIG_PATH
		: app.getPath('userData')
	)
}

function getDbKey() {
	const configFilePath = path.join(getConfigDirPath(), 'config.json');
	if (!fs.existsSync(configFilePath)) {
		throw new Error(`Signal config.json does not exist. ${this.configFilePath}`);
	}
	const configRaw = fs.readFileSync(configFilePath, 'utf-8')
	const config = JSON.parse(configRaw)

	// The encrypted key is stored as a hex string in config.json
	const encryptedKey = config.encryptedKey
	if (!encryptedKey) {
		throw new Error('No encrypted key found in config.json.')
	}

	const encryptedKeyBuffer = Buffer.from(encryptedKey, 'hex')
	if (!safeStorage.isEncryptionAvailable()) {
		throw new Error('Electron safeStorage encryption is not available on this system.')
	}

	// Decrypt the key using Electron's safeStorage
	const decryptedKey = safeStorage.decryptString(encryptedKeyBuffer)
	return decryptedKey
}

module.exports = getDbKey
