def starstarmap(f, xs):
	for x in xs:
		yield f(**x)
