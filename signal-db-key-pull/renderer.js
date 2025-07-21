const el = document.querySelector('span')

const func = async () => {
	el.innerText = await window.getSignalSecrets()
}

func()
