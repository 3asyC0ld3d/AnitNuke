import discord
from discord.ext import commands
from discord import app_commands
import asyncio
from flask import Flask
from threading import Thread
import time
from collections import defaultdict
import json
import os
from dotenv import load_dotenv

# Initialize Flask for keep_alive
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run_flask)
    t.start()

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')

# Load or create config file
CONFIG_FILE = "config.json"
DEFAULT_CONFIG = {
    "whitelisted_role_id": 123456789012345678,  # Replace with your whitelisted role ID
    "ban_threshold": 2,  # Max bans allowed in time window
    "ban_window": 10,  # Time window for bans (seconds)
    "channel_threshold": 3,  # Max channel creations/deletions
    "channel_window": 10,  # Time window for channels
    "role_threshold": 2,  # Max role creations
    "role_window": 10,  # Time window for roles
    "log_channel": "mod-logs",  # Name of logging channel
    "command_cooldown": 5  # Cooldown for commands (seconds)
}

if not os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(DEFAULT_CONFIG, f, indent=4)

with open(CONFIG_FILE, 'r') as f:
    config = json.load(f)

# Bot setup
intents = discord.Intents.default()
intents.members = True
intents.bans = True
intents.webhooks = True
intents.guilds = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Track actions for rate limiting
ban_tracker = defaultdict(list)
channel_tracker = defaultdict(list)
role_tracker = defaultdict(list)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    try:
        synced = await bot.tree.sync()
        print(f'Synced {len(synced)} command(s)')
    except Exception as e:
        print(f"Error syncing commands: {e}")
    keep_alive()  # Start keep_alive server

# Helper function to send log embed
async def send_log(guild, title, description, color=discord.Color.red()):
    channel = discord.utils.get(guild.text_channels, name=config["log_channel"])
    if channel:
        embed = discord.Embed(title=title, description=description, color=color, timestamp=discord.utils.utcnow())
        await channel.send(embed=embed)

# Anti-nuke: Ban on bot addition
@bot.event
async def on_member_join(member):
    if member.bot:
        if not any(role.id == config["whitelisted_role_id"] for role in member.roles):
            try:
                await member.ban(reason="Anti-nuke: Unauthorized bot added")
                await send_log(member.guild, "Bot Banned", f"Banned {member.mention} for adding an unauthorized bot.")
            except Exception as e:
                print(f"Error banning bot {member}: {e}")
                await send_log(member.guild, "Error", f"Failed to ban {member.mention}: {e}", discord.Color.orange())

# Anti-nuke: Ban on webhook creation
@bot.event
async def on_webhook_update(channel):
    async for entry in channel.guild.audit_logs(limit=1, action=discord.AuditLogAction.webhook_create):
        user = entry.user
        if user.bot or user.id == bot.user.id:
            return
        if not any(role.id == config["whitelisted_role_id"] for role in user.roles):
            try:
                await user.ban(reason="Anti-nuke: Created webhook")
                await send_log(channel.guild, "Webhook Creation Detected", f"Banned {user.mention} for creating a webhook.")
            except Exception as e:
                print(f"Error banning {user}: {e}")
                await send_log(channel.guild, "Error", f"Failed to ban {user.mention}: {e}", discord.Color.orange())

# Anti-nuke: Ban on rapid bans
@bot.event
async def on_member_ban(guild, user):
    async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.ban):
        moderator = entry.user
        if moderator.bot or moderator.id == bot.user.id:
            return
        if not any(role.id == config["whitelisted_role_id"] for role in moderator.roles):
            current_time = time.time()
            ban_tracker[moderator.id].append(current_time)
            ban_tracker[moderator.id] = [t for t in ban_tracker[moderator.id] if current_time - t < config["ban_window"]]
            if len(ban_tracker[moderator.id]) > config["ban_threshold"]:
                try:
                    await moderator.ban(reason="Anti-nuke: Rapid banning detected")
                    await send_log(guild, "Rapid Ban Detected", f"Banned {moderator.mention} for banning {len(ban_tracker[moderator.id])} members in {config['ban_window']} seconds.")
                except Exception as e:
                    print(f"Error banning {moderator}: {e}")
                    await send_log(guild, "Error", f"Failed to ban {moderator.mention}: {e}", discord.Color.orange())

# Anti-nuke: Ban on rapid channel creation/deletion
@bot.event
async def on_guild_channel_create(channel):
    async for entry in channel.guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_create):
        user = entry.user
        if user.bot or user.id == bot.user.id:
            return
        if not any(role.id == config["whitelisted_role_id"] for role in user.roles):
            current_time = time.time()
            channel_tracker[user.id].append(current_time)
            channel_tracker[user.id] = [t for t in channel_tracker[user.id] if current_time - t < config["channel_window"]]
            if len(channel_tracker[user.id]) > config["channel_threshold"]:
                try:
                    await user.ban(reason="Anti-nuke: Rapid channel creation")
                    await send_log(channel.guild, "Rapid Channel Creation", f"Banned {user.mention} for creating {len(channel_tracker[user.id])} channels in {config['channel_window']} seconds.")
                except Exception as e:
                    print(f"Error banning {user}: {e}")
                    await send_log(channel.guild, "Error", f"Failed to ban {user.mention}: {e}", discord.Color.orange())

@bot.event
async def on_guild_channel_delete(channel):
    async for entry in channel.guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_delete):
        user = entry.user
        if user.bot or user.id == bot.user.id:
            return
        if not any(role.id == config["whitelisted_role_id"] for role in user.roles):
            current_time = time.time()
            channel_tracker[user.id].append(current_time)
            channel_tracker[user.id] = [t for t in channel_tracker[user.id] if current_time - t < config["channel_window"]]
            if len(channel_tracker[user.id]) > config["channel_threshold"]:
                try:
                    await user.ban(reason="Anti-nuke: Rapid channel deletion")
                    await send_log(channel.guild, "Rapid Channel Deletion", f"Banned {user.mention} for deleting {len(channel_tracker[user.id])} channels in {config['channel_window']} seconds.")
                except Exception as e:
                    print(f"Error banning {user}: {e}")
                    await send_log(channel.guild, "Error", f"Failed to ban {user.mention}: {e}", discord.Color.orange())

# Anti-nuke: Ban on rapid role creation
@bot.event
async def on_guild_role_create(role):
    async for entry in role.guild.audit_logs(limit=1, action=discord.AuditLogAction.role_create):
        user = entry.user
        if user.bot or user.id == bot.user.id:
            return
        if not any(role.id == config["whitelisted_role_id"] for role in user.roles):
            current_time = time.time()
            role_tracker[user.id].append(current_time)
            role_tracker[user.id] = [t for t in role_tracker[user.id] if current_time - t < config["role_window"]]
            if len(role_tracker[user.id]) > config["role_threshold"]:
                try:
                    await user.ban(reason="Anti-nuke: Rapid role creation")
                    await send_log(role.guild, "Rapid Role Creation", f"Banned {user.mention} for creating {len(role_tracker[user.id])} roles in {config['role_window']} seconds.")
                except Exception as e:
                    print(f"Error banning {user}: {e}")
                    await send_log(role.guild, "Error", f"Failed to ban {user.mention}: {e}", discord.Color.orange())

# Slash command: Ping with cooldown
@bot.tree.command(name="ping", description="Check bot latency")
@app_commands.checks.cooldown(1, config["command_cooldown"])
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"Pong! Latency: {round(bot.latency * 1000)}ms")

# Slash command: Set whitelisted role
@bot.tree.command(name="setwhitelist", description="Set the whitelisted role ID (admin only)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.checks.cooldown(1, config["command_cooldown"])
async def setwhitelist(interaction: discord.Interaction, role: discord.Role):
    config["whitelisted_role_id"] = role.id
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)
    await interaction.response.send_message(f"Whitelisted role set to {role.mention}")

# Slash command: View config
@bot.tree.command(name="viewconfig", description="View current bot configuration (admin only)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.checks.cooldown(1, config["command_cooldown"])
async def viewconfig(interaction: discord.Interaction):
    embed = discord.Embed(title="Anti-Nuke Bot Config", color=discord.Color.blue(), timestamp=discord.utils.utcnow())
    for key, value in config.items():
        embed.add_field(name=key.replace('_', ' ').title(), value=str(value), inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

# Error handler for commands
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("You need administrator permissions to use this command!", ephemeral=True)
    elif isinstance(error, app_commands.CommandOnCooldown):
        await interaction.response.send_message(f"Command on cooldown! Try again in {error.retry_after:.1f} seconds.", ephemeral=True)
    else:
        await interaction.response.send_message(f"An error occurred: {str(error)}", ephemeral=True)
        print(f"Command error: {error}")

# Run the bot
if BOT_TOKEN:
    bot.run(BOT_TOKEN)
else:
    print("Error: BOT_TOKEN not found in .env file")
