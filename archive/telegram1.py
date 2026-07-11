import asyncio
import os
import sys
from pathlib import Path

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.errors.rpcerrorlist import FloodWaitError
from telethon.tl.types import DocumentAttributeFilename


# === USER CONFIGURATION =====================================================

API_ID = 123456  # <-- YOUR api_id from my.telegram.org
API_HASH = "0123456789abcdef0123456789abcdef"  # <-- YOUR api_hash
SESSION_NAME = "tg_zip_download"  # Where the session file will be stored
PHONE_NUMBER = "+1234567890"  # Your phone number (including country code, e.g., +79001234567)

# Name or ID of the channel to download files from.
# You can use the channel's username (e.g., 'my_channel_username')
# or its ID (e.g., -1001234567890).
# If it's a private channel, you need to be a member.
TARGET_CHANNEL = "my_telegram_channel"  # <-- REPLACE WITH YOUR CHANNEL NAME/ID

# Folder where downloaded files will be saved
DOWNLOAD_DIR = "downloads_from_telegram"  # <-- CHANGE IF NECESSARY

# === END USER CONFIGURATION =================================================


async def main():
    # Create the download directory if it doesn't exist
    Path(DOWNLOAD_DIR).mkdir(parents=True, exist_ok=True)

    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

    print("Connecting to Telegram...")
    try:
        await client.connect()
    except Exception as e:
        print(f"Connection error: {e}")
        sys.exit(1)

    if not await client.is_user_authorized():
        print("Authorization...")
        try:
            await client.start(phone=PHONE_NUMBER)
        except SessionPasswordNeededError:
            password = input("Enter your two-factor authentication password: ")
            await client.start(password=password)
        print("Authorization successful!")

    print(f"Searching for channel: {TARGET_CHANNEL}")
    try:
        entity = await client.get_entity(TARGET_CHANNEL)
        print(f"Channel found: {entity.title} (ID: {entity.id})")
    except Exception as e:
        print(
            f"Could not find channel '{TARGET_CHANNEL}'. Make sure the name or ID is correct and you are a member of the channel. Error: {e}"
        )
        await client.disconnect()
        sys.exit(1)

    print(f"Starting download of .zip files from channel '{entity.title}' to folder '{DOWNLOAD_DIR}'...")

    total_downloaded = 0
    async for message in client.iter_messages(entity, reverse=True):  # reverse=True to scan from oldest to newest
        if message.document:
            for attr in message.document.attributes:
                if isinstance(attr, DocumentAttributeFilename) and attr.file_name.lower().endswith(".zip"):
                    file_name = attr.file_name
                    file_path = Path(DOWNLOAD_DIR) / file_name

                    if file_path.exists():
                        print(f"File '{file_name}' already exists, skipping.")
                        continue

                    print(f"Downloading: {file_name}")
                    try:
                        # Download the file
                        await client.download_media(message, file=file_path)
                        total_downloaded += 1
                        print(f"Successfully downloaded: {file_name}")
                    except FloodWaitError as e:
                        print(f"Rate limit hit. Waiting {e.seconds} seconds...")
                        await asyncio.sleep(e.seconds)
                        # Retry downloading
                        await client.download_media(message, file=file_path)
                        total_downloaded += 1
                        print(f"Successfully downloaded: {file_name}")
                    except Exception as e:
                        print(f"Failed to download {file_name}: {e}")

    print(f"\n=== Download complete! ===")
    print(f"Total .zip files downloaded: {total_downloaded}")
    print(f"Files saved to: {os.path.abspath(DOWNLOAD_DIR)}")

    await client.disconnect()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nScript interrupted by user.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
