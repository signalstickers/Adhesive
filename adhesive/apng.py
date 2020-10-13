import io

from apng import APNG
from lottie.exporters.cairo import export_png

# adapted from https://gitlab.com/mattbas/python-lottie/-/blob/v0.6.6/lib/lottie/exporters/gif.py#L70
# and used under the terms of the GNU AGPLv3 license
def export_apng(animation, fp):
	start = int(animation.in_point)
	end = int(animation.out_point)
	apng = APNG()
	for i in range(start, end + 1):
		file = io.BytesIO()
		export_png(animation, file, i)
		file.seek(0)
		apng.append_file(file, delay=int(round(1000 / animation.frame_rate)))
	apng.save(fp)
