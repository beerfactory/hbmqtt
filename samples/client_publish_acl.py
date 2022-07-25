import logging
import asyncio

from hbmqtt.client import MQTTClient, ConnectException


#
# This sample shows how to publish messages to broker using different QOS
# Debug outputs shows the message flows
#

logger = logging.getLogger(__name__)


async def test_coro():
    try:
        C = MQTTClient()
        await C.connect('mqtt://0.0.0.0:1883')
        await C.publish('data/classified', b'TOP SECRET', qos=0x01)
        await C.publish('data/memes', b'REAL FUN', qos=0x01)
        await C.publish('repositories/hbmqtt/master', b'NEW STABLE RELEASE', qos=0x01)
        await C.publish('repositories/hbmqtt/devel', b'THIS NEEDS TO BE CHECKED', qos=0x01)
        await C.publish('calendar/hbmqtt/releases', b'NEW RELEASE', qos=0x01)
        logger.info("messages published")
        await C.disconnect()
    except ConnectException as ce:
        logger.error("Connection failed: %s" % ce)
        asyncio.get_event_loop().stop()


if __name__ == '__main__':
    formatter = "[%(asctime)s] %(name)s {%(filename)s:%(lineno)d} %(levelname)s - %(message)s"
    formatter = "%(message)s"
    logging.basicConfig(level=logging.DEBUG, format=formatter)
    asyncio.get_event_loop().run_until_complete(test_coro())
