"""
Want-A-Hero Discord Bot
A bot for managing Age of Empires Mobile hero unlock requests.
"""

import discord
from discord import app_commands
from discord.ext import commands
import os
from dotenv import load_dotenv

from database import Database
from sheets import SheetsManager
from logger_setup import setup_logger
import config

load_dotenv()

logger = setup_logger()

# ─────────────────────────────────────────────
# Bot Setup
# ─────────────────────────────────────────────

intents = discord.Intents.default()
intents.message_content = True


class HeroBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        self.db = Database(config.DB_PATH)
        self.sheets: SheetsManager | None = (
            SheetsManager(
                credentials_path=config.GOOGLE_CREDENTIALS_PATH,
                spreadsheet_id=config.GOOGLE_SPREADSHEET_ID,
            )
            if config.GOOGLE_SHEETS_ENABLED
            else None
        )

    async def setup_hook(self):
        await self.tree.sync()
        logger.info("Slash commands synced with Discord.")

    async def on_ready(self):
        activity = discord.Activity(
            type=discord.ActivityType.watching, name="for hero requests"
        )
        await self.change_presence(activity=activity)
        logger.info(f"Bot online as {self.user} (ID: {self.user.id})")


bot = HeroBot()


# ─────────────────────────────────────────────
# Permission Helper
# ─────────────────────────────────────────────


def is_hero_admin(interaction: discord.Interaction) -> bool:
    """Return True if the user has admin permissions or the Hero Admin role."""
    if interaction.user.guild_permissions.administrator:
        return True
    return any(
        role.name == config.ADMIN_ROLE_NAME for role in interaction.user.roles
    )


# ─────────────────────────────────────────────
# /wantahero  — submit a hero request
# ─────────────────────────────────────────────


@bot.tree.command(
    name="wantahero",
    description="Submit a hero unlock request for Age of Empires Mobile.",
)
@app_commands.describe(
    game_name="Your in-game name in Age of Empires Mobile",
    alliance="Your alliance name",
    medals_needed="Number of medals required to unlock the hero",
    universal_medals="(Optional) Number of Universal Medals you currently have",
)
async def want_a_hero(
    interaction: discord.Interaction,
    game_name: str,
    alliance: str,
    medals_needed: int,
    universal_medals: int | None = None,
):
    logger.info(
        f"[{interaction.user}] /wantahero — game_name={game_name!r}, "
        f"alliance={alliance!r}, medals_needed={medals_needed}, "
        f"universal_medals={universal_medals}"
    )

    # Validate medals_needed
    if medals_needed <= 0:
        await interaction.response.send_message(
            "❌ **Medals needed** must be a positive number.", ephemeral=True
        )
        return
    if universal_medals is not None and universal_medals < 0:
        await interaction.response.send_message(
            "❌ **Universal Medals** cannot be negative.", ephemeral=True
        )
        return

    await interaction.response.defer()  # give us time to write to DB / Sheets

    # Write to database
    request_id = bot.db.add_request(
        discord_user_id=str(interaction.user.id),
        discord_username=str(interaction.user),
        game_name=game_name,
        alliance=alliance,
        medals_needed=medals_needed,
        universal_medals=universal_medals,
    )

    # Write to Google Sheets (non-fatal if it fails)
    sheets_status = ""
    if bot.sheets:
        try:
            bot.sheets.add_request(
                request_id=request_id,
                discord_username=str(interaction.user),
                game_name=game_name,
                alliance=alliance,
                medals_needed=medals_needed,
                universal_medals=universal_medals,
            )
            sheets_status = "\n📊 Also logged to the tracking spreadsheet."
        except Exception as exc:
            logger.error(f"Google Sheets write failed: {exc}")
            sheets_status = "\n⚠️ Could not write to Google Sheets (logged for admin)."

    embed = discord.Embed(
        title="⚔️ Hero Request Submitted!",
        description=f"Your request has been recorded. Good luck, Commander!{sheets_status}",
        color=discord.Color.gold(),
    )
    embed.add_field(name="Request ID", value=f"`#{request_id}`", inline=True)
    embed.add_field(name="Game Name", value=game_name, inline=True)
    embed.add_field(name="Alliance", value=alliance, inline=True)
    embed.add_field(name="Medals Needed", value=str(medals_needed), inline=True)
    if universal_medals is not None:
        embed.add_field(
            name="Universal Medals Owned", value=str(universal_medals), inline=True
        )
    embed.set_footer(
        text=f"Submitted by {interaction.user.display_name} • Request #{request_id}"
    )
    await interaction.followup.send(embed=embed)


# ─────────────────────────────────────────────
# /hero_report  — list all requests (Hero Admin)
# ─────────────────────────────────────────────


@bot.tree.command(
    name="hero_report",
    description="[Hero Admin] List all active hero requests.",
)
@app_commands.describe(
    week_offset="0 = current MGE week, -1 = last week, etc. (default: 0)"
)
async def hero_report(interaction: discord.Interaction, week_offset: int = 0):
    logger.info(
        f"[{interaction.user}] /hero_report — week_offset={week_offset}"
    )

    if not is_hero_admin(interaction):
        logger.warning(f"[{interaction.user}] Unauthorized /hero_report attempt.")
        await interaction.response.send_message(
            f"❌ You need the **{config.ADMIN_ROLE_NAME}** role to use this command.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True)

    requests = bot.db.get_requests_for_week(week_offset=week_offset)
    week_label = bot.db.get_week_label(week_offset=week_offset)

    if not requests:
        await interaction.followup.send(
            f"📋 No hero requests found for **{week_label}**.", ephemeral=True
        )
        return

    # Paginate if needed — Discord embeds cap at 25 fields
    CHUNK = 10
    pages = [requests[i : i + CHUNK] for i in range(0, len(requests), CHUNK)]

    for page_num, page in enumerate(pages):
        embed = discord.Embed(
            title=f"📋 Hero Requests — {week_label}",
            description=f"Total: **{len(requests)}** request(s)",
            color=discord.Color.blue(),
        )
        if len(pages) > 1:
            embed.title += f" (Page {page_num + 1}/{len(pages)})"

        for req in page:
            lines = [
                f"**Alliance:** {req['alliance']}",
                f"**Medals Needed:** {req['medals_needed']}",
            ]
            if req["universal_medals"] is not None:
                lines.append(f"**Universal Medals:** {req['universal_medals']}")
            lines.append(f"**Submitted:** {req['created_at']} UTC")
            embed.add_field(
                name=f"#{req['id']} · {req['game_name']} ({req['discord_username']})",
                value="\n".join(lines),
                inline=False,
            )

        await interaction.followup.send(embed=embed, ephemeral=True)


# ─────────────────────────────────────────────
# /hero_clear  — delete ALL requests (Hero Admin)
# ─────────────────────────────────────────────


@bot.tree.command(
    name="hero_clear",
    description="[Hero Admin] Clear ALL hero requests (irreversible).",
)
@app_commands.describe(
    confirm="Type 'YES' to confirm you want to delete all requests"
)
async def hero_clear(interaction: discord.Interaction, confirm: str):
    logger.info(f"[{interaction.user}] /hero_clear — confirm={confirm!r}")

    if not is_hero_admin(interaction):
        logger.warning(f"[{interaction.user}] Unauthorized /hero_clear attempt.")
        await interaction.response.send_message(
            f"❌ You need the **{config.ADMIN_ROLE_NAME}** role to use this command.",
            ephemeral=True,
        )
        return

    if confirm.strip().upper() != "YES":
        await interaction.response.send_message(
            "⚠️ You must type `YES` in the `confirm` field to clear all requests.",
            ephemeral=True,
        )
        return

    count = bot.db.clear_all_requests()
    logger.info(f"[{interaction.user}] Cleared {count} hero request(s).")
    await interaction.response.send_message(
        f"🗑️ Cleared **{count}** hero request(s). The list is now empty.",
        ephemeral=True,
    )


# ─────────────────────────────────────────────
# /hero_delete  — delete one request (Hero Admin)
# ─────────────────────────────────────────────


@bot.tree.command(
    name="hero_delete",
    description="[Hero Admin] Delete a specific hero request by ID.",
)
@app_commands.describe(request_id="The numeric request ID to delete (shown in submission embed)")
async def hero_delete(interaction: discord.Interaction, request_id: int):
    logger.info(f"[{interaction.user}] /hero_delete — request_id={request_id}")

    if not is_hero_admin(interaction):
        logger.warning(f"[{interaction.user}] Unauthorized /hero_delete attempt.")
        await interaction.response.send_message(
            f"❌ You need the **{config.ADMIN_ROLE_NAME}** role to use this command.",
            ephemeral=True,
        )
        return

    req = bot.db.get_request(request_id)
    if req is None:
        await interaction.response.send_message(
            f"❌ Request **#{request_id}** not found.", ephemeral=True
        )
        return

    bot.db.delete_request(request_id)
    logger.info(
        f"[{interaction.user}] Deleted request #{request_id} "
        f"(player: {req['game_name']}, submitted by: {req['discord_username']})"
    )
    await interaction.response.send_message(
        f"🗑️ Deleted request **#{request_id}** for `{req['game_name']}`.",
        ephemeral=True,
    )


# ─────────────────────────────────────────────
# /hero_update  — update a request (Hero Admin)
# ─────────────────────────────────────────────


@bot.tree.command(
    name="hero_update",
    description="[Hero Admin] Update fields on an existing hero request.",
)
@app_commands.describe(
    request_id="The numeric request ID to update",
    game_name="New in-game name (leave blank to keep current)",
    alliance="New alliance name (leave blank to keep current)",
    medals_needed="New medals-needed value (leave blank to keep current)",
    universal_medals="New Universal Medals count (leave blank to keep current)",
)
async def hero_update(
    interaction: discord.Interaction,
    request_id: int,
    game_name: str | None = None,
    alliance: str | None = None,
    medals_needed: int | None = None,
    universal_medals: int | None = None,
):
    logger.info(
        f"[{interaction.user}] /hero_update — request_id={request_id}, "
        f"game_name={game_name!r}, alliance={alliance!r}, "
        f"medals_needed={medals_needed}, universal_medals={universal_medals}"
    )

    if not is_hero_admin(interaction):
        logger.warning(f"[{interaction.user}] Unauthorized /hero_update attempt.")
        await interaction.response.send_message(
            f"❌ You need the **{config.ADMIN_ROLE_NAME}** role to use this command.",
            ephemeral=True,
        )
        return

    req = bot.db.get_request(request_id)
    if req is None:
        await interaction.response.send_message(
            f"❌ Request **#{request_id}** not found.", ephemeral=True
        )
        return

    # Apply only supplied fields
    new_game_name = game_name if game_name is not None else req["game_name"]
    new_alliance = alliance if alliance is not None else req["alliance"]
    new_medals_needed = medals_needed if medals_needed is not None else req["medals_needed"]
    new_universal_medals = (
        universal_medals if universal_medals is not None else req["universal_medals"]
    )

    bot.db.update_request(
        request_id=request_id,
        game_name=new_game_name,
        alliance=new_alliance,
        medals_needed=new_medals_needed,
        universal_medals=new_universal_medals,
    )

    logger.info(f"[{interaction.user}] Updated request #{request_id}.")

    embed = discord.Embed(
        title=f"✏️ Request #{request_id} Updated",
        color=discord.Color.orange(),
    )
    embed.add_field(name="Game Name", value=new_game_name, inline=True)
    embed.add_field(name="Alliance", value=new_alliance, inline=True)
    embed.add_field(name="Medals Needed", value=str(new_medals_needed), inline=True)
    if new_universal_medals is not None:
        embed.add_field(name="Universal Medals", value=str(new_universal_medals), inline=True)
    embed.set_footer(text=f"Updated by {interaction.user.display_name}")
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ─────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────

if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN is not set in your .env file.")
    bot.run(token, log_handler=None)  # We manage logging ourselves
