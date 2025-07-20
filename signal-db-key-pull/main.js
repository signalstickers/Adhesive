const { app, BrowserWindow, ipcMain } = require('electron')
const path = require('node:path')
const SecretsReader = require('./signal-secrets')

const createWindow = () => {
	const win = new BrowserWindow({
    	width: 800,
    	height: 600,
		webPreferences: {
			preload: path.join(__dirname, 'preload.js'),
		},
	})

	win.loadFile('index.html')
}

app.whenReady().then(() => {
	const secretsReader = new SecretsReader()

	ipcMain.handle('get-signal-secrets', () => secretsReader.readAndDecryptSecrets())

	createWindow()

	app.on('activate', () => {
		if (BrowserWindow.getAllWindows().length === 0) createWindow()
	})
})

app.on('window-all-closed', () => {
	if (process.platform !== 'darwin') app.quit()
})

