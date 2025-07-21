const { app } = require('electron')
const getDbKey = require('./signal-secrets')

app.whenReady().then(() => {
	console.log(`Now run python -m adhesive.signal_auth ${getDbKey()} from the root of this repository.`)
	app.quit()
})
