import discord
import datetime
from discord.ext import commands
from bot.db import get_db

class Strike(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # add member to the database
    @discord.app_commands.command(name="addmember", description="Add a member")
    async def addmember(self, interaction: discord.Interaction, member: discord.Member):
        memberId = str(member.id)
        memberName = str(member.display_name)

        if await self.checkMember(memberId):
            await interaction.response.send_message(f"{memberName} already exists.")

        else:
            await self.insertData("member", ["id"], [memberId])
            await interaction.response.send_message(f"{memberName} has been added.")


    # add strike to a member using poll
    @discord.app_commands.command(name="addstrike", description="Start poll to vote on strike")
    async def addstrike(self, interaction: discord.Interaction, member: discord.Member, strikes: int = 1):
        memberId = str(member.id)
        memberName = str(member.display_name)
        nrOfStrikes = strikes

        # member does not exist
        if not await self.checkMember(memberId):
            await interaction.response.send_message(f"{memberName} must be added first.")
            return

        # create poll
        poll = discord.Poll(
            question=f"Should {memberName} receive {nrOfStrikes} strike(s)?",
            duration=datetime.timedelta(hours=24)
        )
        poll.add_answer(text="Yes")
        poll.add_answer(text="No")

        await interaction.response.send_message(poll=poll)
        message = await interaction.original_response()
        messageId = message.id

        # create strike for member
        await self.insertData("strike", ["memberId", "messageId"], [memberId, messageId])


    # listen for votes
    @commands.Cog.listener()
    async def on_raw_poll_vote_add(self, payload: discord.RawPollVoteActionEvent):
        memberId = str(payload.user_id)
        print(f"Vote received from {memberId}")

        # ignore votes from non-members
        if not await self.checkMember(memberId):
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
                if await self.checkMember(str(voter.id)):
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
        embed.add_field(name="/addmember <member>", value="Add a member to the bot.", inline=False)
        embed.add_field(name="/addstrike <member> [strikes]", value="Start a 24h poll to give a member one or more strikes. Defaults to 1 strike.", inline=False)
        embed.add_field(name="/showstrikes <member>", value="Show the number of accepted strikes a member has.", inline=False)
        embed.add_field(name="/help", value="Show this help message.", inline=False)
        await interaction.response.send_message(embed=embed)


    # show strikes of member
    @discord.app_commands.command(name="showstrikes", description="Show strikes of member")
    async def showstrikes(self, interaction: discord.Interaction, member: discord.Member):
        memberId = str(member.id)
        memberName = str(member.display_name)

        # member does not exist
        if not await self.checkMember(memberId):
            await interaction.response.send_message(f"{memberName} must be added first.")
            return

        strikes = await self.getStrikes(memberId)
        await interaction.response.send_message(f"{memberName} has {strikes} strike(s).")



    # check if member exists in database
    async def checkMember(self, memberId):
        async with get_db() as db:
            async with db.execute(
                "SELECT id FROM member WHERE id = ? AND deleted = 'no'", [memberId]
            ) as cursor:
                row = await cursor.fetchone()

        return row is not None


    # get strikes for member
    async def getStrikes(self, memberId):
        async with get_db() as db:
            async with db.execute(
                "SELECT COUNT(id) FROM strike WHERE memberId = ? AND status = 'accepted' AND honored = '0000-00-00'", [memberId]
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

        status = 'accepted' if result == 'Yes' else 'rejected'
        async with get_db() as db:
            await db.execute(
                "UPDATE strike SET status = ? WHERE messageId = ?", [status, messageId]
            )
            await db.commit()


    # get member total from database
    async def getMemberTotal(self):
        async with get_db() as db:
            async with db.execute(
                "SELECT COUNT(id) FROM member WHERE deleted = 'no'"
            ) as cursor:
                row = await cursor.fetchone()

        return row[0]


async def setup(bot):
    await bot.add_cog(Strike(bot))
