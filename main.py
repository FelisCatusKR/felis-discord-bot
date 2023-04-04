from lagom import Container
from bot import MyDiscordClient, bootstrap

if __name__ == "__main__":
    container: Container = bootstrap()
    client: MyDiscordClient = container[MyDiscordClient]
    client.run(root_logger=True)
