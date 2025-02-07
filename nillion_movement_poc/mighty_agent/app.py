import chainlit as cl

from agent_modules.chat.chat_application import ChatApplication
from agent_modules.chat.message_handler import MessageHandler
from agent_modules.factory.core_factory import CoreFactory
from agent_modules.factory.database_factory import DatabaseFactory
from agent_modules.factory.embedding_factory import EmbeddingFactory

from dishka import make_container

# Create the dependency container for later use
dependency_container = make_container(
    EmbeddingFactory(),
    CoreFactory(),
    DatabaseFactory()
)

message_handler = MessageHandler()

@cl.on_chat_start
async def start():
    try:
        app = ChatApplication(dependency_container)
        await app.initialize_chat_agent()
    except Exception as e:
        print(e)
        await cl.Message(content="The agent ran into an issue. Please refresh the page.").send()

@cl.on_message
async def on_message(message: cl.Message):
    await message_handler.handle_message(message)