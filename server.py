import asyncio
import logging
import os
import signal
from environs import Env
from pathlib import PurePath

import aiofiles
from aiohttp import web


PHOTOS_DIR = "test_photos"
ARCHIVE_NAME = "photos.zip"


async def archive(request, settings):
    network_delay = settings.get('network_delay', 0)
    archive_name = settings.get('archive_name', ARCHIVE_NAME)
    photos_dir = settings.get('photos_dir', PHOTOS_DIR)
    response = web.StreamResponse()

    cwd = PurePath(photos_dir, request.match_info.get("archive_hash"))
    if not os.path.exists(cwd):
        raise web.HTTPNotFound(
            text='The archive does not exist or has been deleted.'
        )
    response.headers['Content-Disposition'] = \
        f'attachment; filename="{archive_name}"'
    # Отправляет клиенту HTTP заголовки
    await response.prepare(request)

    proc = await asyncio.create_subprocess_exec(
        *('zip -r - .'.split()), 
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE)
    try:
        while not proc.stdout.at_eof():
            logging.info('Sending archive chunk ...')
            chunck = await proc.stdout.read(102400)
            if chunck:
                # Отправляет клиенту очередную порцию ответа
                await response.write(chunck)
            # Устанавливаем задержку для эмуляции плохого соединения
            if network_delay:
                await asyncio.sleep(network_delay)
    except asyncio.CancelledError as exc:
        logging.error(f'Download interrupted by {repr(exc)}')
        raise
    finally:
        # proc.send_signal(signal.SIGHUP)
        proc.kill()
        await proc.communicate()

    return response


async def handle_index_page(request):
    async with aiofiles.open('index.html', mode='r') as index_file:
        index_contents = await index_file.read()
    return web.Response(text=index_contents, content_type='text/html')


def get_settings():
    env = Env()
    env.read_env()

    if env.bool('ENABLE_LOGGING', False):
        logging.basicConfig(
            format='%(filename)s[LINE:%(lineno)d]# %(levelname)-8s '
                   '[%(asctime)s] %(message)s', level=logging.INFO,
        )
    settings = {}
    settings['network_delay'] = env.int('NETWORK_DELAY', 0)
    settings['archive_name'] = env.str('ARCHIVE_NAME', ARCHIVE_NAME)
    settings['photos_dir'] = env.str('PHOTOS_DIR', PHOTOS_DIR)
    return settings


if __name__ == '__main__':
    settings = get_settings()
    handle_archive = lambda request: archive(request, settings)
    app = web.Application()
    app.add_routes([
        web.get('/', handle_index_page),
        web.get('/archive/{archive_hash}/', handle_archive),
    ])
    web.run_app(app)
