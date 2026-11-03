import base64
import binascii
import io
import warnings
from PIL import Image, UnidentifiedImageError
MAX_REQUEST_BYTES = 17 * 1024 * 1024

def validate_images(images):
    if images is None:
        return []
    if not isinstance(images, list) or len(images) > 4:
        raise ValueError("Legfeljebb 4 kép csatolható.")
    result = []
    for item in images:
        formats = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}
        if not isinstance(item, dict) or item.get("mime_type") not in formats:
            raise ValueError("Csak JPG, PNG vagy WebP kép csatolható.")
        data = item.get("data")
        if not isinstance(data, str) or len(data) > 4 * 1024 * 1024:
            raise ValueError("Egy kép legfeljebb 3 MiB méretű lehet.")
        try:
            raw = base64.b64decode(data, validate=True)
        except (ValueError, binascii.Error):
            raise ValueError("Hibás képkódolás.") from None
        if not raw or len(raw) > 3 * 1024 * 1024:
            raise ValueError("Üres vagy túl nagy kép (maximum 3 MiB).")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(raw)) as img:
                    if img.format != formats[item["mime_type"]]:
                        raise ValueError("A kép tartalma nem egyezik a fájlformátummal.")
                    if img.width * img.height > 20_000_000 or getattr(img, "n_frames", 1) != 1:
                        raise ValueError("Legfeljebb 20 megapixeles állókép csatolható.")
                    img.verify()
                with Image.open(io.BytesIO(raw)) as img:
                    img.load()
        except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning):
            raise ValueError("A kép sérült vagy nem feldolgozható.") from None
        result.append({"mime_type": item["mime_type"], "data": data})
    return result
