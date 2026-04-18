import discord
import datetime as dt
from discord.ext import commands
from bot.db import get_db

DEFAULT_STRIKES = 1
MAX_STRIKES = 5
POLL_ANSWER_YES = "Yes"
POLL_ANSWER_NO = "No"
POLL_DURATION_HOURS = 1
STRIKE_STATUS_ACCEPTED = 'accepted'
STRIKE_STATUS_REJECTED = 'rejected'

class Strike(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # add member to the database
    @discord.app_commands.command(name="addmember", description="Add a member")
    async def addmember(self, interaction: discord.Interaction, member: discord.Member):
        memberId = str(member.id)
        guildId = str(interaction.guild_id)
        memberName = str(member.display_name)

        if await self.getUserId(memberId, guildId):
            await interaction.response.send_message(f"{memberName} already exists.")

        else:
            await self.insertData("user", ["memberId", "guildId"], [memberId, guildId])
            await interaction.response.send_message(f"{memberName} has been added.")


    # add strike to a member using poll
    @discord.app_commands.command(name="addstrike", description="Start poll to vote on strike")
    async def addstrike(self, interaction: discord.Interaction, member: discord.Member, strikes: int = DEFAULT_STRIKES):
        memberId = str(member.id)
        guildId = str(interaction.guild_id)
        memberName = str(member.display_name)
        nrOfStrikes = strikes

        if nrOfStrikes > MAX_STRIKES:
            await interaction.response.send_message(f"{MAX_STRIKES} is the maximum number of strikes.")
            return

        userId = await self.getUserId(memberId, guildId)

        # member does not exist
        if not userId:
            await interaction.response.send_message(f"{memberName} must be added first.")
            return

        # create poll
        poll = discord.Poll(
            question=f"Should {memberName} receive {nrOfStrikes} strike(s)?",
            duration=dt.timedelta(hours=POLL_DURATION_HOURS)
        )
        poll.add_answer(text=POLL_ANSWER_YES)
        poll.add_answer(text=POLL_ANSWER_NO)

        await interaction.response.send_message(poll=poll)
        message = await interaction.original_response()
        messageId = message.id

        # create strike for member
        await self.insertData("strike", ["userId", "messageId"], [userId, messageId])


    # listen for votes
    @commands.Cog.listener()
    async def on_raw_poll_vote_add(self, payload: discord.RawPollVoteActionEvent):
        memberId = str(payload.user_id)
        guildId = str(payload.guild_id)
        print(f"Vote received from {memberId}")

        # ignore votes from non-members
        if not await self.getUserId(memberId, guildId):
            return

        channel = self.bot.get_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)
        messageId = message.id
        poll = message.poll

        memberTotal = await self.getMemberTotal()

        # count member votes per answer and check if majority is irreversible
        for pollAnswer in poll.answers:
            memberVotes = 0
            async for voter in pollAnswer.voters():
                if await self.getUserId(str(voter.id), guildId):
                    memberVotes += 1

            if memberVotes > memberTotal / 2:
                await poll.end()
                print(f"{pollAnswer.text}")
                await self.updateStrike(pollAnswer.text, messageId)
                return


    # show help
    @discord.app_commands.command(name="help", description="Show available commands")
    async def help(self, interaction: discord.Interaction):
        embed = discord.Embed(title="Strike Bot Commands")
        embed.add_field(name="/adduser <member>", value="Add a member to the bot.", inline=False)
        embed.add_field(name="/addstrike <member> [strikes]", value=f"Start a {POLL_DURATION_HOURS}-hour poll to give a member one or more strikes. Defaults to {DEFAULT_STRIKES}, maximum is {MAX_STRIKES}.", inline=False)
        embed.add_field(name="/showstrikes <member>", value="Show the number of accepted strikes a member has.", inline=False)
        embed.add_field(name="/help", value="Show this help message.", inline=False)
        await interaction.response.send_message(embed=embed)


    # show strikes of member
    @discord.app_commands.command(name="showstrikes", description="Show strikes of member")
    async def showstrikes(self, interaction: discord.Interaction, member: discord.Member):
        memberId = str(member.id)
        guildId = str(interaction.guild_id)
        memberName = str(member.display_name)

        # member does not exist
        userId = await self.getUserId(memberId, guildId)
        if not userId:
            await interaction.response.send_message(f"{memberName} must be added first.")
            return

        nrOfStrikes = await self.getStrikes(userId)
        await interaction.response.send_message(f"{memberName} has {nrOfStrikes} strike(s).")


    # get user id
    async def getUserId(self, memberId, guildId):
        async with get_db() as db:
            async with db.execute(
                "SELECT id FROM user WHERE memberId = ? AND guildId = ? AND deleted = 'no'", [memberId, guildId]
            ) as cursor:
                row = await cursor.fetchone()

        return row[0] if row else None


    # get strikes for user
    async def getStrikes(self, userId):
        async with get_db() as db:
            async with db.execute(
                "SELECT COUNT(id) FROM strike WHERE userId = ? AND status = 'accepted' AND honored = '0000-00-00'", [userId]
            ) as cursor:
                row = await cursor.fetchone()

        return row[0]


    # insert data into database
    async def insertData(self, table, columns, values):
        placeholders = ', '.join(['?'] * len(values))
        cols = ', '.join(columns)

        async with get_db() as db:
            await db.execute(
                f"INSERT INTO {table} ({cols}) VALUES ({placeholders})", values
            )
            await db.commit()


    # update strike based on result of poll
    async def updateStrike(self, result, messageId):

        status = STRIKE_STATUS_ACCEPTED if result == POLL_ANSWER_YES else STRIKE_STATUS_REJECTED
        async with get_db() as db:
            await db.execute(
                "UPDATE strike SET status = ? WHERE messageId = ?", [status, messageId]
            )
            await db.commit()


    # get member total from database
    async def getMemberTotal(self):
        async with get_db() as db:
            async with db.execute(
                "SELECT COUNT(id) FROM user WHERE deleted = 'no'"
            ) as cursor:
                row = await cursor.fetchone()

        return row[0]


async def setup(bot):
    await bot.add_cog(Strike(bot))
