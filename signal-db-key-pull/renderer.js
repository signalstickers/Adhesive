const information = document.getElementById('info')

const func = async () => {
	information.innerText = `Pass this key to python -m adhesive.signal_auth: ${await window.getSignalSecrets()}`
}

func()
