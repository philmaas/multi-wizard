
import socketio
import asyncio
from aiohttp import web
import logging
import logging.handlers
import os
import sys

try:
    # Python 3.7 and newer, fast reentrant implementation
    # witohut task tracking (not needed for that when logging)
    from queue import SimpleQueue as Queue
except ImportError:
    from queue import Queue
from typing import List

# Keep this so that pyinstaller works properly with python-socketio module.
# See https://github.com/miguelgrinberg/python-socketio/issues/35#issuecomment-295809303
from engineio.async_drivers import aiohttp


# """
# Setup Logging.
# """
# Make all other modules log only warnings and above.
logging.basicConfig(level=logging.WARNING)

# Have this log at the info level.
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


# Create asyncio friendly logging handler.
class LocalQueueHandler(logging.handlers.QueueHandler):
    def emit(self, record: logging.LogRecord) -> None:
        # Removed the call to self.prepare(), handle task cancellation
        try:
            self.enqueue(record)
            # flush the output so logs show up in output.
            self.flush()
        except asyncio.CancelledError:
            raise
        except Exception:
            self.handleError(record)


# Setup the logging Queue.
# Code from blog: https://www.zopatista.com/python/2019/05/11/asyncio-logging/
def setup_logging_queue() -> None:
    """Move log handlers to a separate thread.

    Replace handlers on the root logger with a LocalQueueHandler,
    and start a logging.QueueListener holding the original
    handlers.

    """
    queue = Queue()
    root = logging.getLogger(__name__)

    handlers: List[logging.Handler] = []

    handler = LocalQueueHandler(queue)
    root.addHandler(handler)
    for h in root.handlers[:]:
        if h is not handler:
            root.removeHandler(h)
            handlers.append(h)

    listener = logging.handlers.QueueListener(
        queue, *handlers, respect_handler_level=True
    )
    listener.start()



class MessageServer(socketio.AsyncNamespace):

    def on_connect(self, sid, environ):
        logger.info("connected: {}".format(sid))

    def on_disconnect(self, sid):
        logger.info("disconnected: {}".format(sid))

    # Overrides the default method so we can essentially subscribe to arbitrary events.
    # See https://github.com/miguelgrinberg/python-socketio/blob/master/socketio/namespace.py#L23
    async def trigger_event(self, event, *args):
        """Dispatch an event to the proper handler method.
        In the most common usage, this method is not overloaded by subclasses,
        as it performs the routing of events to methods. However, this
        method can be overriden if special dispatching rules are needed, or if
        having a single method that catches all events is desired.
        """

        # First check if we're subscribing to this locally.
        handler_name = 'on_' + event
        if hasattr(self, handler_name):
            return getattr(self, handler_name)(*args)

        # Otherwise just re-emit the message for any subscribers.
        sid, data = args

        # It seems the SocketIO plugin in Unity doesn't allow bare strings as json, so they need to be put into a JSON
        # Object with a key of 'data' to work. If we get one like that, then re-emit just the string.
        # JSON Spec should allow for that, but old spec did not.
        # See https://stackoverflow.com/questions/13318420/is-a-single-string-value-considered-valid-json
        if type(data) == dict and 'data' in data:
            data = data['data']
        await publish_data(event, data)



async def test():
    """
    Just emits some test data every second to the 'test' topic.
     This should be found by the client.
    :return:
    """
    while True:
        # Send a sample computer_vision.frame_detection in base64 format.
        #data = 'Ch8KCg0AAAJDFQAAhUMSCg0AAItDFQCA4UMYASUogEU/Ch0KCg0AAERCFQAAcUMSCg0AAOtDFQAA70MlRCUZPxILCI71u/IFEIeC50k='

        #dialogflow transcript: 'check check check.."
        data = 'CAESH2NoZWNrIGNoZWNrIGNoZWNrIG9uZSB0d28gdGhyZWUYASVB1Xw/KgwIoLXQ8gUQjs7DwQI='

        # dialogflow intent: Fallback Intent
        # data = 'ChdEZWZhdWx0IEZhbGxiYWNrIEludGVudBUAAIA/Gh5JJ20gYWZyYWlkIEkgZG9uJ3QgdW5kZXJzdGFuZC4iDAigtdDyBRDhtPGHAw=='

        await publish_data('test', data)
        await asyncio.sleep(1)


async def publish_data(topic, data):
    """
    Sends data out to a topic.
    :param topic: str
    :param data: str (base64 encoded for protobuf)
    :return:
    """
    logger.info("[{}] {}".format(topic, data))
    # Careful that we don't send anything other than strings.
    try:
        assert type(data) == str
        await sio.emit(topic, {'data': data})
    except Exception as e:
        logger.error("Error publishing data: ", e)


async def heartbeat(delay=5):
    while True:
        await publish_data('message-server.heartbeat', '')
        await asyncio.sleep(delay)

async def async_runner(app):
    """ An async version of aiohttp.web.run_app()

    Want this version so that we can run multiple coroutines.

    See https://docs.aiohttp.org/en/stable/web_advanced.html#application-runners

    """
    port = int(os.environ.get('PORT', 5000))
    host = "0.0.0.0"
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    logger.info("Client Server Listening {} on port {} ...".format(host, port))
    await site.start()


from aiohttp import web
from routes import setup_routes, setup_static_routes

# create a Socket.IO server
sio = socketio.AsyncServer(cors_allowed_origins='*', async_mode='aiohttp')
app = web.Application()
setup_routes(app)
setup_static_routes(app)
sio.attach(app)


# Note: When I tried changing this to /test it didn't seem to work for some reason.
sio.register_namespace(MessageServer('/'))


if __name__ == '__main__':
	
	#List of the coroutines we want to run at the same time.  
    coros = [
        heartbeat(delay=5),
        async_runner(app)
        #test()
    ]
    try:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(asyncio.gather(*coros))
    except KeyboardInterrupt:
        pass
    finally:
        loop.close()
