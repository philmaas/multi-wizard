from aiohttp import web

async def index(request):
    with open('index.html') as f:
        return web.Response(text=f.read(), content_type='text/html')





