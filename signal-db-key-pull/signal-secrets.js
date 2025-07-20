const { app, safeStorage } = require('electron')
const fs = require('node:fs')
const path = require('node:path')

class SecretsReader {
    constructor() {
        this.configFilePath = this.getConfigFilePath();
    }

    getConfigFilePath() {
        // Signal Desktop stores config.json in its user data directory
        const platform = process.platform;

        return path.join(app.getPath('userData'), 'config.json');
    }

    readAndDecryptSecrets() {
        if (!fs.existsSync(this.configFilePath)) {
            throw new Error(`Signal config.json does not exist. ${this.configFilePath}`);
        }
        const configRaw = fs.readFileSync(this.configFilePath, 'utf-8');
        const config = JSON.parse(configRaw);

        // The encrypted key is usually stored as a base64 string in config.json
        const encryptedKey = config.encryptedKey;
        if (!encryptedKey) {
            throw new Error('No encrypted key found in config.json.');
        }

        const encryptedKeyBuffer = Buffer.from(encryptedKey, 'hex');
        if (!safeStorage.isEncryptionAvailable()) {
            throw new Error('Electron safeStorage encryption is not available on this system.');
        }

        // Decrypt the key using Electron's safeStorage
        const decryptedKey = safeStorage.decryptString(encryptedKeyBuffer);
        return decryptedKey;
    }
}

module.exports = SecretsReader
