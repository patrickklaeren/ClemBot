import asyncio
from dataclasses import dataclass

import discord
import discord.ext.commands as commands

import bot.extensions as ext
from bot.clem_bot import ClemBot
from bot.consts import Claims, Colors
from bot.messaging.events import Events
from bot.utils.logging_utils import get_logger
from bot.utils.user_choice import UserChoice

log = get_logger(__name__)

TIMEOUT = 60


@dataclass
class ClassType:
    _abbv: str | None = None

    @property
    def abbv(self) -> str | None:
        return self._abbv

    @abbv.setter
    def abbv(self, val: str) -> None:
        self._abbv = val.lower()

    _teacher: str | None = None

    @property
    def teacher(self) -> str | None:
        return self._teacher

    @teacher.setter
    def teacher(self, val: str) -> None:
        self._teacher = val.lower()

    number = 0
    name: str | None = None
    description: str | None = None

    @property
    def channel(self) -> str:
        empty = ""
        teacher = f'{f"-{self.teacher}" if self.teacher else empty}'
        return f"{self.abbv}-{self.number}{teacher}"

    @property
    def category(self) -> str:
        return f"{self.abbv} {round_down(self.number, 1000)} levels"

    @property
    def role(self) -> str:
        return f"{self.abbv}-{self.number}"

    def __str__(self) -> str:
        return f"""
        Class Major: **{self.abbv}**
        Class Number: ** {self.number}**
        Class Name: ** {self.name}**
        Class Description: ** {self.description}**
        Class Professor: ** {self.teacher}**
        """


class ManageClassesCog(commands.Cog):
    def __init__(self, bot: ClemBot):
        self.bot = bot

    @ext.group(pass_context=True, aliases=["class"], case_insensitive=True)
    @ext.long_help("Command group for the manage classes functionality")
    @ext.short_help("Academic class creation functionality")
    async def classes(self, ctx: ext.ClemBotCtx) -> None:
        pass

    @classes.command(pass_context=True, aliases=["create"])
    @ext.required_claims(Claims.manage_class_add)
    @ext.long_help(
        "Command to initiate the new class creation wizard, optionally takes a "
        'class name as a parameter E.G "cpsc-1010"'
    )
    @ext.short_help("Starts the class creation wizard")
    @ext.example(("class add", "class add cpsc-1010"))
    async def add(self, ctx: ext.ClemBotCtx, class_name: str | None = None) -> None:
        """
        Command to initiate the new class creation wizard, optionally takes a
        class name as a parameter E.G "cpsc-1010"

        Args:
            class_name (str, optional): Formatted class abbreviation and number
            E.G "cpsc-1010" Defaults to None.
        """

        class_repr: ClassType | None = ClassType()

        assert class_repr
        if class_name:
            # try to parse the class name given, if its not in the correct format split will throw
            abbv, num = class_name.split("-")
            class_repr.abbv = abbv
            class_repr.number = int(num)

        # get the user class input and store it in the dataclass
        class_repr = await self.input_class(ctx, class_repr=class_repr)
        if not class_repr:
            return

        try:
            # attempt to get the category to add the class too
            category: discord.CategoryChannel | None = (
                await commands.converter.CategoryChannelConverter().convert(
                    ctx, class_repr.category
                )
            )
        except:
            # the category wasnt found, ask if we want to create one
            log.info(
                f"Class creation category {class_repr.category} non existent, Create a new one?"
            )
            category = await self.create_category(ctx, class_repr)

            # Finding the category and creating one failed
        # We cant do anything more, bail out early
        if not category:
            embed = discord.Embed(
                title=f"Error: Category {class_repr.category} not found and not created, Exiting Wizard",
                color=Colors.Error,
            )
            await ctx.send(embed=embed)
            return

        # Create the class channel in the given category
        channel = await self.create_channel(category, class_repr)
        await channel.send(f"Here is your generated class channel {ctx.author.mention}, Good luck!")

        # create a class role and mark it as assignable
        role = await self.create_role(ctx, class_repr)

        # Sleep here to make sure the role has been sent to the database and added
        await asyncio.sleep(0.5)

        # sync perms with cleanup role
        await self.sync_perms(ctx, channel, role)

    async def input_class(self, ctx: ext.ClemBotCtx, class_repr: ClassType) -> ClassType | None:
        def input_check(msg: discord.Message) -> bool:
            return msg.author == ctx.author and ctx.channel == msg.channel

        # check if the initial command contained a class abbv and number
        if not class_repr.abbv:
            embed = discord.Embed(
                title="**New class setup wizard started :white_check_mark:**",
                color=Colors.ClemsonOrange,
            )
            avi = ctx.author.display_avatar.url
            embed.set_footer(text=f"{ctx.author} - Time Limit: {TIMEOUT} Seconds", icon_url=avi)
            embed.add_field(name="**Current values**", value=class_repr)
            embed.add_field(
                name="Please enter the class abbreviation and name E.G.",
                value="cpsc-1010",
                inline=False,
            )

            await ctx.send(embed=embed)

            try:
                msg = await self.bot.wait_for("message", timeout=TIMEOUT, check=input_check)
                abbv, number = msg.content.split("-")
                class_repr.abbv = abbv
                class_repr.number = int(number)
            except asyncio.TimeoutError:
                await self.input_timeout(ctx)
                return None
        else:
            embed = discord.Embed(
                title="**New class setup wizard started :white_check_mark:**",
                color=Colors.ClemsonOrange,
            )
            await ctx.send(embed=embed)

        embed = discord.Embed(
            title=f'Class "{class_repr.abbv}-{class_repr.number}" set', color=Colors.ClemsonOrange
        )
        avi = ctx.author.display_avatar.url
        embed.set_footer(text=f"{ctx.author} - Time Limit: {TIMEOUT} Seconds", icon_url=avi)
        embed.add_field(name="**Current values**", value=class_repr)
        embed.add_field(
            name='Please enter the class name or "None" to skip this step E.G.',
            value="Introduction to C",
            inline=False,
        )

        await ctx.send(embed=embed)

        try:
            val = (await self.bot.wait_for("message", timeout=TIMEOUT, check=input_check)).content
            if val != "None":
                class_repr.name = val
        except asyncio.TimeoutError:
            await self.input_timeout(ctx)
            return None

        embed = discord.Embed(
            title=f'Class name: "{class_repr.name}" set', color=Colors.ClemsonOrange
        )
        avi = ctx.author.display_avatar.url
        embed.set_footer(text=f"{ctx.author} - Time Limit: {TIMEOUT} Seconds", icon_url=avi)
        embed.add_field(name="**Current values**", value=class_repr)
        embed.add_field(
            name='Please enter the class description (must be less than 256 characters) or "None" to skip this step E.G.',
            value="An overview of programming fundamentals using the C programming langauge",
            inline=False,
        )

        await ctx.send(embed=embed)

        try:
            # Keep retrying to get the description until we get a less then 256 characters one or the wait times out
            while (
                len(
                    val := (
                        await self.bot.wait_for("message", timeout=TIMEOUT, check=input_check)
                    ).content
                )
            ) > 255:
                await ctx.send(
                    "Error: Description needs to be less than 256 characters\nPlease try again"
                )
            if val != "None":
                class_repr.description = val
        except asyncio.TimeoutError:
            await self.input_timeout(ctx)
            return None

        embed = discord.Embed(
            title=f'Class description: "{class_repr.description}" set', color=Colors.ClemsonOrange
        )
        avi = ctx.author.display_avatar.url
        embed.set_footer(text=f"{ctx.author} - Time Limit: {TIMEOUT} Seconds", icon_url=avi)
        embed.add_field(name="**Current values**", value=class_repr)
        embed.add_field(
            name='Please enter the class professors last name or "None" to skip this step E.G.',
            value="Plis",
            inline=False,
        )

        await ctx.send(embed=embed)

        try:
            val = (await self.bot.wait_for("message", timeout=TIMEOUT, check=input_check)).content
            if val != "None":
                class_repr.teacher = val
        except asyncio.TimeoutError:
            await self.input_timeout(ctx)
            return None

        embed = discord.Embed(
            title=f'Class and role "{class_repr.role}" created in category "{class_repr.category}" ',
            color=Colors.ClemsonOrange,
        )
        embed.add_field(name="**Current values**", value=class_repr)
        await ctx.send(embed=embed)

        return class_repr

    async def create_category(
        self, ctx: ext.ClemBotCtx, class_repr: ClassType
    ) -> discord.CategoryChannel | None:
        get_input = UserChoice(ctx=ctx, timeout=TIMEOUT)
        choice = await get_input.send_confirmation(
            content=f"""
            Error: Category "{class_repr.category}" not found
            Would you like to create it?
            """,
            is_error=True,
        )

        if not choice:
            return None

        log.info(f'Creating category "{class_repr.category}" in guild: "{ctx.guild.name}"')
        return await ctx.guild.create_category(class_repr.category)

    async def create_channel(
        self, category: discord.CategoryChannel, class_repr: ClassType
    ) -> discord.TextChannel:
        log.info(f'Creating new Class channel "{class_repr.name}""')
        return await category.create_text_channel(
            class_repr.channel, topic=f"{class_repr.name} - {class_repr.description}"
        )

    async def create_role(self, ctx: ext.ClemBotCtx, class_repr: ClassType) -> discord.Role:
        log.info(f'Creating new class role "{class_repr.role}""')
        # Attempt to convert the role, if we cant then we create a new one
        try:
            role = await commands.converter.RoleConverter().convert(ctx, class_repr.role)
        except:
            role = await ctx.guild.create_role(name=class_repr.role, mentionable=False)

        try:
            # wait a split second to insert the role in the db
            await asyncio.sleep(0.25)
            await self.bot.role_route.set_assignable(role.id, True, raise_on_error=True)
        except:
            # If the marking of the role as assignable fails
            # Wait a second for the api to finish inserting the role then try it again
            await asyncio.sleep(1)
            await self.bot.role_route.set_assignable(role.id, True, raise_on_error=True)

        return role

    async def sync_perms(
        self, ctx: ext.ClemBotCtx, channel: discord.TextChannel, role: discord.Role
    ) -> None:
        # Check if cleanup role exists
        if not (cleanup := discord.utils.get(ctx.guild.roles, name="Cleanup")):
            cleanup = await ctx.guild.create_role(name="Cleanup", mentionable=False)

            assert cleanup

            await self.bot.role_route.set_assignable(cleanup.id, True, raise_on_error=True)

            # Upon detecting first time user, show embed showing how to use commands
            embed = discord.Embed(
                title="Welcome to ClemBot class management!", color=Colors.ClemsonOrange
            )
            embed.add_field(
                name="To assign your class year or a specific class, run the command:",
                value="```!roles <year>``` or ```!roles cpsc-<class-number>```",
                inline=False,
            )
            embed.add_field(
                name="To see a list of assignable roles run:", value="```!roles```", inline=False
            )
            embed.add_field(
                name="If you would like to hide all class channels you are not in, run:",
                value="```!roles cleanup```",
                inline=False,
            )
            await ctx.send(embed=embed)

        log.info("Syncing channel and role with cleanup")
        await channel.set_permissions(role, view_channel=True)
        await channel.set_permissions(cleanup, view_channel=False)
        await role.edit(position=2)

        await cleanup.edit(position=1)

    @classes.command(pass_context=True, aliases=["delete"])
    @commands.has_guild_permissions(administrator=True)
    async def archive(self, ctx: ext.ClemBotCtx, channel: discord.TextChannel) -> None:
        pass

    async def input_timeout(self, ctx: ext.ClemBotCtx) -> None:
        await ctx.send("Response timed out please redo the class wizard")


def round_down(num: int, divisor: int) -> int:
    return num - (num % divisor)


async def setup(bot: ClemBot) -> None:
    await bot.add_cog(ManageClassesCog(bot))
