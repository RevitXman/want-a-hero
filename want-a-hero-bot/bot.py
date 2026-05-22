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
import alliances as alliance_store
import heroes as hero_store
import sanitize
import config

load_dotenv()

logger = setup_logger()

# ─────────────────────────────────────────────
# Medal choices — rendered as a dropdown (1–10)
# ─────────────────────────────────────────────

MEDAL_CHOICES = [
    app_commands.Choice(name=f"{i} Medal{'s' if i > 1 else ''}", value=i)
    for i in range(1, 11)
]

# ─────────────────────────────────────────────
# Bot setup
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
        self.tree.add_command(alliance_group)
        self.tree.add_command(hero_manage_group)

        if config.GUILD_ID:
            # Guild sync is instant — commands appear in Discord immediately.
            guild = discord.Object(id=config.GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            logger.info(f"Slash commands synced to guild {config.GUILD_ID} (instant).")
        else:
            # Global sync can take up to 1 hour to propagate.
            await self.tree.sync()
            logger.info("Slash commands synced globally (may take up to 1 hour to appear).")

    async def on_ready(self):
        activity = discord.Activity(
            type=discord.ActivityType.watching, name="for hero requests"
        )
        await self.change_presence(activity=activity)
        logger.info(f"Bot online as {self.user} (ID: {self.user.id})")


bot = HeroBot()


# ─────────────────────────────────────────────
# Permission helper
# ─────────────────────────────────────────────


def is_hero_admin(interaction: discord.Interaction) -> bool:
    """Return True if the user has server admin permissions or the Hero Admin role."""
    if interaction.user.guild_permissions.administrator:
        return True
    return any(role.name == config.ADMIN_ROLE_NAME for role in interaction.user.roles)


# ─────────────────────────────────────────────
# Autocomplete callbacks
# ─────────────────────────────────────────────


async def alliance_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    names = alliance_store.get_all()
    return [
        app_commands.Choice(name=n, value=n)
        for n in names
        if current.upper() in n.upper()
    ][:25]


async def hero_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    names = hero_store.get_all()
    return [
        app_commands.Choice(name=n, value=n)
        for n in names
        if current.casefold() in n.casefold()
    ][:25]


# ─────────────────────────────────────────────
# Shared: write one hero submission to DB + Sheets
# ─────────────────────────────────────────────


def _persist_request(
    discord_user_id: str,
    discord_username: str,
    game_name: str,
    alliance: str,
    hero: str,
    medals_needed: int,
    universal_medals: int | None,
) -> int:
    """Insert one request row and optionally sync to Sheets. Returns request ID."""
    request_id = bot.db.add_request(
        discord_user_id=discord_user_id,
        discord_username=discord_username,
        game_name=game_name,
        alliance=alliance,
        hero=hero,
        medals_needed=medals_needed,
        universal_medals=universal_medals,
    )
    if bot.sheets:
        try:
            bot.sheets.add_request(
                request_id=request_id,
                discord_username=discord_username,
                game_name=game_name,
                alliance=alliance,
                medals_needed=medals_needed,
                universal_medals=universal_medals,
            )
        except Exception as exc:
            logger.error(f"Google Sheets write failed for request #{request_id}: {exc}")
    return request_id


# ─────────────────────────────────────────────
# /wantahero — submit up to 3 hero requests
# ─────────────────────────────────────────────


@bot.tree.command(
    name="wantahero",
    description="Submit hero unlock request(s) for Age of Empires Mobile.",
)
@app_commands.describe(
    game_name="Your in-game name in Age of Empires Mobile",
    alliance="Your alliance — pick from the list or start typing",
    hero_1="First hero you need medals for",
    medals_1="Medals required for Hero 1 (select 1–10)",
    hero_2="(Optional) Second hero",
    medals_2="Medals required for Hero 2",
    hero_3="(Optional) Third hero",
    medals_3="Medals required for Hero 3",
    universal_medals="(Optional) Universal Medals you currently own",
)
@app_commands.choices(
    medals_1=MEDAL_CHOICES,
    medals_2=MEDAL_CHOICES,
    medals_3=MEDAL_CHOICES,
)
@app_commands.autocomplete(
    alliance=alliance_autocomplete,
    hero_1=hero_autocomplete,
    hero_2=hero_autocomplete,
    hero_3=hero_autocomplete,
)
async def want_a_hero(
    interaction: discord.Interaction,
    game_name: str,
    alliance: str,
    hero_1: str,
    medals_1: int,
    hero_2: str | None = None,
    medals_2: int | None = None,
    hero_3: str | None = None,
    medals_3: int | None = None,
    universal_medals: int | None = None,
):
    logger.info(
        f"[{interaction.user}] /wantahero — game={game_name!r}, "
        f"alliance={alliance!r}, hero_1={hero_1!r}({medals_1}), "
        f"hero_2={hero_2!r}({medals_2}), hero_3={hero_3!r}({medals_3}), "
        f"uni={universal_medals}"
    )

    # ── Sanitize game name ────────────────────────────────────────────────────
    clean_name, err = sanitize.game_name(game_name)
    if err:
        await interaction.response.send_message(err, ephemeral=True)
        return

    # ── Validate alliance ─────────────────────────────────────────────────────
    if not alliance_store.exists(alliance):
        valid = ", ".join(f"`{n}`" for n in alliance_store.get_all())
        await interaction.response.send_message(
            f"❌ **{discord.utils.escape_markdown(alliance)}** is not a recognised alliance.\n"
            f"Please choose from: {valid}\n"
            f"Ask a **{config.ADMIN_ROLE_NAME}** to add yours with `/hero_alliance add`.",
            ephemeral=True,
        )
        return

    # ── Validate universal medals ─────────────────────────────────────────────
    clean_uni, err = sanitize.universal_medals(universal_medals)
    if err:
        await interaction.response.send_message(err, ephemeral=True)
        return

    # ── Build the list of (hero, medals) pairs to submit ─────────────────────
    # hero_2/hero_3 require their matching medals field; ignore unpaired entries
    hero_slots: list[tuple[str, int]] = []

    for slot_num, (hero, medals) in enumerate(
        [(hero_1, medals_1), (hero_2, medals_2), (hero_3, medals_3)], start=1
    ):
        if hero is None:
            continue
        if not hero_store.exists(hero):
            valid_heroes = ", ".join(f"`{n}`" for n in hero_store.get_all())
            await interaction.response.send_message(
                f"❌ **Hero {slot_num}:** `{discord.utils.escape_markdown(hero)}` is not in the hero list.\n"
                f"Available heroes: {valid_heroes}\n"
                f"Ask a **{config.ADMIN_ROLE_NAME}** to add them with `/hero_manage add`.",
                ephemeral=True,
            )
            return
        if medals is None:
            await interaction.response.send_message(
                f"❌ **Hero {slot_num}** (`{discord.utils.escape_markdown(hero)}`) "
                f"needs a **Medals {slot_num}** value.",
                ephemeral=True,
            )
            return
        hero_slots.append((hero, medals))

    await interaction.response.defer()

    # ── Persist each hero as its own request row ──────────────────────────────
    submitted: list[dict] = []
    for hero, medals in hero_slots:
        rid = _persist_request(
            discord_user_id=str(interaction.user.id),
            discord_username=str(interaction.user),
            game_name=clean_name,
            alliance=alliance,
            hero=hero,
            medals_needed=medals,
            universal_medals=clean_uni,
        )
        submitted.append({"id": rid, "hero": hero, "medals": medals})

    sheets_note = (
        "\n📊 Also logged to the tracking spreadsheet." if bot.sheets else ""
    )

    # ── Response embed ────────────────────────────────────────────────────────
    embed = discord.Embed(
        title="⚔️ Hero Request(s) Submitted!",
        description=(
            f"Recorded **{len(submitted)}** request(s) for **{clean_name}**."
            f"{sheets_note}"
        ),
        color=discord.Color.gold(),
    )
    embed.add_field(name="Alliance", value=alliance, inline=True)
    if clean_uni is not None:
        embed.add_field(name="Universal Medals Owned", value=str(clean_uni), inline=True)
    embed.add_field(name="​", value="​", inline=False)  # spacer

    for entry in submitted:
        medal_label = f"{entry['medals']} Medal{'s' if entry['medals'] > 1 else ''}"
        embed.add_field(
            name=f"Request #{entry['id']} — {entry['hero']}",
            value=f"**Medals needed:** {medal_label}",
            inline=False,
        )

    embed.set_footer(text=f"Submitted by {interaction.user.display_name}")
    await interaction.followup.send(embed=embed)


# ─────────────────────────────────────────────
# /hero_report — list requests (Hero Admin)
# ─────────────────────────────────────────────


@bot.tree.command(
    name="hero_report",
    description="[Hero Admin] List all active hero requests.",
)
@app_commands.describe(week_offset="0 = current MGE week, -1 = last week (default: 0)")
async def hero_report(interaction: discord.Interaction, week_offset: int = 0):
    logger.info(f"[{interaction.user}] /hero_report — week_offset={week_offset}")

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
            medals = req["medals_needed"]
            medal_label = f"{medals} Medal{'s' if medals > 1 else ''}"
            lines = [
                f"**Alliance:** {req['alliance']}",
                f"**Hero:** {req.get('hero', '—')}",
                f"**Medals Needed:** {medal_label}",
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
# /hero_clear — wipe all requests (Hero Admin)
# ─────────────────────────────────────────────


@bot.tree.command(
    name="hero_clear",
    description="[Hero Admin] Clear ALL hero requests (irreversible).",
)
@app_commands.describe(confirm="Type YES to confirm deletion of all requests")
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
            "⚠️ Type `YES` (all caps) in the `confirm` field to clear all requests.",
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
# /hero_delete — delete one request (Hero Admin)
# ─────────────────────────────────────────────


@bot.tree.command(
    name="hero_delete",
    description="[Hero Admin] Delete a specific hero request by ID.",
)
@app_commands.describe(request_id="The numeric request ID to delete")
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
        f"(player: {req['game_name']}, hero: {req.get('hero', '?')})"
    )
    await interaction.response.send_message(
        f"🗑️ Deleted request **#{request_id}** "
        f"({req['game_name']} — {req.get('hero', '?')}).",
        ephemeral=True,
    )


# ─────────────────────────────────────────────
# /hero_update — edit a request (Hero Admin)
# ─────────────────────────────────────────────


@bot.tree.command(
    name="hero_update",
    description="[Hero Admin] Update fields on an existing hero request.",
)
@app_commands.describe(
    request_id="The numeric request ID to update",
    game_name="New in-game name (leave blank to keep current)",
    alliance="New alliance (leave blank to keep current)",
    hero="New hero selection (leave blank to keep current)",
    medals_needed="New medal count (leave blank to keep current)",
    universal_medals="New Universal Medals count (leave blank to keep current)",
)
@app_commands.choices(medals_needed=MEDAL_CHOICES)
@app_commands.autocomplete(
    alliance=alliance_autocomplete,
    hero=hero_autocomplete,
)
async def hero_update(
    interaction: discord.Interaction,
    request_id: int,
    game_name: str | None = None,
    alliance: str | None = None,
    hero: str | None = None,
    medals_needed: int | None = None,
    universal_medals: int | None = None,
):
    logger.info(
        f"[{interaction.user}] /hero_update — request_id={request_id}, "
        f"game_name={game_name!r}, alliance={alliance!r}, hero={hero!r}, "
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

    if game_name is not None:
        game_name, err = sanitize.game_name(game_name)
        if err:
            await interaction.response.send_message(err, ephemeral=True)
            return

    if alliance is not None and not alliance_store.exists(alliance):
        valid = ", ".join(f"`{n}`" for n in alliance_store.get_all())
        await interaction.response.send_message(
            f"❌ **{discord.utils.escape_markdown(alliance)}** is not a recognised alliance.\n"
            f"Valid options: {valid}",
            ephemeral=True,
        )
        return

    if hero is not None and not hero_store.exists(hero):
        valid_heroes = ", ".join(f"`{n}`" for n in hero_store.get_all())
        await interaction.response.send_message(
            f"❌ **{discord.utils.escape_markdown(hero)}** is not in the hero list.\n"
            f"Available heroes: {valid_heroes}",
            ephemeral=True,
        )
        return

    if universal_medals is not None:
        universal_medals, err = sanitize.universal_medals(universal_medals)
        if err:
            await interaction.response.send_message(err, ephemeral=True)
            return

    new_game_name      = game_name       if game_name       is not None else req["game_name"]
    new_alliance       = alliance        if alliance         is not None else req["alliance"]
    new_hero           = hero            if hero             is not None else req.get("hero", "")
    new_medals_needed  = medals_needed   if medals_needed    is not None else req["medals_needed"]
    new_universal      = universal_medals if universal_medals is not None else req["universal_medals"]

    bot.db.update_request(
        request_id=request_id,
        game_name=new_game_name,
        alliance=new_alliance,
        hero=new_hero,
        medals_needed=new_medals_needed,
        universal_medals=new_universal,
    )
    logger.info(f"[{interaction.user}] Updated request #{request_id}.")

    medal_label = f"{new_medals_needed} Medal{'s' if new_medals_needed > 1 else ''}"
    embed = discord.Embed(title=f"✏️ Request #{request_id} Updated", color=discord.Color.orange())
    embed.add_field(name="Game Name",     value=new_game_name,  inline=True)
    embed.add_field(name="Alliance",      value=new_alliance,   inline=True)
    embed.add_field(name="Hero",          value=new_hero,       inline=True)
    embed.add_field(name="Medals Needed", value=medal_label,    inline=True)
    if new_universal is not None:
        embed.add_field(name="Universal Medals", value=str(new_universal), inline=True)
    embed.set_footer(text=f"Updated by {interaction.user.display_name}")
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ─────────────────────────────────────────────
# /hero_alliance group — manage alliance dropdown
# ─────────────────────────────────────────────


alliance_group = app_commands.Group(
    name="hero_alliance",
    description="Manage the alliance dropdown options.",
)


@alliance_group.command(name="list", description="Show all available alliances.")
async def alliance_list(interaction: discord.Interaction):
    logger.info(f"[{interaction.user}] /hero_alliance list")
    names = alliance_store.get_all()
    embed = discord.Embed(
        title="🏰 Available Alliances",
        description="\n".join(f"• {n}" for n in names) or "*(none configured)*",
        color=discord.Color.blurple(),
    )
    embed.set_footer(text=f"{len(names)} alliance(s)")
    await interaction.response.send_message(embed=embed, ephemeral=True)


@alliance_group.command(name="add", description="[Hero Admin] Add an alliance to the dropdown.")
@app_commands.describe(name="Alliance tag to add (e.g. S27, T2P, K-27)")
async def alliance_add(interaction: discord.Interaction, name: str):
    logger.info(f"[{interaction.user}] /hero_alliance add — name={name!r}")
    if not is_hero_admin(interaction):
        await interaction.response.send_message(
            f"❌ You need the **{config.ADMIN_ROLE_NAME}** role.", ephemeral=True
        )
        return
    clean, err = sanitize.alliance_name(name)
    if err:
        await interaction.response.send_message(err, ephemeral=True)
        return
    ok, reason = alliance_store.add(clean)
    if not ok:
        await interaction.response.send_message(f"⚠️ {reason}", ephemeral=True)
        return
    logger.info(f"[{interaction.user}] Added alliance '{clean}'.")
    await interaction.response.send_message(f"✅ Added **{clean}** to alliances.", ephemeral=True)


@alliance_group.command(name="remove", description="[Hero Admin] Remove an alliance from the dropdown.")
@app_commands.describe(name="Alliance to remove")
@app_commands.autocomplete(name=alliance_autocomplete)
async def alliance_remove(interaction: discord.Interaction, name: str):
    logger.info(f"[{interaction.user}] /hero_alliance remove — name={name!r}")
    if not is_hero_admin(interaction):
        await interaction.response.send_message(
            f"❌ You need the **{config.ADMIN_ROLE_NAME}** role.", ephemeral=True
        )
        return
    ok, result = alliance_store.remove(name)
    if not ok:
        await interaction.response.send_message(f"⚠️ {result}", ephemeral=True)
        return
    logger.info(f"[{interaction.user}] Removed alliance '{result}'.")
    await interaction.response.send_message(f"🗑️ Removed **{result}** from alliances.", ephemeral=True)


# ─────────────────────────────────────────────
# /hero_manage group — manage hero dropdown
# ─────────────────────────────────────────────


hero_manage_group = app_commands.Group(
    name="hero_manage",
    description="Manage the hero dropdown options.",
)


@hero_manage_group.command(name="list", description="Show all available heroes.")
async def hero_manage_list(interaction: discord.Interaction):
    logger.info(f"[{interaction.user}] /hero_manage list")
    names = hero_store.get_all()
    # Split into two columns if more than 10 heroes
    formatted = "\n".join(f"• {n}" for n in names) or "*(none configured)*"
    embed = discord.Embed(
        title="🦸 Available Heroes",
        description=formatted,
        color=discord.Color.blurple(),
    )
    embed.set_footer(text=f"{len(names)} hero(es) in the list")
    await interaction.response.send_message(embed=embed, ephemeral=True)


@hero_manage_group.command(name="add", description="[Hero Admin] Add a hero to the dropdown.")
@app_commands.describe(name="Hero name to add (e.g. Julius Caesar, Joan of Arc)")
async def hero_manage_add(interaction: discord.Interaction, name: str):
    logger.info(f"[{interaction.user}] /hero_manage add — name={name!r}")
    if not is_hero_admin(interaction):
        await interaction.response.send_message(
            f"❌ You need the **{config.ADMIN_ROLE_NAME}** role.", ephemeral=True
        )
        return
    clean, err = sanitize.hero_name(name)
    if err:
        await interaction.response.send_message(err, ephemeral=True)
        return
    ok, reason = hero_store.add(clean)
    if not ok:
        await interaction.response.send_message(f"⚠️ {reason}", ephemeral=True)
        return
    logger.info(f"[{interaction.user}] Added hero '{clean}'.")
    await interaction.response.send_message(f"✅ Added **{clean}** to the hero list.", ephemeral=True)


@hero_manage_group.command(name="remove", description="[Hero Admin] Remove a hero from the dropdown.")
@app_commands.describe(name="Hero to remove")
@app_commands.autocomplete(name=hero_autocomplete)
async def hero_manage_remove(interaction: discord.Interaction, name: str):
    logger.info(f"[{interaction.user}] /hero_manage remove — name={name!r}")
    if not is_hero_admin(interaction):
        await interaction.response.send_message(
            f"❌ You need the **{config.ADMIN_ROLE_NAME}** role.", ephemeral=True
        )
        return
    ok, result = hero_store.remove(name)
    if not ok:
        await interaction.response.send_message(f"⚠️ {result}", ephemeral=True)
        return
    logger.info(f"[{interaction.user}] Removed hero '{result}'.")
    await interaction.response.send_message(f"🗑️ Removed **{result}** from the hero list.", ephemeral=True)


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────

if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN is not set in your .env file.")
    bot.run(token, log_handler=None)
