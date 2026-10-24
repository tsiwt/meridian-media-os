import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, r"C:\Users\admin\AppData\Local\Temp\opencode\qrcheck")

from PIL import Image  # noqa: E402
import zxingcpp  # noqa: E402

from app.qr import encode  # noqa: E402

TESTS = [
    "https://example.com/claim/MQI-TEST1",
    "http://192.168.1.23:7860/claim/MQI-GOLD15",
    "https://larry5432112345-meridian-media-os.hf.space/claim/MQI-SKY35",
]


def render(matrix, scale=8, quiet=4):
    size = len(matrix)
    total = (size + quiet * 2) * scale
    image = Image.new("L", (total, total), 255)
    pixels = image.load()
    for row in range(size):
        for col in range(size):
            if matrix[row][col]:
                for y in range((row + quiet) * scale, (row + quiet + 1) * scale):
                    for x in range((col + quiet) * scale, (col + quiet + 1) * scale):
                        pixels[x, y] = 0
    return image


for text in TESTS:
    matrix = encode(text)
    result = zxingcpp.read_barcode(render(matrix))
    print(len(matrix), len(text), "OK" if result and result.text == text else "FAIL", result.text if result else None)