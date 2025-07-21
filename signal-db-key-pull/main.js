const { app } = require('electron')
const getDbKey = require('./signal-secrets')

app.whenReady().then(() => {
	let prefix = '';
	if (process.env.SIGNAL_CONFIG_PATH !== undefined) {
		prefix = `SIGNAL_CONFIG_PATH=${process.env.SIGNAL_CONFIG_PATH} `;
	}
	console.log(`Now run ${prefix}python -m adhesive.signal_auth ${getDbKey()}.`)
	app.quit()
})
