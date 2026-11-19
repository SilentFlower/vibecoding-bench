"""校验 Gemini 内嵌媒体，并在账号开启兼容时把 GIF 抽成 PNG。"""
import base64
from io import BytesIO
import json
import struct
import zlib

from .contract import InputError

BODY_LIMIT = 16 * 1024 * 1024
PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'
IMAGE_MIMES = frozenset({'image/png', 'image/jpeg', 'image/jpg', 'image/gif', 'image/webp',
                         'image/bmp', 'image/tiff', 'image/avif'})
INPUT_MIMES = IMAGE_MIMES | {'audio/wav', 'audio/x-wav', 'audio/mpeg', 'audio/ogg', 'audio/flac',
                             'video/mp4', 'video/webm', 'application/pdf'}


def _valid_png(data):
    if data[:16] != PNG_SIGNATURE + b'\0\0\0\rIHDR':
        return False
    offset = 8
    has_data = False
    while offset + 12 <= len(data):
        size = int.from_bytes(data[offset:offset + 4], 'big')
        end = offset + 8 + size
        if end + 4 > len(data):
            return False
        chunk = data[offset + 4:offset + 8]
        if zlib.crc32(data[offset + 4:end]) != int.from_bytes(data[end:end + 4], 'big'):
            return False
        if chunk == b'IHDR':
            if offset != 8 or not all(0 < n < 2**31 for n in struct.unpack_from('>II', data, 16)):
                return False
        elif chunk == b'IDAT':
            has_data |= size > 0
        elif chunk == b'IEND':
            return has_data and size == 0 and end + 4 == len(data)
        offset = end + 4
    return False


def _file_type_matches(mime, data):
    if mime in ('image/jpeg', 'image/jpg'):
        return data[:3] == b'\xff\xd8\xff' and data.find(b'\xff\xd9', 3) >= 0
    if mime == 'image/gif':
        return len(data) >= 14 and data[:6] in (b'GIF87a', b'GIF89a') and data.find(b';', 13) >= 0
    if mime == 'image/webp':
        return data[:4] == b'RIFF' and data[8:12] == b'WEBP'
    if mime in ('audio/wav', 'audio/x-wav'):
        return data[:4] in (b'RIFF', b'RF64') and data[8:12] == b'WAVE'
    if mime == 'audio/mpeg':
        return data[:3] == b'ID3' or (len(data) >= 4 and data[0] == 255 and data[1] & 0xe0 == 0xe0)
    if mime in ('image/avif', 'video/mp4'):
        ftyp_end = int.from_bytes(data[:4], 'big')
        if data[4:8] != b'ftyp' or not 16 <= ftyp_end <= len(data):
            return False
        avif_brands = (b'avif', b'avis')
        avif = data[8:12] in avif_brands or any(data[pos:pos + 4] in avif_brands for pos in range(16, ftyp_end, 4))
        return avif == (mime == 'image/avif')
    if mime == 'video/webm':
        return data[:4] == b'\x1a\x45\xdf\xa3' and b'webm' in data[:128]
    signatures = {'image/bmp': (b'BM',), 'image/tiff': (b'II*\0', b'MM\0*'),
                  'audio/ogg': (b'OggS',), 'audio/flac': (b'fLaC',), 'application/pdf': (b'%PDF-',)}
    return data.startswith(signatures[mime])


def _skip_blocks(data, pos):
    while pos < len(data):
        size = data[pos]
        pos += 1
        if not size:
            return pos
        pos += size
    raise ValueError('GIF 数据块不完整')


def _gif_layout(data, path, pixel_budget):
    width, height = struct.unpack_from('<HH', data, 6)
    if not (0 < width <= 4096 and 0 < height <= 4096):
        raise InputError('gif_conversion_limit:' + path)
    pixels = width * height
    max_frames = min(1000, pixel_budget // pixels)
    offset = 13 + (3 << ((data[10] & 7) + 1) if data[10] & 128 else 0)
    frames = 0
    try:
        while offset < len(data):
            kind = data[offset]
            offset += 1
            if kind == 0x3b and frames:
                return frames, frames * pixels
            if kind == 0x21:
                offset = _skip_blocks(data, offset + 1)
                continue
            if kind != 0x2c or offset + 10 > len(data):
                break
            x, y, w, h, flags = struct.unpack_from('<HHHHB', data, offset)
            if not w or not h or x + w > width or y + h > height:
                break
            frames += 1
            if frames > max_frames:
                raise InputError('gif_conversion_limit:' + path)
            offset += 9 + (3 << ((flags & 7) + 1) if flags & 128 else 0)
            if offset >= len(data) or not 2 <= data[offset] <= 8:
                break
            offset = _skip_blocks(data, offset + 1)
    except InputError:
        raise
    except ValueError:
        pass
    raise InputError('invalid_gemini_media:' + path)


class GifFrames:
    """限制同次请求的 GIF 解码像素、采样帧和 Base64 输出。"""

    def __init__(self, count, remaining):
        """建立请求预算。@param count 输入 GIF 数。@param remaining 可使用的 JSON 字节。@return 无。"""
        if count > 16 or remaining <= 0:
            raise InputError('gif_conversion_limit:/body/contents/0')
        self.frame_limit = min(8, 16 // count)
        self.remaining = remaining
        self.pixels = 134_217_728

    def convert(self, data, path):
        """按帧位置采样合成画布。@param data 已核对的 GIF。@param path 请求字段。@return 原生 PNG 媒体。"""
        from PIL import Image

        count, pixels = _gif_layout(data, path, self.pixels)
        self.pixels -= pixels
        selected = min(count, self.frame_limit)
        # Pillow 顺序读取以应用 GIF 的透明度与处置规则，采样位置包含首尾。
        indexes = [0] if selected == 1 else [
            (i * (count - 1) + (selected - 1) // 2) // (selected - 1) for i in range(selected)]
        result = []
        try:
            with Image.open(BytesIO(data), formats=['GIF']) as image:
                for index in indexes:
                    image.seek(index)
                    # 逐帧释放缓冲，避免请求同时保留全部 PNG 的字节和 Base64。
                    with BytesIO() as buffer:
                        original_write = buffer.write

                        def bounded_write(value):
                            projected = 4 * ((buffer.tell() + len(value) + 2) // 3) + 50
                            if projected > self.remaining:
                                raise InputError('gif_conversion_limit:' + path)
                            return original_write(value)

                        buffer.write = bounded_write
                        image.convert('RGBA').save(buffer, format='PNG')
                        encoded = base64.b64encode(buffer.getbuffer()).decode('ascii')
                    self.remaining -= len(encoded) + 50
                    result.append({'mimeType': 'image/png', 'inlineData': encoded})
        except (OSError, EOFError, SyntaxError) as err:
            raise InputError('invalid_gemini_media:' + path) from err
        return result


def _inline(part):
    field = next((name for name in ('inlineData', 'inline_data') if name in part), None)
    return field, part.get(field) if field else None


def _parts(contents):
    if isinstance(contents, list):
        for i, turn in enumerate(contents):
            if isinstance(turn, dict) and isinstance(turn.get('parts'), list):
                for j, part in enumerate(turn['parts']):
                    if isinstance(part, dict):
                        yield part, f'/body/contents/{i}/parts/{j}', turn.get('role', 'user')


def gif_budget(body, enabled):
    """按总请求大小预留转换空间。@param body 原始 Gemini 正文。@param enabled 账号开关。@return 转换预算或 None。"""
    if not enabled:
        return None
    sizes = []
    for part, _, _ in _parts(body.get('contents')):
        _, value = _inline(part)
        if isinstance(value, dict) and value.get('mimeType', value.get('mime_type')) == 'image/gif':
            content = value.get('data')
            sizes.append(len(content) if isinstance(content, str) else 0)
    if not sizes:
        return None
    size = len(json.dumps(body, separators=(',', ':'), ensure_ascii=False).encode())
    return GifFrames(len(sizes), BODY_LIMIT - size + sum(sizes))


def media_part(part, path, role, gif=None):
    """读取一个用户媒体 Part。@param part 原始 Part。@param path 字段路径。@param role 消息角色。@param gif 当前转换预算。@return 原生媒体列表或 None。"""
    field, value = _inline(part)
    if not field:
        return None
    path += '/' + field
    if role != 'user' or len(part) != 1 or not isinstance(value, dict):
        raise InputError('invalid_gemini_media:' + path)
    if set(value) not in ({'mimeType', 'data'}, {'mime_type', 'data'}):
        raise InputError('invalid_gemini_media:' + path)
    mime = value.get('mimeType', value.get('mime_type'))
    if not isinstance(mime, str) or mime not in INPUT_MIMES:
        raise InputError('unsupported_gemini_media_type:' + path)
    data = value['data']
    reason = 'invalid_gemini_png:' if mime == 'image/png' else 'invalid_gemini_media:'
    if not isinstance(data, str):
        raise InputError(reason + path)
    try:
        decoded = base64.b64decode(data, validate=True)
    except ValueError as err:
        raise InputError(reason + path) from err
    valid = _valid_png(memoryview(decoded)) if mime == 'image/png' else _file_type_matches(mime, decoded)
    if not valid:
        raise InputError(reason + path)
    return gif.convert(decoded, path) if gif and mime == 'image/gif' else [{'mimeType': mime, 'inlineData': data}]


def preflight_gif(body):
    """在领取工具结果前验证下一轮 GIF 转换。@param body 下一轮请求正文。@return 无。"""
    budget = gif_budget(body, True)
    if budget:
        for part, path, role in _parts(body.get('contents')):
            media_part(part, path, role, budget)
